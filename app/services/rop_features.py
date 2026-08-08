"""ROP Prediction — engineered features.

Derives extra predictors from the raw sensor channels we actually have (WOB,
surface RPM, motor RPM, flow, differential pressure, depth). Everything here is
computable from those columns; features that would need channels we DON'T have
(torque → MSE; bit diameter → WOB/dia, d-exponent, HSI, jet impact; mud weight /
pore pressure → overbalance; formation / TVD / survey → distance-to-top, etc.) are
intentionally omitted.

`engineer(df)` takes one WELL's rows (any order), sorts by depth, and appends the
engineered columns. Rolling windows are in rows, which on this ~1 ft-spaced uniform
grid equal feet — a "20 ft window" is `rolling(20)`.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from app.services.exports import _get_label
from app.services.rop_prediction import CONTEXT, PLAUSIBLE_RANGES, raw_candidates

# Rolling-window sizes (rows ≈ ft on this uniform grid) shared by the moving
# avg/std families below.
_WINDOWS = (5, 20, 50)

# Every raw channel the driller sets (controllable) or that the formation/bit
# produces as a consequence of drilling (response) gets a lagged version at each
# window depth below — see the lag block appended to ENGINEERED further down.
# CONTEXT (depth/bit size/block height) is excluded: it's where/what is being
# drilled, not a signal worth lagging.
_LAG_CANDIDATES = [c for c in raw_candidates() if c not in CONTEXT]

# Engineered feature spec. role: "controllable" (a real set-point derived from
# set-points) or "computed" (a derived indicator).
ENGINEERED = [
    {"key": "bit_rpm_total", "label": "Bit RPM (rotary + motor)", "role": "controllable",
     "deps": ["rotary_rpm_rpm", "motor_rpm_rpm"]},
    {"key": "wob_rpm", "label": "WOB × bit RPM (work rate)", "role": "computed",
     "deps": ["weight_on_bit_klbs", "rotary_rpm_rpm", "motor_rpm_rpm"]},
    {"key": "cum_work", "label": "Cumulative work ∫WOB·RPM d(depth)", "role": "computed",
     "deps": ["weight_on_bit_klbs", "rotary_rpm_rpm", "motor_rpm_rpm"]},
    {"key": "sliding_frac", "label": "Sliding fraction (~20 ft)", "role": "computed", "deps": ["rotary_rpm_rpm"]},
    {"key": "wob_slope20", "label": "WOB slope (20 ft)", "role": "computed", "deps": ["weight_on_bit_klbs"]},
    {"key": "rpm_slope20", "label": "Surface RPM slope (20 ft)", "role": "computed", "deps": ["rotary_rpm_rpm"]},
]
# Legacy short names for the original 3 pilot variables — kept as-is (not renamed
# to the generic {col}_ma{w}/{col}_sd{w} scheme below) so already-saved
# experiments/datasets that reference "wob_ma20" etc. keep resolving to the same
# feature.
_MA_SHORT_NAME = {
    "weight_on_bit_klbs": "wob",
    "rotary_rpm_rpm": "rpm",
    "total_pump_output_gal_per_min": "gpm",
}

# Lag (the value exactly N ft back), moving average and moving std — three
# distinct signals, generated for EVERY controllable/response channel (see
# _LAG_CANDIDATES above), at every window depth, so no variable is arbitrarily
# missing one of the three the way only WOB/RPM/Flow used to get avg+std while
# everything else only got lag. Lag captures delayed system response (ROP now
# reacting to a change from a few feet back) rather than a smoothed trailing
# level or its local variability — a response variable lagged/averaged is
# already-observed history, not a real-time reading, so it doesn't break the
# controllable->ROP counterfactual the way using it raw/unlagged would.
# Deliberately NOT lagging/averaging the target itself (would just teach the
# model "ROP ~ ROP nearby" via spatial autocorrelation, inflating R² while
# making it useless for controllable-parameter optimization).
for _col in _LAG_CANDIDATES:
    _base_label = _get_label(_col)
    _prefix = _MA_SHORT_NAME.get(_col, _col)
    for _w in _WINDOWS:
        ENGINEERED.append({
            "key": f"{_col}_lag{_w}", "label": f"{_base_label} lag ({_w} ft back)",
            "role": "computed", "deps": [_col],
        })
        ENGINEERED.append({
            "key": f"{_prefix}_ma{_w}", "label": f"{_base_label} moving avg ({_w} ft)",
            "role": "computed", "deps": [_col],
        })
        ENGINEERED.append({
            "key": f"{_prefix}_sd{_w}", "label": f"{_base_label} moving std ({_w} ft)",
            "role": "computed", "deps": [_col],
        })
ENG_KEYS = [e["key"] for e in ENGINEERED]
ENG_ROLE = {e["key"]: e["role"] for e in ENGINEERED}
ENG_LABEL = {e["key"]: e["label"] for e in ENGINEERED}
_ENG_DEPS = {e["key"]: e["deps"] for e in ENGINEERED}

_WINDOW = 20  # rows ≈ ft — default window used by sliding_frac / slopes


def available_engineered(existing_cols) -> List[str]:
    cols = set(existing_cols)
    return [k for k, deps in _ENG_DEPS.items() if all(d in cols for d in deps)]


def _depth_col(df: pd.DataFrame):
    for c in ("bit_depth_feet", "hole_depth_feet"):
        if c in df.columns:
            return c
    return None


def _plausible(s: pd.Series, col: str) -> pd.Series:
    """Masks values outside PLAUSIBLE_RANGES[col] as NaN before they feed into any
    rolling/lag/cumulative feature below — a single sensor glitch (e.g. a bogus
    WOB=99999 reading) would otherwise corrupt every moving-avg/std/lag value in
    the surrounding window, and permanently poison cum_work's running total (a
    cumsum never "forgets" a bad value). The RAW column returned in the frame is
    left untouched — rop_ml._rows() still applies its own plausible-range gate
    (and n_invalid count) on whichever raw/engineered columns end up selected."""
    r = PLAUSIBLE_RANGES.get(col)
    if r is None:
        return s
    lo, hi = r
    return s.where((s >= lo) & (s <= hi))


def _rolling_slope(s: pd.Series, window: int) -> pd.Series:
    """Rolling least-squares slope of `s` against its row position (≈ ft)."""
    def _slope(arr: np.ndarray) -> float:
        n = len(arr)
        if n < 2:
            return 0.0
        x = np.arange(n, dtype=float)
        x_mean = x.mean()
        denom = ((x - x_mean) ** 2).sum()
        if denom == 0:
            return 0.0
        y_mean = arr.mean()
        return float(((x - x_mean) * (arr - y_mean)).sum() / denom)
    return s.rolling(window, min_periods=2).apply(_slope, raw=True).fillna(0.0)


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Append engineered columns to one well's frame (raw sensor channels)."""
    if df is None or df.empty:
        return df
    dcol = _depth_col(df)
    if dcol is not None:
        # Coerce depth to numeric first — a stray None/text row would otherwise make
        # the column object-dtype and break diff()/sort.
        df = df.copy()
        df[dcol] = pd.to_numeric(df[dcol], errors="coerce")
        df = df.sort_values(dcol).reset_index(drop=True)

    r = pd.to_numeric(df["rotary_rpm_rpm"], errors="coerce") if "rotary_rpm_rpm" in df else None
    m = pd.to_numeric(df["motor_rpm_rpm"], errors="coerce") if "motor_rpm_rpm" in df else None
    wob = pd.to_numeric(df["weight_on_bit_klbs"], errors="coerce") if "weight_on_bit_klbs" in df else None
    gpm = pd.to_numeric(df["total_pump_output_gal_per_min"], errors="coerce") if "total_pump_output_gal_per_min" in df else None
    if r is not None:
        r = _plausible(r, "rotary_rpm_rpm")
    if m is not None:
        m = _plausible(m, "motor_rpm_rpm")
    if wob is not None:
        wob = _plausible(wob, "weight_on_bit_klbs")
    if gpm is not None:
        gpm = _plausible(gpm, "total_pump_output_gal_per_min")

    if r is not None and m is not None:
        df["bit_rpm_total"] = r.fillna(0) + m.fillna(0)
    if wob is not None and "bit_rpm_total" in df:
        df["wob_rpm"] = wob.fillna(0) * df["bit_rpm_total"]
        if dcol is not None:
            dd = df[dcol].diff().fillna(0).clip(lower=0)
            df["cum_work"] = (df["wob_rpm"] * dd).cumsum()
    if r is not None:
        df["sliding_frac"] = (r < 5).astype(float).rolling(_WINDOW, min_periods=1).mean()
    if wob is not None:
        df["wob_slope20"] = _rolling_slope(wob, _WINDOW)
    if r is not None:
        df["rpm_slope20"] = _rolling_slope(r, _WINDOW)

    # Lag + moving avg + moving std for every controllable/response channel
    # actually present, at every window depth — see ENGINEERED's comment above
    # for why all three are generated for every channel alike. Built as a dict
    # and concatenated once (~200 columns now, up from ~90) instead of assigning
    # one column at a time, which pandas fragments badly at this width.
    new_cols = {}
    for col in _LAG_CANDIDATES:
        if col not in df.columns:
            continue
        s = _plausible(pd.to_numeric(df[col], errors="coerce"), col)
        prefix = _MA_SHORT_NAME.get(col, col)
        for w in _WINDOWS:
            new_cols[f"{col}_lag{w}"] = s.shift(w)
            new_cols[f"{prefix}_ma{w}"] = s.rolling(w, min_periods=1).mean()
            new_cols[f"{prefix}_sd{w}"] = s.rolling(w, min_periods=1).std().fillna(0.0)
    if new_cols:
        df = pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)
    return df
