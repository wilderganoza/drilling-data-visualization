"""ROP Prediction — ML engine.

Builds a supervised dataset by pooling rows across wells, then trains a zoo of
regressors (XGBoost, LightGBM, sklearn ensembles, linear/KNN/SVR baselines),
ranks them, tunes the chosen one with Optuna (TPE sampler) and reports
train/test/blind metrics with plot data.

Design notes:
- Preprocessing (scaling / PCA / outlier removal) is fit on TRAIN only and applied
  to test/blind — no leakage. Mirrors the Data-Cleaning (Outliers) options.
- A designated *blind well* is held out entirely (never in train/test) to validate
  on a truly unseen well.
- Datasets are deterministic (fixed seed) and cached by config hash so the
  pre-selection / HPO / validation steps don't re-fetch and re-split each time.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.services.rop_jobs import JobCancelled
from app.services.rop_prediction import TARGET, feature_label
from app.web.shared import fetch_records

# ---------------------------------------------------------------------------
# Model zoo
# ---------------------------------------------------------------------------
MODELS: Dict[str, Dict[str, str]] = {
    "lightgbm": {"label": "LightGBM", "family": "Gradient boosting"},
    "xgboost": {"label": "XGBoost", "family": "Gradient boosting"},
    "hist_gb": {"label": "HistGradientBoosting", "family": "Gradient boosting"},
    "random_forest": {"label": "Random Forest", "family": "Bagging"},
    "extra_trees": {"label": "Extra Trees", "family": "Bagging"},
    "gradient_boosting": {"label": "Gradient Boosting", "family": "Gradient boosting"},
    "adaboost": {"label": "AdaBoost", "family": "Boosting"},
    "mlp": {"label": "Neural Network (MLP)", "family": "Neural network"},
    "knn": {"label": "K-Nearest Neighbors", "family": "Instance"},
    "svr": {"label": "Support Vector Regressor", "family": "Kernel"},
    "ridge": {"label": "Ridge Regression", "family": "Linear"},
    "linear": {"label": "Linear Regression", "family": "Linear"},
    "elasticnet": {"label": "Elastic Net", "family": "Linear"},
    "lasso": {"label": "Lasso Regression", "family": "Linear"},
    "bayesian_ridge": {"label": "Bayesian Ridge", "family": "Linear"},
    "omp": {"label": "Orthogonal Matching Pursuit", "family": "Linear"},
}
# huber/lars were tried and removed (not a bug — both are numerically fragile on
# this app's typical feature set): Huber's LBFGS solver diverges to nonsensical
# coefficients on the wide-magnitude/collinear engineered features this pipeline
# routinely produces (lag/moving-avg/std variants of the same sensor are highly
# correlated by construction), and LARS is textbook-documented as unstable under
# exactly that kind of multicollinearity. Verified with synthetic collinear data
# (condition number ~200-4800) reproducing Huber convergence warnings; real
# preselect runs showed Huber's score diverge to ~1e35 and LARS fail outright.
DEFAULT_MODELS = ["lightgbm", "xgboost", "hist_gb", "random_forest", "extra_trees", "ridge"]


def make_model(key: str, params: Optional[dict] = None, log_target: bool = False):
    base = _make_base(key, params)
    if log_target:
        # Train on log1p(ROP) (stabilises the right-skewed target); predictions are
        # auto-inverted with expm1 so metrics / intervals / plots stay in ft/hr.
        from sklearn.compose import TransformedTargetRegressor
        return TransformedTargetRegressor(regressor=base, func=np.log1p, inverse_func=np.expm1)
    return base


def _make_base(key: str, params: Optional[dict] = None):
    p = dict(params or {})
    if key == "linear":
        from sklearn.linear_model import LinearRegression
        return LinearRegression()
    if key == "ridge":
        from sklearn.linear_model import Ridge
        return Ridge(alpha=p.get("alpha", 1.0))
    if key == "random_forest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_jobs=-1, random_state=42, **p)
    if key == "extra_trees":
        from sklearn.ensemble import ExtraTreesRegressor
        return ExtraTreesRegressor(n_jobs=-1, random_state=42, **p)
    if key == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(random_state=42, **p)
    if key == "hist_gb":
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(random_state=42, **p)
    if key == "xgboost":
        from xgboost import XGBRegressor
        return XGBRegressor(tree_method="hist", n_jobs=-1, random_state=42, verbosity=0, **p)
    if key == "lightgbm":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_jobs=-1, random_state=42, verbose=-1, **p)
    if key == "knn":
        from sklearn.neighbors import KNeighborsRegressor
        return KNeighborsRegressor(n_jobs=-1, **p)
    if key == "svr":
        from sklearn.svm import SVR
        return SVR(**p)
    if key == "adaboost":
        from sklearn.ensemble import AdaBoostRegressor
        return AdaBoostRegressor(random_state=42, **p)
    if key == "mlp":
        from sklearn.neural_network import MLPRegressor
        # early_stopping holds out part of train internally to avoid overfitting
        # small/noisy pooled-well datasets; max_iter generous since it stops early.
        p.setdefault("hidden_layer_sizes", (64, 32))
        p.setdefault("max_iter", 500)
        return MLPRegressor(random_state=42, early_stopping=True, **p)
    if key == "elasticnet":
        from sklearn.linear_model import ElasticNet
        return ElasticNet(random_state=42, **p)
    if key == "lasso":
        from sklearn.linear_model import Lasso
        return Lasso(random_state=42, **p)
    if key == "bayesian_ridge":
        from sklearn.linear_model import BayesianRidge
        return BayesianRidge(**p)
    if key == "omp":
        from sklearn.linear_model import OrthogonalMatchingPursuit
        return OrthogonalMatchingPursuit(**p)
    raise ValueError(f"unknown model {key}")


def suggest_params(key: str, trial) -> dict:
    """Optuna search space. Keys match make_model constructor kwargs exactly."""
    if key == "ridge":
        return {"alpha": trial.suggest_float("alpha", 1e-3, 100.0, log=True)}
    if key in ("random_forest", "extra_trees"):
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 300, step=50),
            "max_depth": trial.suggest_int("max_depth", 4, 16),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 2, 20),
            "max_features": trial.suggest_float("max_features", 0.3, 1.0),
        }
    if key == "gradient_boosting":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }
    if key == "hist_gb":
        return {
            "max_iter": trial.suggest_int("max_iter", 100, 600, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 2, 12),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-3, 10.0, log=True),
        }
    if key == "xgboost":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
    if key == "lightgbm":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 255),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        }
    if key == "knn":
        return {
            "n_neighbors": trial.suggest_int("n_neighbors", 3, 40),
            "weights": trial.suggest_categorical("weights", ["uniform", "distance"]),
            "p": trial.suggest_int("p", 1, 2),
        }
    if key == "svr":
        return {
            "C": trial.suggest_float("C", 0.1, 100.0, log=True),
            "gamma": trial.suggest_categorical("gamma", ["scale", "auto"]),
            "epsilon": trial.suggest_float("epsilon", 0.01, 1.0, log=True),
        }
    if key == "adaboost":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 50, 400, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 1.0, log=True),
            "loss": trial.suggest_categorical("loss", ["linear", "square", "exponential"]),
        }
    if key == "mlp":
        return {
            "hidden_layer_sizes": trial.suggest_categorical(
                "hidden_layer_sizes", [(32,), (64,), (64, 32), (128, 64), (100, 50, 25)]),
            "alpha": trial.suggest_float("alpha", 1e-5, 1e-1, log=True),
            "learning_rate_init": trial.suggest_float("learning_rate_init", 1e-4, 1e-2, log=True),
        }
    if key == "elasticnet":
        return {
            "alpha": trial.suggest_float("alpha", 1e-3, 10.0, log=True),
            "l1_ratio": trial.suggest_float("l1_ratio", 0.0, 1.0),
        }
    if key == "lasso":
        return {"alpha": trial.suggest_float("alpha", 1e-3, 10.0, log=True)}
    return {}


def supports_hpo(key: str) -> bool:
    # bayesian_ridge/omp auto-select their own regularization — no meaningful
    # search space to tune (same reason "linear" is excluded).
    return key not in ("linear", "bayesian_ridge", "omp")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))
    nz = y_true != 0
    mape = float(np.mean(np.abs((y_true[nz] - y_pred[nz]) / y_true[nz])) * 100.0) if nz.any() else None
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "mape": mape,
    }


def _error_bands(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[dict]:
    """Bins absolute percentage error into 10%-wide bands (0-10%, 10-20%, ...,
    90%+) plus a cumulative-frequency curve — the diagnostic from Zou (2026,
    Sci Rep) Fig. 8: what fraction of predictions falls within each error band,
    and what fraction is "good enough" at any given threshold."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    nz = y_true != 0
    if not nz.any():
        return None
    ape = np.abs((y_true[nz] - y_pred[nz]) / y_true[nz]) * 100.0
    n = len(ape)
    edges = list(range(0, 100, 10)) + [np.inf]  # 0,10,...,90,inf -> 10 bands
    labels, freq = [], []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        labels.append(f"{lo:g}-{hi:g}%" if np.isfinite(hi) else f">{lo:g}%")
        count = int(((ape >= lo) & (ape < hi)).sum())
        freq.append(count / n * 100.0)
    cumulative = np.cumsum(freq).tolist()
    return {"labels": labels, "freq": [float(f) for f in freq],
            "cumulative": [float(c) for c in cumulative], "n": n}


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
@dataclass
class Dataset:
    X_train: np.ndarray
    y_train: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    X_blind: Optional[np.ndarray]
    y_blind: Optional[np.ndarray]
    feature_names: List[str]     # post-PCA names (for importance labels)
    raw_features: List[str]      # original feature columns, for inference
    blind_well_id: Optional[int]
    n_pooled: int
    n_removed_outliers: int
    n_invalid: int = 0           # train/test pool rows dropped by the plausible-range gate
    n_invalid_blind: int = 0     # same, but for the blind well specifically (separate scope)
    split_grouped: bool = False  # True if test wells are disjoint from train wells
    groups_train: Optional[np.ndarray] = None  # well id per train row (for GroupKFold)
    groups_test: Optional[np.ndarray] = None   # well id per test row (which wells are in the test split)
    scaler: Any = None
    pca: Any = None
    drift: Optional[List[dict]] = None  # per-feature train-vs-blind distribution shift
    raw_stats: Optional[dict] = None    # per raw feature {median,min,max} for what-if
    log_target: bool = False            # train on log1p(ROP); predictions auto-inverted


