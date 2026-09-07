"""Well control — kill sheet, MAASP and kick tolerance.

Kill sheet (Wait & Weight and Driller's methods):
  KMW  = MW + SIDPP / (0.052·TVD)
  ICP  = SIDPP + slow-pump pressure
  FCP  = slow-pump pressure · KMW / MW
  Pressure-vs-strokes step-down schedule from ICP to FCP over strokes-to-bit.

MAASP = (EMW_leakoff − MW) · 0.052 · TVD_shoe  (max annulus surface pressure).

Kick tolerance: the maximum kick intensity (extra formation EMW at TD) tolerable
as a zero-volume kick, and the influx volume tolerable at a design kick
intensity before the casing shoe fractures with the gas at the shoe."""
# Importamos math (usado por otros cálculos de ingeniería del mismo estilo de módulo)
import math
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (casing, geopresión, TVD, etc.)
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


# Listamos los inputs del formulario de control de pozo, con sus valores por defecto
INPUTS = [
    Inp("mw", "Current mud weight", 9.9, "ppg"),
    Inp("sidpp", "Shut-in drill-pipe pressure", 350, "psi"),
    Inp("sicp", "Shut-in casing pressure", 500, "psi"),
    Inp("pit_gain", "Pit gain (influx)", 12, "bbl"),
    Inp("slow_spm", "Slow pump rate", 40, "spm"),
    Inp("slow_press", "Slow-pump (kill-rate) pressure", 700, "psi"),
    Inp("pump_output", "Pump output", 0.102, "bbl/stk"),
    Inp("dp_capacity", "Drill-string capacity", 0.0178, "bbl/ft"),
    Inp("frac_emw_shoe", "Leak-off / frac EMW at shoe", 15.4, "ppg"),
    Inp("design_ki", "Design kick intensity", 0.5, "ppg"),
    Inp("gas_grad", "Influx (gas) gradient", 0.10, "psi/ft"),
    Inp("shoe_hole_id", "Casing ID at shoe (annulus)", 8.681, "in"),
    Inp("dp_od", "Drill pipe OD", 5.0, "in"),
]


def context_defaults(ctx: WellContext) -> dict:
    """Seed the kill-sheet inputs from the shared pore/fracture profile so the
    well-control basis matches the casing/mud design (same design line)."""
    out: dict = {}
    tvd = ctx.td_tvd()
    # Sin perfil de geopresión o sin TVD conocido no podemos sembrar valores
    if not ctx.has_geopressure() or not tvd:
        return out
    # Leemos la presión de poro en el TVD final
    pore = ctx.pore_at(tvd)
    if pore:
        out["mw"] = round(pore + 0.3, 1)          # drilling mw = pore + trip margin
    # Recolectamos los TVD de zapato de todos los strings excepto el último (el de producción/TD)
    shoes = [c.get("setting_tvd") or ctx.tvd_at(c.get("setting_md") or 0)
             for c in ctx.casing[:-1] if c.get("setting_md")]
    # Usamos el zapato más profundo como referencia, o un estimado si no hay casing
    shoe_tvd = max(shoes) if shoes else tvd * 0.36
    # Leemos el EMW de fractura en el zapato de referencia
    frac = ctx.frac_at(shoe_tvd)
    if frac:
        out["frac_emw_shoe"] = round(frac, 1)
    # Devolvemos los valores sembrados desde el perfil compartido
    return out


