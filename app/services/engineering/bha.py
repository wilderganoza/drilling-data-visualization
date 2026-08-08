"""BHA / drillstring design & analysis.

Builds the assembly weights (air & buoyed), the WOB available while keeping the
neutral point safely inside the drill collars, the neutral-point location, the
weight below the jars, and the directional tendency (fulcrum-build / packed-hold
/ pendulum-drop) from the stabilizer configuration. Collar steel weight from the
standard 2.674·(OD²−ID²) lb/ft."""
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
    Inp("bit_size", "Bit size", 8.5, "in"),
    Inp("collar_od", "Drill-collar OD", 6.75, "in"),
    Inp("collar_id", "Drill-collar ID", 2.8125, "in"),
    Inp("collar_length", "Total drill-collar length", 270, "ft"),
    Inp("hwdp_weight", "HWDP weight", 49.7, "ppf"),
    Inp("hwdp_length", "HWDP length", 300, "ft"),
    Inp("mud_weight", "Mud weight", 9.9, "ppg"),
    Inp("wob", "Design WOB", 35, "klbf"),
    Inp("jar_position", "Jar position (above bit)", 200, "ft"),
    Inp("nearbit_stab", "Near-bit stabilizer (0/1)", 1, ""),
    Inp("nearbit_dist", "Near-bit stab distance from bit", 3, "ft"),
    Inp("stab_count", "Total string stabilizers", 3, ""),
    Inp("gauge_pct", "Stabilizer blade gauge", 99, "%"),
    Inp("design_factor", "WOB safety factor (NP in collars)", 0.85, ""),
]


def compute(params: dict, ctx: WellContext) -> dict:
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    bf = 1.0 - p["mud_weight"] / 65.4
    collar_ppf = 2.674 * (p["collar_od"] ** 2 - p["collar_id"] ** 2)
    collar_wt = collar_ppf * p["collar_length"]
    hwdp_wt = p["hwdp_weight"] * p["hwdp_length"]
    bha_air = collar_wt + hwdp_wt
    bha_buoyed = bha_air * bf

    # WOB available keeping neutral point inside the collars (design factor margin)
    max_wob_collars = collar_wt * bf * p["design_factor"]
    # neutral point above bit (ft): NP = WOB / (buoyed weight per ft of collars)
    np_ft = (p["wob"] * 1000.0) / (collar_ppf * bf) if collar_ppf else 0
    np_zone = "drill collars" if np_ft <= p["collar_length"] else ("HWDP" if np_ft <= p["collar_length"] + p["hwdp_length"] else "DRILL PIPE (unsafe)")
    np_ok = np_ft <= p["collar_length"]

    # weight below jars (buoyed) — collars/HWDP below the jar position
    below = collar_ppf * min(p["jar_position"], p["collar_length"])
    if p["jar_position"] > p["collar_length"]:
        below += p["hwdp_weight"] * (p["jar_position"] - p["collar_length"])
    weight_below_jars = below * bf

    # directional tendency (simplified fulcrum / packed / pendulum)
    if p["nearbit_stab"] >= 1 and p["nearbit_dist"] <= 5 and p["stab_count"] <= 1:
        tendency = "Build (fulcrum)"
    elif p["stab_count"] >= 3 and p["nearbit_stab"] >= 1:
        tendency = "Hold (packed)"
    elif p["nearbit_stab"] < 1 or p["nearbit_dist"] > 30:
        tendency = "Drop (pendulum)"
    else:
        tendency = "Slight build / hold"

    return {
        "collar_ppf": round(collar_ppf, 1), "collar_wt": round(collar_wt), "hwdp_wt": round(hwdp_wt),
        "bha_air": round(bha_air), "bha_buoyed": round(bha_buoyed), "bf": round(bf, 3),
        "max_wob": round(max_wob_collars / 1000, 1), "wob": p["wob"], "wob_ok": p["wob"] * 1000 <= max_wob_collars,
        "np_ft": round(np_ft), "np_zone": np_zone, "np_ok": np_ok,
        "weight_below_jars": round(weight_below_jars / 1000, 1), "jar_position": round(p["jar_position"]),
        "tendency": tendency, "stab_count": int(p["stab_count"]), "gauge": p["gauge_pct"],
        "bit_size": p["bit_size"],
    }