_DS_CACHE: Dict[str, Dataset] = {}
_DS_CACHE_LOCK = threading.Lock()  # build_dataset() runs in a ThreadPoolExecutor (rop_jobs);
                                    # without this, two concurrent jobs can race on the
                                    # check-then-act cache read/clear/write below.


def well_frame(db, wid: int, per_well: int, depth_range: Optional[tuple] = None,
               date_range: Optional[tuple] = None, bit_sizes: Optional[list] = None) -> Optional[pd.DataFrame]:
    """One well's rows as a DataFrame with raw channels + engineered features
    (depth-ordered). Shared by dataset build, feature stats, previews, inference.

    `depth_range`/`date_range` are (lo, hi) tuples (either side may be None) —
    filtered in SQL before the `per_well` LIMIT, so a narrow window isn't starved
    by the sample cap.

    `bit_sizes`, if given, keeps only rows drilled with one of those diameters —
    applied here (not per-caller) so every consumer (dataset build, Features-step
    stats, Scaling/PCA/Outliers previews, well-filtering/correlation tools) sees
    the same filtered rows, not just the final trained model."""
    from app.services.rop_features import engineer
    recs = fetch_records(db, wid, None, raw_sample_size=per_well,
                         processed_page_size=per_well, domain="depth",
                         depth_range=depth_range, date_range=date_range)
    if not recs:
        return None
    df = engineer(pd.DataFrame(recs))
    if bit_sizes and "bit_size" in df.columns:
        bs = pd.to_numeric(df["bit_size"], errors="coerce").round(3)
        df = df[bs.isin([round(b, 3) for b in bit_sizes])]
        if df.empty:
            return None
    return df


