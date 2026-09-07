"""Stuck pipe / free-point — differential sticking and stretch free-point.

Differential sticking (over-balanced, permeable zone):
  ΔP     = (MW − pore_EMW) · 0.052 · TVD                 (overbalance, psi)
  A_c    = (embed_frac · pipe_OD) · (zone_len · 12)      (contact area, in²)
  F_stick = cake_friction · ΔP · A_c                     (sticking force, lbf)

Free-point from measured pipe stretch (elastic, uniform pipe):
  weight-based (field free-point-constant form):
    FreePoint_ft = stretch_in · pipe_weight_lbft · 735000 / pull_force
  area-based (Hooke's law, E·A·ΔL / (12·F)):
    FreePoint_ft = E · pipe_area · stretch_in / (12 · pull_force)

Spotting pill to cover the permeable zone + 100 ft above in the annulus:
  ann_cap = (hole² − pipe_OD²) / 1029.4  (bbl/ft)
  pill    = ann_cap · (zone_len + 100) · 1.2  (20% excess)."""
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (geopresión, TD, etc.)
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


# Listamos los inputs del formulario de stuck pipe / free-point, con sus valores por defecto
INPUTS = [
    Inp("mw", "Mud weight", 9.9, "ppg"),
    Inp("pore_emw", "Pore pressure", 9.2, "ppg"),
    Inp("perm_zone_len", "Permeable zone length", 30, "ft"),
    Inp("cake_friction", "Filter-cake friction coeff", 0.25, ""),
    Inp("dp_od", "Pipe OD", 5.0, "in"),
    Inp("hole_size", "Hole size", 8.5, "in"),
    Inp("embed_frac", "Pipe embedment fraction", 0.4, "0-1"),
    Inp("pipe_weight", "Pipe weight in air", 19.5, "lb/ft"),
    Inp("pipe_area", "Pipe steel area", 5.27, "in²"),
    Inp("stretch_in", "Measured pipe stretch", 24, "in"),
    Inp("pull_force", "Applied pull (over string wt)", 40000, "lbf"),
    Inp("youngs", "Young's modulus", 30000000, "psi"),
]


def context_defaults(ctx: WellContext) -> dict:
    """Seed mud weight / pore pressure from the shared geopressure profile so the
    overbalance basis matches the rest of the well design (same design line)."""
    # Solo sembramos valores si el contexto trae perfil de geopresión y TD conocido
    if ctx.has_geopressure() and ctx.td_tvd():
        # Leemos la presión de poro en TVD final para usarla como base
        pore = ctx.pore_at(ctx.td_tvd())
        # Devolvemos mud weight (con margen de viaje) y pore pressure derivados del perfil
        return {"mw": round(pore + 0.4, 1), "pore_emw": round(pore, 1)}
    # Si no hay perfil de geopresión, no sembramos nada (se usan los defaults del formulario)
    return {}


def compute(params: dict, ctx: WellContext) -> dict:
    # Armamos el diccionario de parámetros, tomando el valor enviado o el default de cada input
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    # Usamos el TVD final del pozo (o el MD como respaldo) como profundidad de referencia
    tvd = ctx.td_tvd() or (ctx.td() or 10000)

    # --- differential sticking (permeable zone taken at TD) ---
    # Calculamos el sobrebalance en EMW (mud weight menos presión de poro)
    overbalance_emw = p["mw"] - p["pore_emw"]
    # Convertimos el sobrebalance a psi usando el gradiente hidrostático y el TVD
    overbalance_psi = overbalance_emw * 0.052 * tvd
    # contact area (in²): contact width (embed_frac·OD, in) over zone length (in)
    a_c = (p["embed_frac"] * p["dp_od"]) * (p["perm_zone_len"] * 12)
    f_stick = p["cake_friction"] * overbalance_psi * a_c  # lbf

    # --- free point from stretch ---
    # weight-based (field free-point-constant form; constant = 735000)
    freepoint_weight = (p["stretch_in"] * p["pipe_weight"] * 735000) / p["pull_force"] if p["pull_force"] else 0.0
    # area-based (Hooke's law: E·A·ΔL / (12·F))
    freepoint_area = (p["youngs"] * p["pipe_area"] * p["stretch_in"]) / (12 * p["pull_force"]) if p["pull_force"] else 0.0

    # --- spotting pill (cover zone + 100 ft above, 20% excess) ---
    ann_cap = (p["hole_size"] ** 2 - p["dp_od"] ** 2) / 1029.4  # bbl/ft
    pill_bbl = ann_cap * (p["perm_zone_len"] + 100) * 1.2

    # Determinamos el mecanismo probable según el nivel de sobrebalance
    mechanism = ("Differential sticking likely" if overbalance_psi > 500
                 else "Low differential — check pack-off/geometry")

    # Devolvemos todos los resultados redondeados para mostrar en el formulario
    return {
        "overbalance_psi": round(overbalance_psi),
        "overbalance_emw": round(overbalance_emw, 2),
        "stick_force_klbf": round(f_stick / 1000, 1),
        "freepoint_weight_ft": round(freepoint_weight),
        "freepoint_area_ft": round(freepoint_area),
        "ann_cap_bblft": round(ann_cap, 4),
        "pill_bbl": round(pill_bbl, 1),
        "tvd": round(tvd),
        "mechanism": mechanism,
        "high_risk": overbalance_psi > 1000,
    }
