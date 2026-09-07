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
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (geopresión, TVD, etc.)
from app.services.engineering.context import WellContext


# Definimos la estructura de cada input que se muestra en el formulario del cálculo
@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


# Listamos los inputs del formulario de temperatura, con sus valores por defecto
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
    # Sin perfil de geopresión con datos de temperatura no podemos sembrar nada
    if not ctx.has_geopressure() or not ctx.geopressure:
        return out
    # Filtramos los puntos del grid de geopresión que traen temperatura y TVD
    pts = [g for g in ctx.geopressure if g.get("temp_f") is not None and g.get("tvd") is not None]
    if not pts:
        return out
    # Tomamos el punto más somero como referencia de temperatura de superficie
    shallow = min(pts, key=lambda g: g["tvd"])
    out["surface_temp"] = round(float(shallow["temp_f"]), 1)
    # Devolvemos la temperatura de superficie sembrada desde el perfil compartido
    return out


def compute(params: dict, ctx: WellContext) -> dict:
    # Armamos el diccionario de parámetros, tomando el valor enviado o el default de cada input
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    surface_temp = p["surface_temp"]
    inlet_temp = p["inlet_temp"]
    # Usamos el TVD final del pozo (o el MD como respaldo) como profundidad de referencia
    td_tvd = ctx.td_tvd() or (ctx.td() or 10000)
    td_md = ctx.td() or td_tvd

    # --- static / geothermal profile ---
    # Prefer a measured temperature profile from the geopressure grid; fall back
    # to the input geothermal gradient.
    uses_measured = False
    # Intentamos leer la temperatura medida en el TVD final desde el grid de geopresión
    measured_bottom = ctx.temp_at(td_tvd) if ctx.has_geopressure() else None
    if measured_bottom is not None:
        uses_measured = True
        bhst = float(measured_bottom)
        # Retrocalculamos el gradiente efectivo entre superficie y fondo a partir del dato medido
        geo_grad_eff = (bhst - surface_temp) / (td_tvd / 100) if td_tvd else p["geo_grad"]
    else:
        # Sin dato medido, usamos el gradiente ingresado para proyectar la temperatura de fondo
        geo_grad_eff = p["geo_grad"]
        bhst = surface_temp + geo_grad_eff * td_tvd / 100

    def static_at(tvd: float) -> float:
        if uses_measured:
            # Si hay perfil medido, preferimos el valor medido en esa profundidad si existe
            m = ctx.temp_at(tvd)
            if m is not None:
                return float(m)
        # Si no hay medición en ese punto, proyectamos con el gradiente efectivo
        return surface_temp + geo_grad_eff * tvd / 100

    # --- bottom-hole circulating temperature (BHCT) ---
    # Simplified published-chart approximation: BHCT is a depth-decreasing
    # fraction of the static bottom-hole temperature above surface.
    f = 0.97 - 0.0000265 * td_tvd
    # Acotamos la fracción f al rango físicamente razonable del chart
    f = max(0.5, min(0.97, f))
    bhct_base = surface_temp + (bhst - surface_temp) * f
    # Small correction for mud inlet temperature and circulation time (minor).
    bhct = bhct_base + (inlet_temp - bhct_base) * max(0.0, 0.15 - 0.02 * p["circ_hours"])

    # --- profiles at ~10 stations from surface to TD ---
    profile = []
    stations = 10
    # Construimos el perfil de temperatura estática y circulante en 10 estaciones de superficie a TD
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

    # Armamos la nota de rating de herramientas, combinando la temperatura estática y la circulante
    tool_rating_note = (
        "Rate tools/electronics for BHST %.0f°F static; BHCT %.0f°F governs cement "
        "slurry thickening-time." % (bhst, bhct)
    )

    # Devolvemos las temperaturas de fondo, el perfil completo y la nota de rating
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