def _scaler(method: str):
    if method == "standard":
        from sklearn.preprocessing import StandardScaler
        return StandardScaler()
    if method == "minmax":
        from sklearn.preprocessing import MinMaxScaler
        return MinMaxScaler()
    if method == "robust":
        from sklearn.preprocessing import RobustScaler
        return RobustScaler()
    if method == "maxabs":
        from sklearn.preprocessing import MaxAbsScaler
        return MaxAbsScaler()
    return None


def _inlier_mask(X: np.ndarray, y: np.ndarray, method: str, params: Optional[dict] = None) -> np.ndarray:
    """Boolean mask of rows to KEEP (train-only outlier removal on features+target).

    zscore/iqr/isolation_forest/local_outlier_factor/dbscan are the same methods
    and per-method parameters as the Data-Cleaning wizard: zscore (threshold σ),
    iqr (multiplier), isolation_forest (contamination, n_estimators),
    local_outlier_factor (n_neighbors), dbscan (eps, min_samples). Model-based
    methods run on standardised data so distance scales are comparable.

    "leverage" is ROP-Prediction-only (not offered in Data-Cleaning): the
    Hat-matrix/Williams-plot technique — flags rows whose FEATURE combination is
    extreme (high-leverage in X-space), independent of their residual/target
    value. No model fit or standardization needed, and no tunable parameter —
    the threshold is the fixed Williams-plot convention H* = 3(n+1)/m.
    """
    p = params or {}
    data = np.column_stack([X, y])
    if method == "leverage":
        # Design matrix with an intercept column, matching H = X(XᵀX)⁻¹Xᵀ.
        Xd = np.column_stack([np.ones(len(X)), X])
        m, n_params = Xd.shape  # n_params = number of features + 1 (intercept)
        try:
            xtx_inv = np.linalg.pinv(Xd.T @ Xd)
        except np.linalg.LinAlgError:
            return np.ones(len(X), dtype=bool)
        # Diagonal of the Hat matrix H = Xd @ xtx_inv @ Xdᵀ, without forming the
        # full m×m matrix: h_i = x_i @ xtx_inv @ x_iᵀ for each row.
        h = np.einsum("ij,jk,ik->i", Xd, xtx_inv, Xd)
        h_star = 3.0 * n_params / m
        return h <= h_star
    if method == "zscore":
        thr = float(p.get("threshold", 3.0))
        mu = data.mean(axis=0)
        sd = data.std(axis=0)
        sd[sd == 0] = 1.0
        z = np.abs((data - mu) / sd)
        return (z <= thr).all(axis=1)
    if method == "iqr":
        mult = float(p.get("multiplier", 1.5))
        q1 = np.percentile(data, 25, axis=0)
        q3 = np.percentile(data, 75, axis=0)
        iqr = q3 - q1
        lo, hi = q1 - mult * iqr, q3 + mult * iqr
        return ((data >= lo) & (data <= hi)).all(axis=1)

    if method in ("isolation_forest", "local_outlier_factor", "dbscan"):
        mu = data.mean(axis=0)
        sd = data.std(axis=0)
        sd[sd == 0] = 1.0
        Z = (data - mu) / sd
        if method == "isolation_forest":
            from sklearn.ensemble import IsolationForest
            cont = min(0.5, max(0.001, float(p.get("contamination", 0.05))))
            n_est = int(p.get("n_estimators") or 100)
            return IsolationForest(n_estimators=n_est, contamination=cont,
                                   random_state=42, n_jobs=-1).fit_predict(Z) == 1
        if method == "local_outlier_factor":
            from sklearn.neighbors import LocalOutlierFactor
            n_nb = max(2, int(p.get("n_neighbors") or 20))
            return LocalOutlierFactor(n_neighbors=n_nb, n_jobs=-1).fit_predict(Z) == 1
        from sklearn.cluster import DBSCAN
        eps = max(0.01, float(p.get("eps", 0.5)))
        min_s = max(1, int(p.get("min_samples") or 5))
        labels = DBSCAN(eps=eps, min_samples=min_s, n_jobs=-1).fit_predict(Z)
        return labels != -1
    return np.ones(len(X), dtype=bool)


