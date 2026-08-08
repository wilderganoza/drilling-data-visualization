"""Directional-survey math: derive TVD, N/S, E/W and DLS from the measured
MD / Inclination / Azimuth of each station using the industry-standard
minimum-curvature method. These four columns are computed, never entered by
hand — the capture engine recomputes them whenever a station is added, edited
or removed.

Surveys are stored per daily report, but a wellbore's trajectory is continuous
across days, so recompute accepts a `tie_in` (the deepest station from earlier
reports of the same event) to keep TVD/displacement cumulative rather than
resetting to zero each day."""
import math


def recompute_survey(rows, tie_in=None) -> None:
    """Fill tvd/ns/ew/dls on each station row in `rows` (ORM objects), in place.

    Stations are processed in MD order. Rows missing MD/Inc/Azi are left
    untouched and don't advance the reference point. `tie_in`, if given, is an
    object exposing md/inclination/azimuth/tvd/ns/ew used as the station above
    the first one here (continuity across daily reports)."""
    stations = [r for r in rows if r.md is not None and r.inclination is not None and r.azimuth is not None]
    stations.sort(key=lambda r: float(r.md))

    prev = tie_in
    for r in stations:
        md, inc, azi = float(r.md), float(r.inclination), float(r.azimuth)
        if prev is None:
            # First station in the whole well: treat as the tie-on point,
            # vertical above it (TVD = MD, no horizontal displacement).
            r.tvd, r.ns, r.ew, r.dls = round(md, 3), 0.0, 0.0, 0.0
            prev = r
            continue

        md1 = float(prev.md)
        dmd = md - md1
        if dmd <= 0:
            # Duplicate / out-of-order MD — carry the previous position, no leg.
            r.tvd = float(prev.tvd) if prev.tvd is not None else round(md, 3)
            r.ns = float(prev.ns) if prev.ns is not None else 0.0
            r.ew = float(prev.ew) if prev.ew is not None else 0.0
            r.dls = 0.0
            prev = r
            continue

        i1, a1 = math.radians(float(prev.inclination)), math.radians(float(prev.azimuth))
        i2, a2 = math.radians(inc), math.radians(azi)

        cos_beta = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1 - math.cos(a2 - a1))
        cos_beta = max(-1.0, min(1.0, cos_beta))
        beta = math.acos(cos_beta)                      # dogleg angle (rad)
        rf = 1.0 if beta < 1e-9 else (2.0 / beta) * math.tan(beta / 2.0)  # ratio factor

        d_tvd = dmd / 2.0 * (math.cos(i1) + math.cos(i2)) * rf
        d_ns = dmd / 2.0 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf
        d_ew = dmd / 2.0 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf

        base_tvd = float(prev.tvd) if prev.tvd is not None else md1
        base_ns = float(prev.ns) if prev.ns is not None else 0.0
        base_ew = float(prev.ew) if prev.ew is not None else 0.0

        r.tvd = round(base_tvd + d_tvd, 3)
        r.ns = round(base_ns + d_ns, 3)
        r.ew = round(base_ew + d_ew, 3)
        r.dls = round(math.degrees(beta) * (100.0 / dmd), 3)  # deg / 100 ft
        prev = r
