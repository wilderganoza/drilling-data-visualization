"""Primary cementing design per casing string.

For each string (matched to its open-hole section) computes annular and casing
capacities, required slurry volume (cement column + shoe track + open-hole
excess), sacks, spacer, displacement volume and strokes, plug-bump differential
pressure, U-tube hydrostatic balance / free-fall check, and a centralizer
standoff estimate. Geometry from the casing & hole programs; slurry densities /
TOC compared against the planned Cement Program grid where available."""
# Importamos math para la raíz cuadrada del cálculo de espesor de pared
import math
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (casing, hueco, TVD, etc.)
from app.services.engineering.context import WellContext

# Definimos el factor de conversión de pies cúbicos a barriles
FT3_PER_BBL = 5.615
PROGRAM_TARGETS = ["cement-program"]  # this module generates the Cement Program grid


# Definimos la estructura de cada input que se muestra en el formulario del cálculo
@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


# Listamos los inputs del formulario de cementación, con sus valores por defecto
INPUTS = [
    Inp("excess", "Open-hole excess", 0.5, "frac"),
    Inp("shoe_track", "Shoe track length", 80, "ft"),
    Inp("lead_density", "Lead slurry density", 13.5, "ppg"),
    Inp("tail_density", "Tail slurry density", 15.8, "ppg"),
    Inp("tail_length", "Tail slurry length", 500, "ft"),
    Inp("spacer_density", "Spacer density", 10.5, "ppg"),
    Inp("spacer_bbl", "Spacer volume", 30, "bbl"),
    Inp("mud_density", "Displacement mud density", 9.9, "ppg"),
    Inp("cement_yield", "Cement yield", 1.15, "ft³/sack"),
    Inp("pump_output", "Pump output", 0.102, "bbl/stk"),
    Inp("centralizer_spacing", "Centralizer spacing", 40, "ft"),
]


def _wall(od, ppf):
    # Estimamos el espesor de pared a partir del OD y el peso por pie (fórmula API aproximada)
    disc = od * od - 4 * ppf / 10.68
    # Si el discriminante es válido devolvemos el espesor real, si no un valor mínimo de respaldo
    return (od - math.sqrt(disc)) / 2.0 if disc > 0 else od * 0.05


def _hole_id_at(ctx, md):
    # Buscamos la sección de hueco que contiene esta profundidad
    for h in ctx.hole:
        top, bot = h.get("top_md"), h.get("bottom_md")
        if top is not None and bot is not None and top <= md <= bot:
            return h.get("hole_size_in")
    # Si no encontramos sección que la cubra, usamos la última del programa como respaldo
    return ctx.hole[-1]["hole_size_in"] if ctx.hole else None