def _cache_key(cfg: dict) -> str:
    return hashlib.md5(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()


def is_cached(cfg: dict) -> bool:
    """True if build_dataset(cfg) would return instantly from _DS_CACHE instead
    of re-fetching every selected well — used to give the pre-flight time
    estimate an honest 'this'll be instant' instead of a scary minutes figure."""
    with _DS_CACHE_LOCK:
        return _cache_key(cfg) in _DS_CACHE


def build_dataset(db, cfg: dict, progress_cb=None, cancel_event=None) -> Dataset:
    key = _cache_key(cfg)
    with _DS_CACHE_LOCK:
        if key in _DS_CACHE:
            return _DS_CACHE[key]

    features: List[str] = cfg["features"]
    well_ids: List[int] = cfg["well_ids"]
    blind_id: Optional[int] = cfg.get("blind_well_id")
    seed = int(cfg.get("seed", 42))
    cols = features + [TARGET]

    train_pool_ids = [w for w in well_ids if w != blind_id]
    # No per-well/pool cap — pull every row of every selected well. Larger than
    # any single well's actual row count, so this is just the SQL LIMIT ceiling,
    # not a real truncation.
    per_well = 2_000_000
    depth_range = cfg.get("depth_range")
    date_range = cfg.get("date_range")
    bit_sizes = cfg.get("bit_sizes") or []

    from app.services.rop_prediction import PLAUSIBLE_RANGES
    ranges = {c: PLAUSIBLE_RANGES[c] for c in cols if c in PLAUSIBLE_RANGES}

    def _rows(ids, invalid_counter):
        frames = []
        for i, wid in enumerate(ids):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled()
            if progress_cb is not None:
                progress_cb({"stage": f"Loading well data… ({i + 1}/{len(ids)})"})
            # bit_sizes filtered inside well_frame() itself — mixing hole sizes in
            # one model conflates very different ROP mechanics (e.g. 8.5" vs 17.5").
            df_w = well_frame(db, wid, per_well, depth_range=depth_range, date_range=date_range,
                              bit_sizes=bit_sizes)   # raw channels + engineered
            if df_w is None or not all(c in df_w.columns for c in cols):
                continue
            sub = df_w[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=cols)
            sub = sub[sub[TARGET] > 0]
            n0 = len(sub)
            for c, (lo, hi) in ranges.items():
                sub = sub[(sub[c] >= lo) & (sub[c] <= hi)]
            invalid_counter["n"] += n0 - len(sub)
            if len(sub):
                sub = sub.copy()
                sub["__wid"] = wid
                frames.append(sub)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols + ["__wid"])

    # Separate counters — n_invalid is scoped to the train/test pool only (same
    # scope as n_pooled/n_train/n_test), not conflated with the blind well's own
    # count (see n_invalid_blind below).
    invalid = {"n": 0}
    invalid_blind = {"n": 0}
    df = _rows(train_pool_ids, invalid)
    if progress_cb is not None:
        progress_cb({"stage": "Splitting & scaling…"})

    # Friendly guard BEFORE the split: with a near-empty pool sklearn's
    # train_test_split raises its raw "With n_samples=0, test_size=0.2 ..."
    # ValueError, which is what the user used to see instead of the message
    # the job layer only checked for AFTER a successful build.
    if len(df) < 30:
        raise ValueError(
            "Not enough valid rows after the quality gate & filtering "
            f"({len(df)} found, at least 30 needed). Pick more wells or different "
            "features, or relax the depth/date/bit-diameter filters.")

    raw_stats = {}
    for f in features:
        col = df[f] if len(df) else None
        raw_stats[f] = {
            "median": float(col.median()) if col is not None and len(col) else 0.0,
            "min": float(col.min()) if col is not None and len(col) else 0.0,
            "max": float(col.max()) if col is not None and len(col) else 1.0,
        }

    from sklearn.model_selection import GroupShuffleSplit, train_test_split
    X = df[features].to_numpy(dtype=float)
    y = df[TARGET].to_numpy(dtype=float)
    g = df["__wid"].to_numpy()
    test_pct = float(cfg.get("test_pct", 20)) / 100.0

    # Grouped test split (test wells disjoint from train wells) when there are enough
    # wells — removes within-well leakage so the test metric is honest, not just the
    # blind well. Falls back to a random split if too few wells.
    split_grouped = len(np.unique(g)) >= 4
    if split_grouped:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_pct, random_state=seed)
        tr_idx, te_idx = next(gss.split(X, y, groups=g))
        X_train, X_test, y_train, y_test, g_train, g_test = X[tr_idx], X[te_idx], y[tr_idx], y[te_idx], g[tr_idx], g[te_idx]
    else:
        X_train, X_test, y_train, y_test, g_train, g_test = train_test_split(
            X, y, g, test_size=test_pct, random_state=seed)

    X_blind = y_blind = None
    if blind_id is not None:
        bdf = _rows([blind_id], invalid_blind)
        if len(bdf):
            X_blind = bdf[features].to_numpy(dtype=float)
            y_blind = bdf[TARGET].to_numpy(dtype=float)

    # Train-only outlier removal.
    n_removed = 0
    om = cfg.get("outlier_method", "none")
    if om and om != "none":
        mask = _inlier_mask(X_train, y_train, om, cfg.get("outlier_params") or {})
        n_removed = int((~mask).sum())
        X_train, y_train, g_train = X_train[mask], y_train[mask], g_train[mask]

    # Drift: how far the blind well's feature distributions sit from training,
    # in raw units (before scaling). |mean shift| in training-σ; >2σ = strong.
    drift = None
    if X_blind is not None and len(X_blind):
        mu, sd = X_train.mean(axis=0), X_train.std(axis=0)
        sd = np.where(sd == 0, 1.0, sd)
        shift = np.abs(X_blind.mean(axis=0) - mu) / sd
        drift = [{"feature": features[i], "label": feature_label(features[i]), "shift_sigma": float(shift[i]),
                  "strong": bool(shift[i] > 2.0)} for i in range(len(features))]
        drift.sort(key=lambda d: -d["shift_sigma"])

    # Scaling (fit on train).
    sc = _scaler(cfg.get("scaling", "standard"))
    if sc is not None:
        X_train = sc.fit_transform(X_train)
        X_test = sc.transform(X_test)
        if X_blind is not None:
            X_blind = sc.transform(X_blind)

    # PCA (fit on train).
    pca = None
    feat_names = list(features)
    if cfg.get("pca_enabled"):
        from sklearn.decomposition import PCA
        n_comp = cfg.get("pca_components") or None
        if n_comp is not None:  # clamp: sklearn errors if components > features/rows
            n_comp = max(1, min(int(n_comp), len(features), max(1, len(X_train) - 1)))
        pca = PCA(n_components=n_comp, svd_solver=cfg.get("pca_svd_solver", "auto"),
                  whiten=bool(cfg.get("pca_whiten")), random_state=seed)
        X_train = pca.fit_transform(X_train)
        X_test = pca.transform(X_test)
        if X_blind is not None:
            X_blind = pca.transform(X_blind)
        feat_names = [f"PC{i + 1}" for i in range(X_train.shape[1])]

    ds = Dataset(
        X_train=X_train, y_train=y_train, X_test=X_test, y_test=y_test,
        X_blind=X_blind, y_blind=y_blind, feature_names=feat_names,
        raw_features=list(features), blind_well_id=blind_id, n_pooled=len(df),
        n_removed_outliers=n_removed, n_invalid=invalid["n"], n_invalid_blind=invalid_blind["n"],
        split_grouped=split_grouped,
        groups_train=g_train, groups_test=g_test, scaler=sc, pca=pca,
        drift=drift, raw_stats=raw_stats,
        log_target=bool(cfg.get("log_target")),
    )
    with _DS_CACHE_LOCK:
        # Oldest-first eviction (dicts are insertion-ordered), not a wholesale
        # clear() — a full clear used to nuke the entry a later wizard step (e.g.
        # Validation) still needs just because the user had tried >8 well/feature
        # combinations earlier, forcing a full, very slow rebuild (this dataset
        # build alone can take several minutes with the no-row-cap policy).
        while len(_DS_CACHE) >= 8:
            _DS_CACHE.pop(next(iter(_DS_CACHE)))
        _DS_CACHE[key] = ds
    return ds


