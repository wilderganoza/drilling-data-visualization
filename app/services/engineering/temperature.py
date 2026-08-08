"""Temperature profile — static geothermal and circulating temperatures.

Static (geothermal) profile:
  BHST(tvd) = surface_temp + geo_grad·tvd/100          (gradient in °F/100ft)
If a measured temperature profile is available on the geopressure grid it is
preferred, and an effective gradient is back-calculated from surface to TD.

Circulating (bottom-hole circulating temperature, BHCT) uses a simplified,
widely used API RP 10B-2 style chart approximation:
  BHCT ≈ surface_temp + (BHST − surface_temp)·f
with the fraction f falling with depth. This is a static-chart correlation, NOT
a transient wellbore thermal simulation — it is intended for cement slurry
thickening-time design and downhole-tool temperature ratings only."""
from dataclasses import dataclass

from app.services.engineering.context import WellContext


@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


INPUTS = [
    Inp("surface_temp", "Surface/seabed temp", 60, "°F"),
    Inp("geo_grad", "Geothermal gradient", 1.1, "°F/100ft"),
    Inp("flow", "Circulation rate", 600, "gpm"),
    Inp("inlet_temp", "Mud inlet temp", 110, "°F"),
    Inp("circ_hours", "Circulation time", 4, "hr"),
    Inp("mw", "Mud weight", 9.9, "ppg"),
]


def context_defaults(ctx: WellContext) -> dict:
    """Seed the surface temperature from the shallowest measured temp point on
    the geopressure grid so the profile ties to the well's own data."""
    out: dict = {}
    if not ctx.has_geopressure() or not ctx.geopressure:
        return out
    pts = [g for g in ctx.geopressure if g.get("temp_f") is not None and g.get("tvd") is not None]
    if not pts:
        return out
    shallow = min(pts, key=lambda g: g["tvd"])
    out["surface_temp"] = round(float(shallow["temp_f"]), 1)
    return out


def compute(params: dict, ctx: WellContext) -> dict:
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    surface_temp = p["surface_temp"]
    inlet_temp = p["inlet_temp"]
    td_tvd = ctx.td_tvd() or (ctx.td() or 10000)
    td_md = ctx.td() or td_tvd

    # --- static / geothermal profile ---
    # Prefer a measured temperature profile from the geopressure grid; fall back
    # to the input geothermal gradient.
    uses_measured = False
    measured_bottom = ctx.temp_at(td_tvd) if ctx.has_geopressure() else None
    if measured_bottom is not None:
        uses_measured = True
        bhst = float(measured_bottom)
        geo_grad_eff = (bhst - surface_temp) / (td_tvd / 100) if td_tvd else p["geo_grad"]
    else:
        geo_grad_eff = p["geo_grad"]
        bhst = surface_temp + geo_grad_eff * td_tvd / 100

    def static_at(tvd: float) -> float:
        if uses_measured:
            m = ctx.temp_at(tvd)
            if m is not None:
                return float(m)
        return surface_temp + geo_grad_eff * tvd / 100

    # --- bottom-hole circulating temperature (BHCT) ---
    # Simplified published-chart approximation: BHCT is a depth-decreasing
    # fraction of the static bottom-hole temperature above surface.
    f = 0.97 - 0.0000265 * td_tvd
    f = max(0.5, min(0.97, f))
    bhct_base = surface_temp + (bhst - surface_temp) * f
    # Small correction for mud inlet temperature and circulation time (minor).
    bhct = bhct_base + (inlet_temp - bhct_base) * max(0.0, 0.15 - 0.02 * p["circ_hours"])

    # --- profiles at ~10 stations from surface to TD ---
    profile = []
    stations = 10
    for i in range(stations + 1):
        frac = i / stations
        tvd = td_tvd * frac
        md = td_md * frac
        # circulating: curved gradient from inlet at surface to BHCT at TD
        circ = inlet_temp + (bhct - inlet_temp) * (tvd / td_tvd) ** 1.5 if td_tvd else inlet_temp
        profile.append({
            "tvd": round(tvd),
            "md": round(md),
            "static": round(static_at(tvd), 1),
            "circulating": round(circ, 1),
        })

    tool_rating_note = (
        "Rate tools/electronics for BHST %.0f°F static; BHCT %.0f°F governs cement "
        "slurry thickening-time." % (bhst, bhct)
    )

    return {
        "bhst": round(bhst, 1),
        "bhct": round(bhct, 1),
        "geo_grad_eff": round(geo_grad_eff, 3),
        "surface_temp": round(surface_temp, 1),
        "td_tvd": round(td_tvd),
        "cement_thickening_temp": round(bhct, 1),
        "tool_rating_note": tool_rating_note,
        "uses_measured": uses_measured,
        "profile": profile,
    }
