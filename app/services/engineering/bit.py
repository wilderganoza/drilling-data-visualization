"""Bit selection & drilling optimization.

1. Recommendation per prognosed formation (from the Formation Tops grid): bit
   type (PDC / roller-cone / impregnated) and an IADC-style code from the
   lithology and hole size.
2. Cost-per-foot for a candidate bit run and the break-even ROP against an
   alternative bit.
3. Mechanical Specific Energy (Teale) as a drilling-efficiency metric and the
   implied bit efficiency."""
import math
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

_SOFT = ("arcilla", "arena", "grava", "clay", "sand", "unconsolid")
_HARD = ("basamento", "granito", "chert", "igneous", "basement", "hard")
_MED = ("lutita", "caliza", "shale", "limestone", "dolomit", "conglomer", "arenisca", "sandstone")


def _recommend(lith, hole):
    l = (lith or "").lower()
    big = hole >= 12
    if any(k in l for k in _HARD):
        return ("Impregnated / hard PDC" if not big else "Roller cone (hard)",
                "IADC M433" if not big else "IADC 6-3-7", "High blade count, small cutters, high DF")
    if any(k in l for k in _SOFT):
        return ("PDC (soft, long parabolic)", "IADC S123" if not big else "IADC 1-1-5",
                "Few blades, large cutters, aggressive")
    if any(k in l for k in _MED):
        return ("PDC (medium)", "IADC M323", "Medium blade count, medium cutters")
    return ("PDC (medium)", "IADC M323", "General medium formation")


def _cpf(bit_cost, rig_rate, trip, footage, rop):
    if footage <= 0 or rop <= 0:
        return None
    return (bit_cost + rig_rate * (footage / rop + trip)) / footage


def compute(params: dict, ctx: WellContext) -> dict:
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}

    recs = []
    for f in ctx.formations:
        hole = None
        md = f.get("md")
        for h in ctx.hole:
            if h.get("top_md") is not None and h.get("bottom_md") is not None and h["top_md"] <= (md or 0) <= h["bottom_md"]:
                hole = h.get("hole_size_in")
        hole = hole or (ctx.hole[-1]["hole_size_in"] if ctx.hole else 8.5)
        bt, iadc, feat = _recommend(f.get("lithology"), hole)
        recs.append({"formation": f.get("formation"), "md": round(md) if md else None, "lith": f.get("lithology"),
                     "hole": hole, "type": bt, "iadc": iadc, "features": feat})

    cpf = _cpf(p["bit_cost"], p["rig_rate"], p["trip_hours"], p["footage"], p["rop"])
    cpf_alt = _cpf(p["alt_bit_cost"], p["rig_rate"], p["trip_hours"], p["alt_footage"], p["alt_rop"])
    # break-even ROP for candidate to match the alternative's CPF
    breakeven_rop = None
    if cpf_alt and p["footage"] > 0:
        denom = cpf_alt * p["footage"] - p["bit_cost"] - p["rig_rate"] * p["trip_hours"]
        breakeven_rop = round(p["rig_rate"] * p["footage"] / denom, 1) if denom > 0 else None

    # MSE (Teale)
    D = p["bit_diameter"]; Ab = math.pi / 4 * D * D
    wob = p["wob_mse"] * 1000
    mse = 4 * wob / (math.pi * D * D) + (480 * p["torque_mse"] * p["rpm_mse"]) / (D * D * p["rop_mse"]) if p["rop_mse"] else 0
    # bit efficiency ~ min MSE / MSE (assume ~ confined rock strength as floor); report MSE vs a nominal UCS
    ucs_nominal = 18000  # psi typical medium rock
    efficiency = round(min(100, ucs_nominal / mse * 100), 0) if mse else None

    return {
        "recs": recs,
        "cpf": round(cpf, 1) if cpf else None, "cpf_alt": round(cpf_alt, 1) if cpf_alt else None,
        "cheaper": ("candidate" if (cpf and cpf_alt and cpf < cpf_alt) else "alternative"),
        "breakeven_rop": breakeven_rop, "footage": round(p["footage"]), "rop": p["rop"],
        "mse": round(mse), "mse_efficiency": efficiency, "bit_diameter": D,
    }
