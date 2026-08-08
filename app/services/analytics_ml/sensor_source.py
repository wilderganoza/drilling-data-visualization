"""Bridge the ops Analytics to the REAL sensor record.

An ops Event → Wellbore → ops Well may carry a `legacy_well_id` (the unified
legacy sensor well). When it does, we can feed ROP / dysfunction analytics the
actual high-frequency `well_data` (depth-indexed) or `well_data_time` (time-
indexed) instead of the manually-captured `drill-params` grid.

Honest data note: the sensor channel set has ROP, WOB, RPM, SPP, flow, depth and
differential pressure — but NO surface torque, bit size or formation. So MSE
(needs torque + bit diameter) is NOT computed from sensor data; founder analysis
falls back to the ROP-vs-WOB response, which is a valid method on its own.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# well_data column → standard drilling-point key
_CHANNELS = {
    "depth_md": "bit_depth_feet",
    "rop": "rate_of_penetration_ft_per_hr",
    "wob": "weight_on_bit_klbs",
    "rpm": "rotary_rpm_rpm",
    "flow_gpm": "total_pump_output_gal_per_min",
    "spp_psi": "standpipe_pressure_psi",
    "diff_psi": "differential_pressure_psi",
}


def legacy_well_id(db: Session, event_id: str) -> Optional[int]:
    """event → wellbore → ops well → legacy_well_id (or None)."""
    row = db.execute(text(
        "SELECT w.legacy_well_id FROM ops_events e "
        "JOIN ops_wellbores wb ON wb.id = e.wellbore_id "
        "JOIN ops_wells w ON w.id = wb.well_id "
        "WHERE e.id = :eid"
    ), {"eid": event_id}).fetchone()
    return row[0] if row and row[0] is not None else None


def has_sensor_data(db: Session, event_id: str, domain: str = "depth") -> bool:
    lw = legacy_well_id(db, event_id)
    if lw is None:
        return False
    table = "well_data_time" if domain == "time" else "well_data"
    try:
        return db.execute(text(f"SELECT 1 FROM {table} WHERE well_id=:w LIMIT 1"), {"w": lw}).fetchone() is not None
    except Exception:
        return False


def drilling_points(db: Session, event_id: str, domain: str = "depth", max_points: int = 4000) -> dict:
    """Real drilling points for the well behind an event, from the sensor record.
    Returns {source, domain, well_id, n, points:[...]} — source is
    'sensor-depth'/'sensor-time' or 'none'. Points use the standard keys
    (torque_ftlb / mse_ksi / bit_size / formation are None — not in the channels)."""
    lw = legacy_well_id(db, event_id)
    if lw is None:
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": None}
    table = "well_data_time" if domain == "time" else "well_data"

    try:
        n = db.execute(text(f"SELECT count(*) FROM {table} WHERE well_id=:w"), {"w": lw}).scalar() or 0
    except Exception:
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": lw}
    if n == 0:
        return {"source": "none", "points": [], "n": 0, "domain": domain, "well_id": lw}

    # downsample large series with a modulo stride on the primary key
    stride = max(1, n // max_points)
    sel = ", ".join(f"{col} AS {key}" for key, col in _CHANNELS.items())
    rows = db.execute(text(
        f"SELECT {sel} FROM {table} WHERE well_id=:w AND (id % :s)=0 ORDER BY id LIMIT :lim"
    ), {"w": lw, "s": stride, "lim": max_points}).mappings().all()

    # Keep only ON-BOTTOM drilling samples (real ROP and WOB), then aggregate the
    # high-frequency stream into depth bins so the analytics see clean interval-
    # level points (like the manual grid) instead of noisy 10-second samples.
    raw = []
    for r in rows:
        rop, wob, depth = _f(r["rop"]), _f(r["wob"]), _f(r["depth_md"])
        if rop is None or rop <= 0 or wob is None or wob <= 0 or depth is None:
            continue
        raw.append((depth, rop, wob, _f(r["rpm"]), _f(r["flow_gpm"]), _f(r["spp_psi"]), _f(r["diff_psi"])))

    BIN = 30.0  # ft
    bins: dict = {}
    for depth, rop, wob, rpm, flow, spp, diff in raw:
        bins.setdefault(round(depth / BIN) * BIN, []).append((rop, wob, rpm, flow, spp, diff))

    def _avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    points = []
    for depth in sorted(bins):
        b = bins[depth]
        points.append({
            "depth_md": depth,
            "rop": _avg([x[0] for x in b]), "wob": _avg([x[1] for x in b]),
            "rpm": _avg([x[2] for x in b]), "flow_gpm": _avg([x[3] for x in b]),
            "spp_psi": _avg([x[4] for x in b]), "diff_psi": _avg([x[5] for x in b]),
            "torque_ftlb": None, "mse_ksi": None, "bit_size": None, "formation": None,
        })
    return {"source": f"sensor-{domain}", "points": points, "n": len(points),
            "domain": domain, "well_id": lw, "raw_samples": len(raw)}


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
