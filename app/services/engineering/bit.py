"""Bit selection & drilling optimization.

1. Recommendation per prognosed formation (from the Formation Tops grid): bit
   type (PDC / roller-cone / impregnated) and an IADC-style code from the
   lithology and hole size.
2. Cost-per-foot for a candidate bit run and the break-even ROP against an
   alternative bit.
3. Mechanical Specific Energy (Teale) as a drilling-efficiency metric and the
   implied bit efficiency."""
# Importamos math para las fórmulas de área (MSE) y raíz cuadrada
import math
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (formaciones, hueco, etc.)
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


# Listamos los inputs del formulario de selección de broca, con sus valores por defecto
INPUTS = [
    Inp("bit_cost", "Candidate bit cost", 28000, "$"),
    Inp("rig_rate", "Rig + spread rate", 1800, "$/hr"),
    Inp("trip_hours", "Trip time (round)", 9, "hr"),
    Inp("footage", "Expected footage", 4500, "ft"),
    Inp("rop", "Expected ROP", 55, "ft/hr"),
    Inp("alt_bit_cost", "Alternative bit cost", 6000, "$"),
    Inp("alt_footage", "Alternative footage", 2200, "ft"),
    Inp("alt_rop", "Alternative ROP", 40, "ft/hr"),
    Inp("bit_diameter", "Bit diameter (MSE)", 8.5, "in"),
    Inp("wob_mse", "WOB (MSE)", 35, "klbf"),
    Inp("rpm_mse", "RPM (MSE)", 120, "rpm"),
    Inp("torque_mse", "Bit torque (MSE)", 2500, "ft-lbf"),
    Inp("rop_mse", "ROP (MSE)", 55, "ft/hr"),
]

# Listamos las palabras clave que identifican litología blanda
_SOFT = ("arcilla", "arena", "grava", "clay", "sand", "unconsolid")
# Listamos las palabras clave que identifican litología dura
_HARD = ("basamento", "granito", "chert", "igneous", "basement", "hard")
# Listamos las palabras clave que identifican litología media
_MED = ("lutita", "caliza", "shale", "limestone", "dolomit", "conglomer", "arenisca", "sandstone")


def _recommend(lith, hole):
    # Normalizamos la litología a minúsculas para comparar contra las listas de palabras clave
    l = (lith or "").lower()
    # Consideramos hueco grande a partir de 12 pulgadas
    big = hole >= 12
    if any(k in l for k in _HARD):
        # Recomendamos broca para formación dura, distinguiendo hueco grande vs pequeño
        return ("Impregnated / hard PDC" if not big else "Roller cone (hard)",
                "IADC M433" if not big else "IADC 6-3-7", "High blade count, small cutters, high DF")
    if any(k in l for k in _SOFT):
        # Recomendamos broca para formación blanda
        return ("PDC (soft, long parabolic)", "IADC S123" if not big else "IADC 1-1-5",
                "Few blades, large cutters, aggressive")
    if any(k in l for k in _MED):
        # Recomendamos broca para formación media
        return ("PDC (medium)", "IADC M323", "Medium blade count, medium cutters")
    # Si no reconocemos la litología, devolvemos la recomendación media por defecto
    return ("PDC (medium)", "IADC M323", "General medium formation")


def _cpf(bit_cost, rig_rate, trip, footage, rop):
    # Sin metraje o ROP válidos no podemos calcular el costo por pie
    if footage <= 0 or rop <= 0:
        return None
    # Calculamos el costo por pie: (costo de broca + tarifa·(horas de perforación + viaje)) / metraje
    return (bit_cost + rig_rate * (footage / rop + trip)) / footage


def compute(params: dict, ctx: WellContext) -> dict:
    # Armamos el diccionario de parámetros, tomando el valor enviado o el default de cada input
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}

    recs = []
    # Recorremos cada formación prognosticada para recomendar una broca
    for f in ctx.formations:
        hole = None
        md = f.get("md")
        # Buscamos el diámetro de hueco vigente en la profundidad de la formación
        for h in ctx.hole:
            if h.get("top_md") is not None and h.get("bottom_md") is not None and h["top_md"] <= (md or 0) <= h["bottom_md"]:
                hole = h.get("hole_size_in")
        # Si no encontramos sección de hueco que cubra esa profundidad, usamos la última del programa
        hole = hole or (ctx.hole[-1]["hole_size_in"] if ctx.hole else 8.5)
        bt, iadc, feat = _recommend(f.get("lithology"), hole)
        recs.append({"formation": f.get("formation"), "md": round(md) if md else None, "lith": f.get("lithology"),
                     "hole": hole, "type": bt, "iadc": iadc, "features": feat})

    # Calculamos el costo por pie de la broca candidata y de la alternativa
    cpf = _cpf(p["bit_cost"], p["rig_rate"], p["trip_hours"], p["footage"], p["rop"])
    cpf_alt = _cpf(p["alt_bit_cost"], p["rig_rate"], p["trip_hours"], p["alt_footage"], p["alt_rop"])
    # break-even ROP for candidate to match the alternative's CPF
    breakeven_rop = None
    if cpf_alt and p["footage"] > 0:
        # Despejamos el ROP que iguala el costo por pie de la candidata con el de la alternativa
        denom = cpf_alt * p["footage"] - p["bit_cost"] - p["rig_rate"] * p["trip_hours"]
        breakeven_rop = round(p["rig_rate"] * p["footage"] / denom, 1) if denom > 0 else None

    # MSE (Teale)
    D = p["bit_diameter"]; Ab = math.pi / 4 * D * D
    wob = p["wob_mse"] * 1000
    # Calculamos la Energía Específica Mecánica (MSE) combinando el término de empuje y el de torque
    mse = 4 * wob / (math.pi * D * D) + (480 * p["torque_mse"] * p["rpm_mse"]) / (D * D * p["rop_mse"]) if p["rop_mse"] else 0
    # bit efficiency ~ min MSE / MSE (assume ~ confined rock strength as floor); report MSE vs a nominal UCS
    ucs_nominal = 18000  # psi typical medium rock
    # Estimamos la eficiencia de la broca comparando el MSE contra una resistencia de roca nominal
    efficiency = round(min(100, ucs_nominal / mse * 100), 0) if mse else None

    # Devolvemos las recomendaciones por formación y los resultados de costo/eficiencia
    return {
        "recs": recs,
        "cpf": round(cpf, 1) if cpf else None, "cpf_alt": round(cpf_alt, 1) if cpf_alt else None,
        "cheaper": ("candidate" if (cpf and cpf_alt and cpf < cpf_alt) else "alternative"),
        "breakeven_rop": breakeven_rop, "footage": round(p["footage"]), "rop": p["rop"],
        "mse": round(mse), "mse_efficiency": efficiency, "bit_diameter": D,
    }
