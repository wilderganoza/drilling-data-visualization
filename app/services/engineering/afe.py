"""AFE builder — authorization for expenditure.

Rolls up the detailed cost-estimate program grid by category, adds contingency
and the completion cost to a dry-hole/total AFE, derives cost-per-foot and
days, benchmarks cost/ft against the offset wells, produces a P10/P50/P90 range
from a stated uncertainty, and lays out a time–depth cost curve (cumulative
spend vs planned day) for the classic AFE curve."""
# Importamos dataclass para tipar cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el contexto compartido del pozo (cost-estimate, plan, time-depth, etc.)
from app.services.engineering.context import WellContext

PROGRAM_TARGETS = ["cost-estimate"]  # generate a template AFE Cost Estimate


# Definimos la estructura de cada input que se muestra en el formulario del cálculo
@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


# Listamos los inputs del formulario de AFE, con sus valores por defecto
INPUTS = [
    Inp("contingency_pct", "Contingency", 10, "%"),
    Inp("completion_cost", "Completion cost", 900000, "$"),
    Inp("uncertainty_pct", "Cost uncertainty (P10/P90)", 15, "%"),
    Inp("currency", "Currency", "USD", "", "text"),
    Inp("day_rate", "Rig day-rate (template)", 42000, "$/day"),
]


def context_defaults(ctx) -> dict:
    """Seed completion cost / contingency from the well plan header if present."""
    out = {}
    # Solo sembramos valores si existe un plan de pozo cargado en el contexto
    if ctx.plan:
        if ctx.plan.completion_cost is not None:
            out["completion_cost"] = float(ctx.plan.completion_cost)
        if ctx.plan.contingency_pct is not None:
            out["contingency_pct"] = float(ctx.plan.contingency_pct)
    # Devolvemos los valores sembrados desde el plan (o vacío si no hay plan)
    return out


def generate_rows(params: dict, ctx: WellContext, target: str = "cost-estimate") -> list[dict]:
    """A template AFE Cost Estimate scaled by days and TD — the starting point an
    engineer refines. Categories match the cost-estimate grid."""
    day_rate = float(params.get("day_rate", 42000))
    days = None
    if ctx.time_depth:
        # Tomamos el día máximo planificado del grid de tiempo-profundidad
        days = max((d.get("day") for d in ctx.time_depth if d.get("day") is not None), default=None)
    # Si no hay días planificados, estimamos a partir del TD y una tasa de avance típica
    days = int(days) if days else max(10, round((ctx.td() or 8000) / 650))
    td = ctx.td() or 8000
    # tangibles scale with the casing/hole program size
    # Contamos las sartas de casing (sin el conductor) para escalar bits y cementación
    n_strings = max(1, len([c for c in ctx.casing if (c.get("string") or "").lower() != "conductor"]))
    # Devolvemos las filas plantilla del AFE Cost Estimate, escaladas por días y TD
    return [
        {"category": "Rig", "description": f"Rig day-rate ({days} days)", "qty": days, "unit_cost": round(day_rate)},
        {"category": "Services", "description": "Directional + MWD/LWD", "qty": days, "unit_cost": 18500},
        {"category": "Fluids", "description": "Mud products & engineering", "qty": days, "unit_cost": 11200},
        {"category": "Services", "description": "Supervision, geology & mudlogging", "qty": days, "unit_cost": 14700},
        {"category": "Bits", "description": "Bits (PDC)", "qty": max(2, n_strings), "unit_cost": 21600},
        {"category": "Casing", "description": "Casing & liner tangibles", "qty": 1, "unit_cost": round(td * 37)},
        {"category": "Cementing", "description": "Primary + liner cementing", "qty": n_strings, "unit_cost": 41000},
        {"category": "Logging", "description": "Wireline logging", "qty": 1, "unit_cost": 68000},
        {"category": "Logistics", "description": "Fuel, camp, transport, waste", "qty": days, "unit_cost": 16400},
    ]