# ---------------------------------------------------------------------------
# Pre-flight time estimate
# ---------------------------------------------------------------------------
# Calibrated from real measurements taken this session (not a formal benchmark —
# hardware/row-count/network vary, hence the wide ±50% band the UI shows). The
# per-well DB round-trip dominates build cost far more than row count does:
# ~425s to build a dataset from 913 wells (~0.47s/well) vs. ~1s for the same
# step on 3 small wells. SHAP + permutation importance scale with TEST rows,
# not well count: ~39s end-to-end (fit+calibrate+perm+SHAP) on an 11k-row/
# 3-well validation run, most of it in perm/SHAP → ~0.0035s/test-row.
SECONDS_PER_WELL_BUILD = 0.5
SECONDS_PER_TEST_ROW_INTERPRET = 0.0035
# Average rows/well pooled across a full-DB run this session (2,901,686 rows /
# 913 wells) — used only to guess a test-row count BEFORE the dataset is built,
# for the pre-flight estimate; actual wells vary widely, hence the wide band.
AVG_ROWS_PER_WELL = 3180
# Rough multiplier of "one dataset build" for the rest of each job kind's work,
# on top of the (possibly-zero-if-cached) build cost above.
_KIND_BUILD_MULTIPLIER = {"preselect": 1.3, "hpo": 1.0, "validation": 1.0}


def estimate_seconds(cfg: dict, kind: str, n_trials: int = 20) -> tuple[float, float]:
    """Rough (low, high) second estimate for a preselect/hpo/validation run —
    an approximation for the pre-flight UI hint, not a promise. Skips the build
    cost entirely when this exact cfg is already in _DS_CACHE."""
    n_wells = len({w for w in cfg.get("well_ids") or [] if w != cfg.get("blind_well_id")})
    build = 0.0 if is_cached(cfg) else n_wells * SECONDS_PER_WELL_BUILD
    if kind == "preselect":
        extra = build * (_KIND_BUILD_MULTIPLIER["preselect"] - 1.0)
    elif kind == "hpo":
        # Each trial re-fits on the ALREADY-loaded train split — a small, roughly
        # constant per-trial cost regardless of well count; ~1-3s/trial is typical
        # for the tree models in this zoo, wider band since it's model-dependent.
        extra = n_trials * 2.0
    else:  # validation
        test_pct = float(cfg.get("test_pct", 20)) / 100.0
        test_rows = int(round(n_wells * AVG_ROWS_PER_WELL * test_pct))  # crude pre-build guess
        extra = SECONDS_PER_TEST_ROW_INTERPRET * test_rows + 5.0  # +fit/calibrate/package
    total = build + extra
    return (max(1.0, total * 0.5), max(2.0, total * 1.5))


# ---------------------------------------------------------------------------
# Train / rank / tune / validate
# ---------------------------------------------------------------------------
def preselect(ds: Dataset, model_keys: List[str], progress_cb=None, cancel_event=None) -> List[dict]:
    """Trains each model in `model_keys` in turn. If `progress_cb` is given, it's
    called after each model finishes with {"done": [...results so far, unsorted],
    "total": len(model_keys), "current": <key just started, or None if finished>}
    so a caller (e.g. a polling UI) can show live per-model completion.
    If `cancel_event` is set between models, stops before starting the next one
    (a model already fitting still runs to completion, but its result is dropped)."""
    results = []
    for k in model_keys:
        if cancel_event is not None and cancel_event.is_set():
            break
        if progress_cb is not None:
            progress_cb({"done": list(results), "total": len(model_keys), "current": k})
        try:
            m = make_model(k, log_target=ds.log_target)
            m.fit(ds.X_train, ds.y_train)
            mt = metrics(ds.y_test, m.predict(ds.X_test))
            train_mt = metrics(ds.y_train, m.predict(ds.X_train))
            # Top-level keys (r2/rmse/mae/mape) stay TEST metrics — ranking/sort is
            # by test R², unchanged — train is additionally nested so the UI can
            # show both without ambiguity about which one is "the" score.
            results.append({"key": k, "label": MODELS[k]["label"], "family": MODELS[k]["family"], "ok": True,
                            "train": train_mt, "test": mt, **mt})
        except Exception as exc:  # keep ranking the rest
            results.append({"key": k, "label": MODELS.get(k, {}).get("label", k), "ok": False, "error": str(exc)[:200]})
    if progress_cb is not None:
        progress_cb({"done": list(results), "total": len(model_keys), "current": None})
    results.sort(key=lambda r: (not r["ok"], -(r.get("r2") if r.get("r2") is not None else -9)))
    return results


