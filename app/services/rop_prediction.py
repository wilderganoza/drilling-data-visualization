"""ROP Prediction — service layer.

Trains ML models (XGBoost, LightGBM, sklearn ensembles, …) to predict rate of
penetration (ROP) from drilling parameters, pooling rows across many wells. This
module owns the data-facing helpers; the wizard/routes live in
``app/ops/web/rop_prediction.py`` and reuse the Outlier-Detection preprocessing
(scaling / PCA / anomaly removal).

Step 1 of the wizard needs, per well: how complete the model's variables are, when
drilling started and the final depth — so the user can pick wells worth training on.
Computing that means a GROUP BY over well_data (~5M rows), so the result is cached
in-process with a short TTL (same pattern as db_manager.time_well_ids()).
"""
from __future__ import annotations

import time as _time
from typing import Any, Dict, List

from sqlalchemy import text

from app.constants.parameters import get_tracked_parameters
from app.core.logging import get_logger
from app.db.session import db_manager

logger = get_logger(__name__)

# The variable the model predicts.
TARGET = "rate_of_penetration_ft_per_hr"

# Columns that ARE the target in disguise (would leak it into the features).
_LEAKAGE = {"on_bottom_rop_ft_per_hr", "time_of_penetration_min_per_ft"}

# Not literal same-row leakage (doesn't use THIS row's ROP), but close enough to
# ban outright: on_bottom_hours_hrs is a cumulative on-bottom-drilling-time
# counter, i.e. roughly cumsum(depth_increment / ROP) — a near-deterministic
# proxy for the well's entire ROP history up to that point. A model can partly
# "invert" it (or its lag/moving-avg/std variants) to recover local ROP and
# inflate R² without learning anything causal from WOB/RPM. Excluded from
# candidates entirely (like _LEAKAGE) rather than just left unchecked, so
# neither it nor its lag/ma/sd variants can be picked — including via "Select
# all". circulating_hours_hrs is a weaker version of the same pattern (doesn't
# require the bit to be advancing) and is left selectable, just not recommended.
_MONOTONIC_PROXY = {"on_bottom_hours_hrs"}

# Feature roles — informational labels only; ANY variable can be selected.
# CONTROLLABLE = parameters the driller sets. RESPONSE = consequences of drilling
# (torque, pressures, hook load) — raise R² but aren't actionable. CONTEXT =
# where/what is being drilled. Unlisted raw channels default to "response".
# (The default-checked set is RECOMMENDED_DEFAULT below, independent of role.)
CONTROLLABLE = {
    "weight_on_bit_klbs", "rotary_rpm_rpm", "motor_rpm_rpm",
    "pump_1_strokes_min_spm", "pump_2_strokes_min_spm",
    "total_pump_output_gal_per_min", "totalpumpdisplacement_barrels",
}
CONTEXT = {"bit_depth_feet", "hole_depth_feet", "block_height_feet", "bit_size"}

ROLE_LABELS = {"controllable": "Controllable", "context": "Context",
               "response": "Response", "computed": "Computed"}


def feature_role(col: str) -> str:
    from app.services.rop_features import ENG_ROLE
    if col in ENG_ROLE:
        return ENG_ROLE[col]
    if col in CONTROLLABLE:
        return "controllable"
    if col in CONTEXT:
        return "context"
    return "response"


def raw_candidates() -> List[str]:
    """Raw sensor channels offered as predictors (target, leakage, and the
    on_bottom_hours ROP-history proxy removed — see _LEAKAGE/_MONOTONIC_PROXY)."""
    return [p for p in get_tracked_parameters()
            if p != TARGET and p not in _LEAKAGE and p not in _MONOTONIC_PROXY]


def feature_candidates() -> List[str]:
    """Raw channels + the engineered features derivable from them."""
    from app.services.rop_features import available_engineered
    raw = raw_candidates()
    eng = available_engineered(get_tracked_parameters())
    return raw + eng


def feature_label(col: str) -> str:
    from app.services.rop_features import ENG_LABEL
    if col in ENG_LABEL:
        return ENG_LABEL[col]
    try:
        from app.services.exports import _get_label
        return _get_label(col)
    except Exception:
        return col.replace("_", " ").title()


