"""Data Cleaning submodule — self-contained statistical outlier detection over
the OPERATIONAL drilling-parameter record (the ops_drill_params grid rows that
live under each daily report).

This is deliberately independent of the legacy high-frequency sensor pipeline
(/wells, LAS/CSV, the `well_data` table): it runs immediately on whatever
operational drilling parameters have been captured, using plain-Python
statistics (no numpy/pandas). Two complementary flag methods are combined:

  * Z-score:  |(x - mean) / std| > 3
  * IQR:      x < Q1 - 1.5·IQR  or  x > Q3 + 1.5·IQR

A point is an outlier if EITHER method flags it; the method(s) that fired are
recorded per point.
"""
from statistics import mean as _mean, median as _median, pstdev as _pstdev

# Parameters we screen, in display order.
PARAMS = ["rop", "mse_ksi", "wob", "spp_psi", "torque_ftlb"]

# Preference order for which parameter drives the chart (most-populated wins,
# ties broken toward the front of this list).
_CHART_PREF = ["rop", "mse_ksi", "wob", "spp_psi", "torque_ftlb"]

Z_THRESH = 3.0
IQR_K = 1.5
MIN_N = 5
OUTLIER_CAP = 200


def _quartiles(sorted_vals):
    """Q1 and Q3 via linear interpolation on the sorted list (Tukey-ish,
    inclusive median method — good enough for outlier fences)."""
    n = len(sorted_vals)

    def _percentile(p):
        if n == 1:
            return sorted_vals[0]
        rank = p * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

    return _percentile(0.25), _percentile(0.75)


def _collect(db):
    """Pull every operational drilling-parameter reading across all wells.

    Returns a list of dicts: {well, depth_md, rop, mse_ksi, wob, rpm,
    spp_psi, torque_ftlb} with Numeric columns coerced to float (or None)."""
    from sqlalchemy import select

    from app.models.capture import CONFIG_BY_KEY
    from app.models.hierarchy import Event, Well, Wellbore
    from app.repositories.capture_repository import GridRepository
    from app.repositories.daily_report_repository import DailyReportRepository

    model = CONFIG_BY_KEY["drill-params"].model
    report_repo = DailyReportRepository(db)

    def _f(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    points = []
    for ev in db.execute(select(Event)).scalars().all():
        wb = db.get(Wellbore, ev.wellbore_id)
        well = db.get(Well, wb.well_id) if wb else None
        well_label = (well.legal_well_name if well and well.legal_well_name else "—")
        for report in report_repo.list_for_event(ev.id):
            rows = GridRepository(db, model, parent_field="daily_report_id").list_for_parent(report.id)
            for r in rows:
                points.append({
                    "well": well_label,
                    "depth_md": _f(getattr(r, "depth_md", None)),
                    "rop": _f(getattr(r, "rop", None)),
                    "mse_ksi": _f(getattr(r, "mse_ksi", None)),
                    "wob": _f(getattr(r, "wob", None)),
                    "rpm": _f(getattr(r, "rpm", None)),
                    "spp_psi": _f(getattr(r, "spp_psi", None)),
                    "torque_ftlb": _f(getattr(r, "torque_ftlb", None)),
                })
    return points


def analyze(db, **kwargs) -> dict:
    points = _collect(db)

    empty = {
        "params_stats": [],
        "outliers": [],
        "total_points": 0,
        "total_outliers": 0,
        "pct_outliers": 0.0,
        "series_by_param": {},
        "has_data": False,
    }
    if not points:
        return empty

    params_stats = []
    outliers = []
    # Per-parameter outlier bookkeeping so we can build the chart series with the
    # outlier flag already resolved.
    flags_by_param = {}   # param -> list of (point_index, is_outlier)
    counts_by_param = {}  # param -> non-null count

    for param in PARAMS:
        vals = [(i, p[param]) for i, p in enumerate(points) if p.get(param) is not None]
        counts_by_param[param] = len(vals)
        if len(vals) < MIN_N:
            continue

        xs = [v for _, v in vals]
        m = _mean(xs)
        sd = _pstdev(xs)  # population std; robust to n and never raises on n>=1
        med = _median(xs)
        q1, q3 = _quartiles(sorted(xs))
        iqr = q3 - q1
        lo_fence = q1 - IQR_K * iqr
        hi_fence = q3 + IQR_K * iqr

        param_flags = []
        n_out = 0
        for idx, x in vals:
            z = (x - m) / sd if sd > 0 else 0.0
            by_z = sd > 0 and abs(z) > Z_THRESH
            by_iqr = iqr > 0 and (x < lo_fence or x > hi_fence)
            is_out = by_z or by_iqr
            param_flags.append((idx, is_out))
            if is_out:
                n_out += 1
                if by_z and by_iqr:
                    method = "z+iqr"
                elif by_z:
                    method = "z"
                else:
                    method = "iqr"
                outliers.append({
                    "well": points[idx]["well"],
                    "depth_md": points[idx].get("depth_md"),
                    "param": param,
                    "value": round(x, 3),
                    "z": round(z, 2),
                    "method": method,
                })

        flags_by_param[param] = param_flags
        n = len(xs)
        params_stats.append({
            "param": param,
            "n": n,
            "mean": round(m, 3),
            "std": round(sd, 3),
            "median": round(med, 3),
            "q1": round(q1, 3),
            "q3": round(q3, 3),
            "n_outliers": n_out,
            "pct_outliers": round(100.0 * n_out / n, 1) if n else 0.0,
        })

    total_points = sum(s["n"] for s in params_stats)
    total_outliers = sum(s["n_outliers"] for s in params_stats)
    pct_outliers = round(100.0 * total_outliers / total_points, 1) if total_points else 0.0

    # Sort outliers most-extreme first, then cap for display.
    outliers.sort(key=lambda o: abs(o["z"]), reverse=True)
    outliers = outliers[:OUTLIER_CAP]

    # Chart series: the most-populated analysed parameter (ties -> _CHART_PREF).
    series_by_param = {}
    analysed = [s["param"] for s in params_stats]
    if analysed:
        chart_param = max(
            analysed,
            key=lambda p: (counts_by_param.get(p, 0), -_CHART_PREF.index(p) if p in _CHART_PREF else 0),
        )
        flag_map = dict(flags_by_param.get(chart_param, []))
        series = []
        i = 0
        for idx, p in enumerate(points):
            v = p.get(chart_param)
            if v is None:
                continue
            series.append({"i": i, "value": round(v, 3), "outlier": bool(flag_map.get(idx, False))})
            i += 1
        series_by_param[chart_param] = series

    return {
        "params_stats": params_stats,
        "outliers": outliers,
        "total_points": total_points,
        "total_outliers": total_outliers,
        "pct_outliers": pct_outliers,
        "series_by_param": series_by_param,
        "has_data": True,
    }