def optimize(ds: Dataset, model_key: str, n_trials: int = 20, progress_cb=None, cancel_event=None) -> dict:
    import optuna
    from sklearn.model_selection import GroupKFold, KFold, cross_val_score
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Rows from one well are autocorrelated (adjacent depths), so a plain KFold
    # leaks near-duplicate rows across folds and reports optimistic scores. Split by
    # WELL when there are enough wells — the honest, blind-well-consistent estimate.
    groups = ds.groups_train
    n_wells = len(np.unique(groups)) if groups is not None else 0
    use_groups = n_wells >= 3
    cv = GroupKFold(n_splits=min(4, n_wells)) if use_groups else KFold(n_splits=3, shuffle=True, random_state=42)

    def objective(trial):
        params = suggest_params(model_key, trial)
        model = make_model(model_key, params, log_target=ds.log_target)
        scores = cross_val_score(model, ds.X_train, ds.y_train,
                                 groups=(groups if use_groups else None), cv=cv,
                                 scoring="r2", n_jobs=1)
        return float(scores.mean())

    # No pruner: the objective is a single cross_val_score call per trial, with
    # no intermediate trial.report() steps, so a pruner (e.g. MedianPruner)
    # could never actually prune anything — configuring one just misled the UI
    # copy into advertising "median pruning" that never ran.
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    # Builds the (trial, r2, best-so-far) history as trials complete — the SAME
    # list backs both the live progress view (via progress_cb) and the final
    # returned `history`. Train/test metrics for the chosen model are computed
    # once, after the search, not per trial (an extra full fit per trial bought
    # nothing once the per-trial train/test lines were dropped from the chart).
    history, best = [], {"v": -math.inf}

    def _on_trial(study_, trial):
        if trial.value is None:
            return
        best["v"] = max(best["v"], trial.value)
        history.append({"trial": trial.number + 1, "r2": trial.value, "best": best["v"]})
        if progress_cb is not None:
            progress_cb({"history": list(history), "total": n_trials})

    callbacks = [_on_trial]

    if cancel_event is not None:
        # Optuna checks Study.stop() between trials — same once-per-trial
        # granularity as the progress callback (a trial already running still
        # finishes, but no further trials start).
        def _on_cancel(study_, trial):
            if cancel_event.is_set():
                study_.stop()

        callbacks.append(_on_cancel)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False, callbacks=callbacks)
    return {"best_params": study.best_params, "best_r2": study.best_value, "history": history}


_TREE_MODELS = {"lightgbm", "xgboost", "hist_gb", "random_forest", "extra_trees", "gradient_boosting"}


def _conformal_q(model_key: str, params: dict, X, y, groups, level: float, log_target: bool = False) -> float:
    """Split-conformal absolute-residual quantile → symmetric prediction interval
    half-width (in ft/hr). Calibration split is grouped by well when possible."""
    from sklearn.model_selection import GroupShuffleSplit
    if groups is not None and len(np.unique(groups)) >= 2:
        fit_idx, cal_idx = next(GroupShuffleSplit(1, test_size=0.3, random_state=7).split(X, y, groups))
    else:
        rng = np.random.RandomState(7)
        idx = rng.permutation(len(X))
        cut = int(len(X) * 0.7)
        fit_idx, cal_idx = idx[:cut], idx[cut:]
    m = make_model(model_key, params, log_target=log_target)
    m.fit(X[fit_idx], y[fit_idx])
    resid = np.abs(y[cal_idx] - m.predict(X[cal_idx]))
    return float(np.quantile(resid, level))


def _perm_importance(model, ds: Dataset) -> List[dict]:
    from sklearn.inspection import permutation_importance
    # n_jobs left at its default (serial), not -1: for a handful of features x 5
    # repeats the actual compute is milliseconds — n_jobs=-1 here just pays
    # joblib/loky worker-pool startup cost (measured ~50s of pure overhead on
    # Windows, nested under a model that itself already used n_jobs=-1 to fit)
    # for zero benefit at this problem size.
    r = permutation_importance(model, ds.X_test, ds.y_test, n_repeats=5, random_state=42)
    pairs = sorted(zip(ds.feature_names, r.importances_mean, r.importances_std),
                   key=lambda t: -t[1])
    return [{"feature": f, "label": feature_label(f), "importance": float(m_), "std": float(s)} for f, m_, s in pairs]


_SHAP_ROW_CAP = 2000
# random_forest/extra_trees default to UNBOUNDED tree depth (sklearn's
# max_depth=None) whenever no HPO params were applied (e.g. "Skip → Validation"
# with default params) — measured on synthetic data with that default: avg tree
# depth ~23, and SHAP TreeExplainer on just 100 rows took ~25s (vs. XGBoost/
# LightGBM/HistGB, which have optimized native SHAP paths and stayed under 1.5s
# for 500-2000 rows at 300 estimators/100 features regardless of depth — measured
# too). A 2000-row cap alone does NOT fix this: it's driven by tree depth/leaf
# count, not row count, so these two specifically get a much smaller cap.
_SHAP_ROW_CAP_SLOW = 150
_SHAP_SLOW_TREE_MODELS = {"random_forest", "extra_trees"}


def _shap_importance(model, model_key: str, ds: Dataset) -> Optional[List[dict]]:
    if model_key not in _TREE_MODELS or ds.pca is not None:
        return None
    try:
        import shap
        # Unwrap the log-target wrapper to reach the underlying tree (SHAP values are
        # then in log space, but the importance ranking is unchanged).
        est = getattr(model, "regressor_", model)
        # This pipeline deliberately never caps row counts elsewhere (a multi-well
        # test split can easily be tens of thousands of rows), but
        # TreeExplainer.shap_values() cost scales with rows × trees × depth — on an
        # uncapped X_test with a few hundred boosting rounds this can genuinely run
        # for minutes with no incremental feedback (a single blocking call), which
        # reads as "stuck" even when it isn't. Mean|SHAP| importance is a stable
        # estimate well under the full test size, so sampling down (standard SHAP
        # practice) keeps this fast without meaningfully changing the ranking.
        cap = _SHAP_ROW_CAP_SLOW if model_key in _SHAP_SLOW_TREE_MODELS else _SHAP_ROW_CAP
        X_shap = ds.X_test
        if len(X_shap) > cap:
            idx = np.random.RandomState(42).choice(len(X_shap), cap, replace=False)
            X_shap = X_shap[idx]
        vals = shap.TreeExplainer(est).shap_values(X_shap)
        mean_abs = np.abs(np.asarray(vals)).mean(axis=0)
        pairs = sorted(zip(ds.feature_names, mean_abs), key=lambda kv: -float(kv[1]))
        return [{"feature": f, "label": feature_label(f), "mean_abs_shap": float(v)} for f, v in pairs]
    except Exception:
        return None


