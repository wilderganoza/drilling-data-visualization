"""AFE builder — authorization for expenditure.

Rolls up the detailed cost-estimate program grid by category, adds contingency
and the completion cost to a dry-hole/total AFE, derives cost-per-foot and
days, benchmarks cost/ft against the offset wells, produces a P10/P50/P90 range
from a stated uncertainty, and lays out a time–depth cost curve (cumulative
spend vs planned day) for the classic AFE curve."""
from dataclasses import dataclass

from app.services.engineering.context import WellContext

PROGRAM_TARGETS = ["cost-estimate"]  # generate a template AFE Cost Estimate


@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


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
    if ctx.plan:
        if ctx.plan.completion_cost is not None:
            out["completion_cost"] = float(ctx.plan.completion_cost)
        if ctx.plan.contingency_pct is not None:
            out["contingency_pct"] = float(ctx.plan.contingency_pct)
    return out


def generate_rows(params: dict, ctx: WellContext, target: str = "cost-estimate") -> list[dict]:
    """A template AFE Cost Estimate scaled by days and TD — the starting point an
    engineer refines. Categories match the cost-estimate grid."""
    day_rate = float(params.get("day_rate", 42000))
    days = None
    if ctx.time_depth:
        days = max((d.get("day") for d in ctx.time_depth if d.get("day") is not None), default=None)
    days = int(days) if days else max(10, round((ctx.td() or 8000) / 650))
    td = ctx.td() or 8000
    # tangibles scale with the casing/hole program size
    n_strings = max(1, len([c for c in ctx.casing if (c.get("string") or "").lower() != "conductor"]))
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
    for r in ctx.cost_estimate:
        amt = (r.get("amount") if r.get("amount") is not None else
               (r.get("qty") or 0) * (r.get("unit_cost") or 0))
        by_cat[r.get("category") or "Other"] = by_cat.get(r.get("category") or "Other", 0.0) + (amt or 0)
        base += (amt or 0)
    # if the estimate grid is empty, fall back to the plan header
    if base == 0 and ctx.plan and ctx.plan.dry_hole_cost:
        base = float(ctx.plan.dry_hole_cost)
    contingency_amt = base * contingency / 100.0
    dry_hole = base + contingency_amt
    total_afe = dry_hole + completion

    td = ctx.td() or 0
    cost_per_ft = round(dry_hole / td, 1) if td else None
    days = None
    if ctx.time_depth:
        days = max((d.get("day") for d in ctx.time_depth if d.get("day") is not None), default=None)

    # P10 / P50 / P90 (cost convention: P10 low, P90 high)
    p50 = total_afe
    p10 = total_afe * (1 - unc / 100.0)
    p90 = total_afe * (1 + unc / 100.0)

    # benchmark cost/ft vs offsets
    bench = []
    for b in ctx.benchmark:
        if b.get("cost_per_ft"):
            bench.append({"well": b.get("well"), "cost_per_ft": b.get("cost_per_ft"), "days": b.get("days")})
    avg_bench = round(sum(x["cost_per_ft"] for x in bench) / len(bench), 1) if bench else None

    # time-depth cost curve: distribute dry-hole cost across planned days by depth progress
    curve = []
    tds = sorted([d for d in ctx.time_depth if d.get("day") is not None and d.get("planned_md") is not None], key=lambda x: x["day"])
    max_md = tds[-1]["planned_md"] if tds else td
    for d in tds:
        frac = (d["planned_md"] / max_md) if max_md else 0
        curve.append({"day": int(d["day"]), "md": round(d["planned_md"]), "cost": round(dry_hole * frac)})

    cat_rows = sorted([{"category": k, "amount": round(v), "pct": round(v / base * 100, 1) if base else 0}
                       for k, v in by_cat.items()], key=lambda x: -x["amount"])
    return {
        "currency": currency, "base": round(base), "contingency_pct": contingency, "contingency_amt": round(contingency_amt),
        "dry_hole": round(dry_hole), "completion": round(completion), "total_afe": round(total_afe),
        "cost_per_ft": cost_per_ft, "days": days, "td": round(td),
        "p10": round(p10), "p50": round(p50), "p90": round(p90), "uncertainty": unc,
        "categories": cat_rows, "benchmark": bench, "avg_bench_cpf": avg_bench,
        "cpf_vs_bench": ("below" if (cost_per_ft and avg_bench and cost_per_ft < avg_bench) else "above") if avg_bench else None,
        "curve": curve,
    }