# Default-recommended = exactly the variables from the field team's requested list
# that we actually have (raw) or can compute (engineered), plus one lagged response
# variable (see below). Everything else is still selectable, just not pre-checked.
#
# RAW response variables are never recommended by default: they're consequences of
# drilling (torque, pressures, hook load), not driller-set controls, so predicting
# from them raw breaks the controllable->ROP counterfactual an optimizer needs (it
# can't supply a future response value as an input to search over). A LAGGED
# response variable is different — it's already-observed history at decision time,
# not a real-time reading, so it's safe for the optimization use case. That's the
# criterion: differential_pressure_psi_lag20 (the response to WOB/torque with a
# downhole motor) is recommended lagged; its raw/unlagged form is not, and is left
# selectable-but-unchecked along with every other lag/response combination — see
# rop_features.py's _LAG_CANDIDATES for the full generated set.
#
# bit_rpm_total is also deliberately left out here (still selectable, just not
# pre-checked): bit_rpm_total = rotary_rpm + gpm*rev/gal, i.e. perfect
# collinearity with two already-recommended variables (keep rotary/gpm free, let
# the model imply bit RPM). on_bottom_hours_hrs isn't in this set for a
# different reason — it isn't a candidate at all anymore, see _MONOTONIC_PROXY.
RECOMMENDED_DEFAULT = {
    # raw, available
    "weight_on_bit_klbs", "rotary_rpm_rpm", "total_pump_output_gal_per_min",
    "hole_depth_feet", "bit_size",
    # engineered, computable from what we have
    "cum_work", "wob_ma20", "rpm_ma20", "gpm_ma20",
    "wob_sd20", "rpm_sd20", "gpm_sd20", "sliding_frac",
    # lagged response — see comment above
    "differential_pressure_psi_lag20",
}


def is_recommended(col: str) -> bool:
    return col in RECOMMENDED_DEFAULT


# Physically plausible ranges per channel — the data-quality gate drops rows with
# any selected feature (or the target) outside these. Channels without an entry are
# left unbounded.
PLAUSIBLE_RANGES = {
    "rate_of_penetration_ft_per_hr": (0.0, 1000.0),
    "weight_on_bit_klbs": (0.0, 120.0),
    "rotary_rpm_rpm": (0.0, 350.0),
    "motor_rpm_rpm": (0.0, 500.0),
    "total_pump_output_gal_per_min": (0.0, 1500.0),
    "totalpumpdisplacement_barrels": (0.0, 1e6),
    "standpipe_pressure_psi": (0.0, 8000.0),
    "differential_pressure_psi": (0.0, 3000.0),
    "hook_load_klbs": (0.0, 700.0),
    "over_pull_klbs": (0.0, 300.0),
    "bit_depth_feet": (0.0, 40000.0),
    "hole_depth_feet": (0.0, 40000.0),
    "block_height_feet": (0.0, 200.0),
    "trip_speed_ft_per_min": (0.0, 600.0),
    "pump_1_strokes_min_spm": (0.0, 250.0),
    "pump_2_strokes_min_spm": (0.0, 250.0),
    "bit_size": (3.0, 40.0),
}


# 0 means "no reading" for these sensors, so completeness counts non-null AND non-zero
# (same convention as the Outliers module).
def _present_sql(col: str) -> str:
    return f'count(*) FILTER (WHERE "{col}" IS NOT NULL AND "{col}" <> 0)'


_CACHE: Dict[str, Any] = {"data": None, "at": 0.0}
_BIT_SIZE_CACHE: Dict[str, Any] = {"data": None, "at": 0.0}