def compute(params: dict, ctx: WellContext) -> dict:
    contingency = float(params.get("contingency_pct", 10))
    completion = float(params.get("completion_cost", 900000))
    unc = float(params.get("uncertainty_pct", 15))
    currency = params.get("currency", "USD")

    # roll up cost-estimate grid by category
    by_cat = {}
    base = 0.0
    # Sumamos el grid de cost-estimate por categoría para obtener el costo base
    for r in ctx.cost_estimate:
        amt = (r.get("amount") if r.get("amount") is not None else
               (r.get("qty") or 0) * (r.get("unit_cost") or 0))
        by_cat[r.get("category") or "Other"] = by_cat.get(r.get("category") or "Other", 0.0) + (amt or 0)
        base += (amt or 0)
    # if the estimate grid is empty, fall back to the plan header
    # Si el grid está vacío, usamos el costo de pozo seco del encabezado del plan como respaldo
    if base == 0 and ctx.plan and ctx.plan.dry_hole_cost:
        base = float(ctx.plan.dry_hole_cost)
    # Calculamos el monto de contingencia y el costo de pozo seco (dry-hole)
    contingency_amt = base * contingency / 100.0
    dry_hole = base + contingency_amt
    # Sumamos el costo de completación para obtener el AFE total
    total_afe = dry_hole + completion

    td = ctx.td() or 0
    # Calculamos el costo por pie a partir del dry-hole y el TD
    cost_per_ft = round(dry_hole / td, 1) if td else None
    days = None
    if ctx.time_depth:
        # Tomamos el día máximo planificado del grid de tiempo-profundidad
        days = max((d.get("day") for d in ctx.time_depth if d.get("day") is not None), default=None)

    # P10 / P50 / P90 (cost convention: P10 low, P90 high)
    # Derivamos el rango P10/P50/P90 a partir del AFE total y la incertidumbre declarada
    p50 = total_afe
    p10 = total_afe * (1 - unc / 100.0)
    p90 = total_afe * (1 + unc / 100.0)

    # benchmark cost/ft vs offsets
    bench = []
    # Recolectamos los pozos offset del benchmark que traen costo por pie
    for b in ctx.benchmark:
        if b.get("cost_per_ft"):
            bench.append({"well": b.get("well"), "cost_per_ft": b.get("cost_per_ft"), "days": b.get("days")})
    # Promediamos el costo por pie de los pozos offset para comparar
    avg_bench = round(sum(x["cost_per_ft"] for x in bench) / len(bench), 1) if bench else None

    # time-depth cost curve: distribute dry-hole cost across planned days by depth progress
    curve = []
    # Ordenamos los puntos de tiempo-profundidad que traen día y MD planificado
    tds = sorted([d for d in ctx.time_depth if d.get("day") is not None and d.get("planned_md") is not None], key=lambda x: x["day"])
    max_md = tds[-1]["planned_md"] if tds else td
    # Distribuimos el costo de pozo seco proporcionalmente al avance de profundidad por día
    for d in tds:
        frac = (d["planned_md"] / max_md) if max_md else 0
        curve.append({"day": int(d["day"]), "md": round(d["planned_md"]), "cost": round(dry_hole * frac)})

    # Ordenamos las categorías de costo de mayor a menor monto, con su porcentaje sobre el base
    cat_rows = sorted([{"category": k, "amount": round(v), "pct": round(v / base * 100, 1) if base else 0}
                       for k, v in by_cat.items()], key=lambda x: -x["amount"])
    # Devolvemos el rollup de costos, el rango P10/P50/P90, el benchmark y la curva de costo
    return {
        "currency": currency, "base": round(base), "contingency_pct": contingency, "contingency_amt": round(contingency_amt),
        "dry_hole": round(dry_hole), "completion": round(completion), "total_afe": round(total_afe),
        "cost_per_ft": cost_per_ft, "days": days, "td": round(td),
        "p10": round(p10), "p50": round(p50), "p90": round(p90), "uncertainty": unc,
        "categories": cat_rows, "benchmark": bench, "avg_bench_cpf": avg_bench,
        "cpf_vs_bench": ("below" if (cost_per_ft and avg_bench and cost_per_ft < avg_bench) else "above") if avg_bench else None,
        "curve": curve,
    }