# One representative complexity/regularization knob per model family, swept by
# _validation_curve(). Models with no single obvious knob (linear, bayesian_ridge,
# omp, mlp) are simply absent — the curve is skipped for those.
_VALIDATION_CURVE_PARAM: Dict[str, tuple] = {
    "random_forest": ("n_estimators", [50, 100, 150, 200, 300, 400]),
    "extra_trees": ("n_estimators", [50, 100, 150, 200, 300, 400]),
    "gradient_boosting": ("n_estimators", [50, 100, 150, 200, 300, 400]),
    "xgboost": ("n_estimators", [50, 100, 150, 200, 300, 400]),
    "lightgbm": ("n_estimators", [50, 100, 150, 200, 300, 400]),
    "hist_gb": ("max_iter", [50, 100, 150, 200, 300, 400]),
    "adaboost": ("n_estimators", [25, 50, 100, 150, 200, 300]),
    "knn": ("n_neighbors", [3, 5, 10, 15, 20, 30]),
    "svr": ("C", [0.1, 1.0, 10.0, 50.0, 100.0]),
    "ridge": ("alpha", [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]),
    "lasso": ("alpha", [0.001, 0.01, 0.1, 1.0, 10.0]),
    "elasticnet": ("alpha", [0.001, 0.01, 0.1, 1.0, 10.0]),
}


def _cv_for(ds: Dataset):
    """Same GroupKFold-when-enough-wells convention as optimize()/_conformal_q()."""
    from sklearn.model_selection import GroupKFold, KFold
    groups = ds.groups_train
    n_wells = len(np.unique(groups)) if groups is not None else 0
    use_groups = n_wells >= 3
    cv = GroupKFold(n_splits=min(4, n_wells)) if use_groups else KFold(n_splits=3, shuffle=True, random_state=42)
    return cv, (groups if use_groups else None)


def _learning_curve(ds: Dataset, model_key: str, params: dict) -> Optional[dict]:
    """Train/CV R² vs. training-set size — the standard over/underfitting
    diagnostic: a wide, non-closing gap between the two lines means overfitting;
    both lines converging to a low score means underfitting (more data won't help)."""
    from sklearn.model_selection import learning_curve
    cv, groups = _cv_for(ds)
    model = make_model(model_key, params or {}, log_target=ds.log_target)
    try:
        sizes, train_scores, cv_scores = learning_curve(
            model, ds.X_train, ds.y_train, groups=groups, cv=cv,
            train_sizes=np.linspace(0.2, 1.0, 5), scoring="r2", n_jobs=1,
        )
    except Exception:
        return None
    return {
        "sizes": [int(s) for s in sizes],
        "train_mean": [float(v) for v in train_scores.mean(axis=1)],
        "cv_mean": [float(v) for v in cv_scores.mean(axis=1)],
        "cv_std": [float(v) for v in cv_scores.std(axis=1)],
    }


def _validation_curve(ds: Dataset, model_key: str, params: dict) -> Optional[dict]:
    """Train/CV R² vs. one representative hyperparameter — shows over/underfitting
    as model complexity or regularization strength changes. None when the model
    has no single obvious knob (see _VALIDATION_CURVE_PARAM)."""
    spec = _VALIDATION_CURVE_PARAM.get(model_key)
    if spec is None:
        return None
    param_name, param_range = spec
    from sklearn.model_selection import validation_curve
    cv, groups = _cv_for(ds)
    base_params = {k: v for k, v in (params or {}).items() if k != param_name}
    model = make_model(model_key, base_params, log_target=ds.log_target)
    # TransformedTargetRegressor (log_target=True) nests the real estimator under
    # "regressor" — set_params() needs the qualified path in that case.
    qualified = f"regressor__{param_name}" if ds.log_target else param_name
    try:
        train_scores, cv_scores = validation_curve(
            model, ds.X_train, ds.y_train, param_name=qualified, param_range=param_range,
            groups=groups, cv=cv, scoring="r2", n_jobs=1,
        )
    except Exception:
        return None
    return {
        "param_name": param_name,
        "param_values": [float(v) for v in param_range],
        "train_mean": [float(v) for v in train_scores.mean(axis=1)],
        "cv_mean": [float(v) for v in cv_scores.mean(axis=1)],
        "cv_std": [float(v) for v in cv_scores.std(axis=1)],
    }


def fit_model_and_q(ds: Dataset, model_key: str, params: dict, pi_level: float = 0.9,
                    progress_cb=None, cancel_event=None):
    """Fits the final model once and computes its conformal-interval half-width
    once — shared by final_validation()/fit_pipeline() so the router's validation
    job doesn't fit the SAME model twice (it used to: once per function)."""
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Fitting final model…"})
    model = make_model(model_key, params or {}, log_target=ds.log_target)
    model.fit(ds.X_train, ds.y_train)
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Calibrating prediction interval…"})
    q = _conformal_q(model_key, params or {}, ds.X_train, ds.y_train, ds.groups_train, pi_level, ds.log_target)
    return model, q