def bit_size_options(ttl: float = 300.0) -> List[float]:
    """Distinct bit diameters present across all well data, for the wizard's
    bit-diameter filter (Step 1). Cached — the set of drilled bit sizes changes
    rarely, and this is a DISTINCT scan over a multi-million-row table."""
    now = _time.monotonic()
    if _BIT_SIZE_CACHE["data"] is not None and (now - _BIT_SIZE_CACHE["at"]) < ttl:
        return _BIT_SIZE_CACHE["data"]
    sql = text('SELECT DISTINCT "bit_size" FROM well_data WHERE "bit_size" IS NOT NULL AND "bit_size" > 0 ORDER BY "bit_size"')
    try:
        with db_manager._engine.connect() as cx:
            out = [float(r[0]) for r in cx.execute(sql)]
    except Exception:
        logger.exception("bit_size_options() query failed")
        return _BIT_SIZE_CACHE["data"] or []
    _BIT_SIZE_CACHE["data"] = out
    _BIT_SIZE_CACHE["at"] = now
    return out


def well_summaries(ttl: float = 300.0, depth_range=None, date_range=None, bit_sizes=None) -> Dict[int, Dict[str, Any]]:
    """Per-well {n_rows, start_date, final_depth, target_completeness,
    feature_completeness} keyed by well_id. Cached for ``ttl`` seconds — but only
    the unfiltered result is cacheable; a depth/date/bit-size filter bypasses the
    cache (single grouped-aggregate query, cheap enough to run live per keystroke)."""
    live_filter = depth_range is not None or date_range is not None or bool(bit_sizes)
    if not live_filter:
        now = _time.monotonic()
        if _CACHE["data"] is not None and (now - _CACHE["at"]) < ttl:
            return _CACHE["data"]

    # Only RAW sensor columns exist in well_data — engineered features are derived
    # later in pandas, so the completeness SQL must use raw_candidates(), not
    # feature_candidates() (which also lists engineered names that aren't columns).
    feats = raw_candidates()
    feat_present = " + ".join(_present_sql(c) for c in feats) or "0"

    where, params = [], {}
    if depth_range is not None:
        lo, hi = depth_range
        if lo is not None:
            where.append('COALESCE("bit_depth_feet", "hole_depth_feet") >= :depth_lo')
            params["depth_lo"] = lo
        if hi is not None:
            where.append('COALESCE("bit_depth_feet", "hole_depth_feet") <= :depth_hi')
            params["depth_hi"] = hi
    if date_range is not None:
        yr_lo, yr_hi = date_range
        if yr_lo is not None:
            where.append('"yyyy_mm_dd" >= :date_lo')
            params["date_lo"] = "%04d/01/01" % yr_lo
        if yr_hi is not None:
            where.append('"yyyy_mm_dd" <= :date_hi')
            params["date_hi"] = "%04d/12/31" % yr_hi
    if bit_sizes:
        where.append('"bit_size" = ANY(:bit_sizes)')
        params["bit_sizes"] = list(bit_sizes)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = text(
        f"""
        SELECT well_id,
               count(*)                                           AS n,
               min(yyyy_mm_dd)                                    AS start_date,
               min(COALESCE(hole_depth_feet, bit_depth_feet))     AS start_depth,
               max(COALESCE(hole_depth_feet, bit_depth_feet))     AS final_depth,
               {_present_sql(TARGET)}                             AS target_present,
               ({feat_present})                                   AS feat_present_sum
        FROM well_data
        {where_sql}
        GROUP BY well_id
        """
    )
    n_feats = max(1, len(feats))
    out: Dict[int, Dict[str, Any]] = {}
    try:
        with db_manager._engine.connect() as cx:
            for row in cx.execute(sql, params):
                n = row.n or 0
                out[row.well_id] = {
                    "n_rows": n,
                    "start_date": row.start_date,
                    "start_depth": float(row.start_depth) if row.start_depth is not None else None,
                    "final_depth": float(row.final_depth) if row.final_depth is not None else None,
                    "target_completeness": (row.target_present / n * 100.0) if n else 0.0,
                    "feature_completeness": (row.feat_present_sum / (n * n_feats) * 100.0) if n else 0.0,
                }
    except Exception:
        logger.exception("well_summaries() query failed (depth_range=%s date_range=%s); falling back to cache",
                         depth_range, date_range)
        return _CACHE["data"] or {}

    if not live_filter:
        _CACHE["data"] = out
        _CACHE["at"] = now
    return out