def compute(params: dict, ctx: WellContext) -> dict:
    # Armamos el diccionario de parámetros, tomando el valor enviado o el default de cada input
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    mw = p["mw"]
    # Usamos el TVD final del pozo (o el MD como respaldo) como profundidad de referencia
    tvd = ctx.td_tvd() or (ctx.td() or 10000)
    # Determinamos la profundidad MD del zapato de la última sarta previa al TD
    shoe_md = max([c.get("setting_md") for c in ctx.casing[:-1] if c.get("setting_md")] or [tvd * 0.36])
    shoe_tvd = ctx.tvd_at(shoe_md) or shoe_md

    # --- kill sheet ---
    # Calculamos el peso de lodo de matanza (KMW) a partir del SIDPP
    kmw = mw + p["sidpp"] / (0.052 * tvd)
    # Calculamos la presión inicial de circulación (ICP)
    icp = p["sidpp"] + p["slow_press"]
    # Calculamos la presión final de circulación (FCP); guardamos con 0 si mw es 0 para evitar división por cero
    fcp = p["slow_press"] * kmw / mw if mw else 0
    # Calculamos las emboladas y minutos hasta que el lodo de matanza llegue a la broca
    strokes_to_bit = round(p["dp_capacity"] * (ctx.td() or tvd) / p["pump_output"]) if p["pump_output"] else 0
    minutes_to_bit = round(strokes_to_bit / p["slow_spm"], 1) if p["slow_spm"] else 0
    schedule = []
    steps = 10
    # Construimos el programa de presión-vs-emboladas, bajando linealmente de ICP a FCP
    for i in range(steps + 1):
        stk = round(strokes_to_bit * i / steps)
        press = round(icp - (icp - fcp) * i / steps)
        schedule.append({"strokes": stk, "pressure": press, "minutes": round(stk / p["slow_spm"], 1) if p["slow_spm"] else 0})

    # --- MAASP ---
    # Calculamos la presión máxima admisible en superficie del anular (MAASP) con el mud weight actual
    maasp = (p["frac_emw_shoe"] - mw) * 0.052 * shoe_tvd
    # Calculamos el MAASP equivalente con el peso de lodo de matanza (KMW)
    maasp_kill = (p["frac_emw_shoe"] - kmw) * 0.052 * shoe_tvd

    # --- kick tolerance ---
    # max kick intensity as zero-volume kick (frac at shoe governs)
    max_ki = (p["frac_emw_shoe"] - mw) * shoe_tvd / tvd
    # influx volume tolerable at the design KI, gas at the shoe
    gas_emw = p["gas_grad"] / 0.052
    # available pressure margin at shoe for the influx column
    margin = (p["frac_emw_shoe"] - mw) * 0.052 * shoe_tvd - p["design_ki"] * 0.052 * tvd
    denom = 0.052 * (mw - gas_emw)
    # Calculamos la altura de columna de influjo tolerable (evitando división por cero o negativos)
    influx_h = max(0.0, margin / denom) if denom > 0 else 0.0
    ann_cap = (p["shoe_hole_id"] ** 2 - p["dp_od"] ** 2) / 1029.4  # bbl/ft
    # Convertimos la altura de influjo a volumen tolerable en barriles
    kt_volume = round(influx_h * ann_cap, 1)

    # influx classification from gradients
    influx_grad = None
    if p["pit_gain"] > 0:
        # Estimamos el gradiente del influjo a partir de la diferencia SICP-SIDPP y el pit gain
        influx_grad = (p["sicp"] - p["sidpp"]) / (p["pit_gain"] / ann_cap) if ann_cap else None
    influx_type = "—"
    if influx_grad is not None:
        # Clasificamos el tipo de influjo (gas / aceite-mixto / agua) según el gradiente estimado
        influx_type = "Gas" if influx_grad < 0.25 else ("Oil / mixed" if influx_grad < 0.4 else "Water")

    # Devolvemos el kill sheet, el MAASP y la tolerancia al kick calculados
    return {
        "kmw": round(kmw, 2), "icp": round(icp), "fcp": round(fcp),
        "strokes_to_bit": strokes_to_bit, "minutes_to_bit": minutes_to_bit, "schedule": schedule,
        "maasp": round(maasp), "maasp_kill": round(maasp_kill),
        "max_ki": round(max_ki, 2), "kt_volume": kt_volume, "influx_h": round(influx_h, 1),
        "shoe_md": round(shoe_md), "shoe_tvd": round(shoe_tvd), "tvd": round(tvd),
        "influx_type": influx_type,
        "ki_ok": p["design_ki"] <= max_ki, "vol_ok": p["pit_gain"] <= kt_volume,
        "design_ki": p["design_ki"], "pit_gain": p["pit_gain"],
    }