def final_validation(ds: Dataset, model_key: str, params: dict, pi_level: float = 0.9,
                     model=None, q=None, progress_cb=None, cancel_event=None) -> dict:
    if model is None or q is None:
        model, q = fit_model_and_q(ds, model_key, params, pi_level, progress_cb=progress_cb, cancel_event=cancel_event)

    yp_train, yp_test = model.predict(ds.X_train), model.predict(ds.X_test)

    out: Dict[str, Any] = {
        "train": metrics(ds.y_train, yp_train),
        "test": metrics(ds.y_test, yp_test),
        "pi_level": pi_level, "pi_halfwidth": q,
        "split_grouped": ds.split_grouped, "n_invalid": ds.n_invalid,
        "n_invalid_blind": ds.n_invalid_blind, "drift": ds.drift,
    }
    # Explicit None so templates can uniformly test `coverage is not none`.
    out["train"]["coverage"] = None
    out["test"]["coverage"] = float(np.mean(np.abs(ds.y_test - yp_test) <= q) * 100)
    if ds.X_blind is not None:
        yp_b = model.predict(ds.X_blind)
        out["blind"] = metrics(ds.y_blind, yp_b)
        out["blind"]["coverage"] = float(np.mean(np.abs(ds.y_blind - yp_b) <= q) * 100)

    # Plot data for every split: predicted-vs-actual + residuals (sampled).
    def _plot_data(y_true, y_pred, cap=900):
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y_pred))[:cap]
        return {
            "scatter": [{"x": float(y_true[i]), "y": float(y_pred[i])} for i in idx],
            "residuals": [{"x": float(y_pred[i]), "y": float(y_true[i] - y_pred[i])} for i in idx],
        }

    out["plots"] = {"train": _plot_data(ds.y_train, yp_train), "test": _plot_data(ds.y_test, yp_test)}
    if ds.X_blind is not None:
        out["plots"]["blind"] = _plot_data(ds.y_blind, model.predict(ds.X_blind))

    out["error_bands"] = {"train": _error_bands(ds.y_train, yp_train), "test": _error_bands(ds.y_test, yp_test)}
    if ds.X_blind is not None:
        out["error_bands"]["blind"] = _error_bands(ds.y_blind, model.predict(ds.X_blind))

    # Back-compat keys (older saved metrics readers).
    out["scatter"] = [{"actual": p["x"], "pred": p["y"]} for p in out["plots"]["test"]["scatter"]]
    out["residuals"] = [{"pred": p["x"], "resid": p["y"]} for p in out["plots"]["test"]["residuals"]]

    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Computing permutation importance…"})
    perm = _perm_importance(model, ds)
    out["perm_importance"] = perm
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Computing SHAP values…"})
    out["shap"] = _shap_importance(model, model_key, ds)
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Computing learning curve…"})
    out["learning_curve"] = _learning_curve(ds, model_key, params or {})
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()
    if progress_cb is not None:
        progress_cb({"stage": "Computing validation curve…"})
    out["validation_curve"] = _validation_curve(ds, model_key, params or {})
    return out


# --------------------------------------------------------------------------- #
# Persistence / inference pipeline
# --------------------------------------------------------------------------- #
def fit_pipeline(ds: Dataset, model_key: str, params: dict, pi_level: float = 0.9,
                 model=None, q=None) -> dict:
    """A self-contained, picklable predictor: raw features → scaled → PCA → model,
    plus the conformal interval half-width. Saved by the experiments service."""
    if model is None or q is None:
        model, q = fit_model_and_q(ds, model_key, params, pi_level)
    from app.services.rop_prediction import feature_role
    return {
        "model": model, "scaler": ds.scaler, "pca": ds.pca,
        "raw_features": ds.raw_features, "model_key": model_key,
        "pi_halfwidth": q, "pi_level": pi_level,
        "raw_stats": ds.raw_stats or {},
        "roles": {f: feature_role(f) for f in ds.raw_features},
    }


def predict_pipeline(pipe: dict, X_raw: np.ndarray):
    """Returns (predictions, interval_halfwidth_per_row)."""
    X = np.asarray(X_raw, dtype=float)
    if pipe.get("scaler") is not None:
        X = pipe["scaler"].transform(X)
    if pipe.get("pca") is not None:
        X = pipe["pca"].transform(X)
    yp = pipe["model"].predict(X)
    q = float(pipe.get("pi_halfwidth", 0.0))
    return yp, np.full(len(yp), q)


def param_sweep(pipe: dict, base_values: dict, feature: str, lo: float, hi: float,
                n_points: int = 30, compare_feature: Optional[str] = None,
                compare_values: Optional[list] = None) -> dict:
    """Freeze every raw feature at `base_values` except `feature`, which is swept
    linearly from lo to hi, and score the grid with the already-fitted pipeline —
    no refit. Turns the model from purely predictive (score a historical row)
    into prescriptive (what WOB/RPM maximizes ROP here), the "founder point"
    diagnostic from Al Dushaishi et al. 2025 (ChemEngineering): ROP rises with
    WOB/RPM up to a threshold, then flattens or drops as the bit founders.

    With compare_feature/compare_values, one series is produced per compare
    value (that feature pinned to it instead of base_values[compare_feature]),
    so the interaction between two controllable parameters is visible as
    overlaid curves — e.g. sweep WOB at a few fixed RPM levels. Sweeping and
    comparing the SAME feature would be a no-op (the sweep value always wins
    on that column), so it's treated as "no comparison" instead of silently
    producing identical series.
    """
    feats = pipe["raw_features"]
    xs = np.linspace(float(lo), float(hi), max(2, int(n_points)))
    if compare_feature == feature:
        compare_feature = None

    def _run(overrides: dict):
        rows = [[overrides.get(f, base_values.get(f, 0.0)) if f != feature else x for f in feats] for x in xs]
        yp, half = predict_pipeline(pipe, np.array(rows, dtype=float))
        return yp, half

    if compare_feature and compare_values:
        series = []
        for cv in compare_values:
            yp, half = _run({compare_feature: cv})
            series.append({"value": float(cv), "y": yp.tolist(),
                           "y_lo": (yp - half).tolist(), "y_hi": (yp + half).tolist()})
        founder = None
    else:
        yp, half = _run({})
        series = [{"value": None, "y": yp.tolist(), "y_lo": (yp - half).tolist(), "y_hi": (yp + half).tolist()}]
        # Only call it a founder point when the peak is INTERIOR to the swept
        # range (a peak sitting at an edge just means the model would keep
        # rising past the range tested) AND is a real, finite prediction — a
        # NaN/inf value at an interior grid point would otherwise "win"
        # np.argmax (NaN is neither > nor < anything, but argmax still picks
        # its index), reporting a bogus founder point with y="nan".
        finite = np.isfinite(yp)
        founder = None
        if finite.any():
            peak_i = int(np.where(finite, yp, -np.inf).argmax())
            if 0 < peak_i < len(xs) - 1:
                founder = {"x": float(xs[peak_i]), "y": float(yp[peak_i])}

    return {"x": xs.tolist(), "series": series, "founder": founder}