def compute(params: dict, ctx: WellContext) -> dict:
    # Armamos el diccionario de parámetros, tomando el valor enviado o el default de cada input
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    strings = ctx.casing
    jobs = []
    # Recorremos cada string de casing del programa para calcular su job de cementación
    for idx, c in enumerate(strings):
        name = (c.get("string") or "").lower()
        # El conductor no se cementa con este flujo, así que lo saltamos
        if "conductor" in name:
            continue
        od = c.get("od_in"); ppf = c.get("weight_ppf"); md = c.get("setting_md")
        # Sin OD, peso o profundidad de asentamiento no podemos calcular este string
        if not od or not ppf or not md:
            continue
        t = _wall(od, ppf); idd = od - 2 * t
        # Obtenemos el diámetro de hueco en la profundidad de asentamiento (o un estimado si falta)
        hole = _hole_id_at(ctx, md) or (od + 1.5)
        ann_cap = (hole ** 2 - od ** 2) / 1029.4       # bbl/ft
        int_cap = (idd ** 2) / 1029.4                  # bbl/ft
        # top of cement: liner hangs off previous shoe; others to surface
        is_liner = "liner" in name
        # Si es liner, el tope de cemento parte del zapato del string anterior; si no, va a superficie
        toc = (strings[idx - 1].get("setting_md") if is_liner and idx > 0 else 0) or 0
        col_len = md - toc
        tail_len = min(p["tail_length"], col_len)
        lead_len = max(0.0, col_len - tail_len)

        # Calculamos el volumen de lechada total, la porción de cola y la de cabeza
        slurry_bbl = ann_cap * col_len * (1 + p["excess"]) + int_cap * p["shoe_track"]
        tail_bbl = ann_cap * tail_len * (1 + p["excess"]) + int_cap * p["shoe_track"]
        lead_bbl = slurry_bbl - tail_bbl
        # Convertimos el volumen de lechada a sacos de cemento según el rendimiento
        sacks = round(slurry_bbl * FT3_PER_BBL / p["cement_yield"])
        # Calculamos el volumen de desplazamiento y las emboladas necesarias
        displacement_bbl = int_cap * (md - p["shoe_track"])
        strokes = round(displacement_bbl / p["pump_output"]) if p["pump_output"] else 0

        # hydrostatics at shoe: outside (cement column) vs inside (displacement mud) → differential at bump
        tvd_shoe = ctx.tvd_at(md) or md
        tvd_toc = ctx.tvd_at(toc) or toc
        # Promediamos la densidad de la columna de cemento (cabeza + cola) ponderada por longitud
        avg_slurry = (p["lead_density"] * lead_len + p["tail_density"] * tail_len) / col_len if col_len else p["tail_density"]
        # Calculamos la presión hidrostática afuera (columna de cemento + lodo sobre el TOC)
        p_out = avg_slurry * 0.052 * (tvd_shoe - tvd_toc) + p["mud_density"] * 0.052 * tvd_toc
        # Calculamos la presión hidrostática adentro (lodo de desplazamiento hasta el zapato)
        p_in = p["mud_density"] * 0.052 * tvd_shoe
        differential = round(p_out - p_in)  # positive → U-tube tendency, need to hold with pressure at bump
        free_fall = differential > 0

        # Estimamos el standoff del centralizador según el espaciamiento y la relación OD/hueco
        standoff = min(100, round(100 * (1 - (od / hole) * (p["centralizer_spacing"] / 100.0) * 0.4)))
        jobs.append({
            "string": c.get("string"), "od": od, "hole": hole, "toc": round(toc), "shoe": round(md),
            "col_len": round(col_len), "ann_cap": round(ann_cap, 4), "int_cap": round(int_cap, 4),
            "lead_bbl": round(lead_bbl, 1), "tail_bbl": round(tail_bbl, 1), "slurry_bbl": round(slurry_bbl, 1),
            "sacks": sacks, "spacer_bbl": p["spacer_bbl"], "displacement_bbl": round(displacement_bbl, 1),
            "strokes": strokes, "differential": differential, "free_fall": free_fall,
            "avg_slurry": round(avg_slurry, 1), "standoff": standoff, "is_liner": is_liner,
        })
    # Devolvemos todos los jobs de cementación calculados
    return {"jobs": jobs, "pump_output": p["pump_output"], "excess": p["excess"]}


def generate_rows(params: dict, ctx: WellContext, target: str = "cement-program") -> list[dict]:
    """Rows for the Cement Program grid (one per cemented string)."""
    # Reutilizamos compute() para obtener los jobs de cementación
    res = compute(params, ctx)
    rows = []
    # Convertimos cada job en una fila del grid del Cement Program
    for j in res["jobs"]:
        rows.append({
            "string": j["string"], "slurry_type": ("Lead + Tail" if not j["is_liner"] else "Tail"),
            "density_ppg": j["avg_slurry"], "volume_bbl": j["slurry_bbl"],
            "top_md": j["toc"], "bottom_md": j["shoe"],
            "comments": f"{j['sacks']} sacks · displacement {j['displacement_bbl']} bbl · standoff ~{j['standoff']}%",
        })
    # Devolvemos las filas listas para insertar en el grid
    return rows
