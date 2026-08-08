"""Cross-well benchmarking — one comparison row per drilling Event, derived
from the same analytics the dashboard uses. Normalised KPIs (days/1000ft,
cost/ft, NPT%) let wells of different depths be compared on the same footing."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hierarchy import Event, Well, Wellbore
from app.services.event_analytics import event_metrics


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or not b:
        return None
    return a / b


def benchmark_row(db: Session, event: Event) -> dict:
    m = event_metrics(db, str(event.id))
    k = m["kpis"]
    wellbore = db.get(Wellbore, event.wellbore_id) if event.wellbore_id else None
    well = db.get(Well, wellbore.well_id) if wellbore else None
    md = k.get("current_md")
    days = k.get("days_elapsed")
    cost = k.get("total_actual_cost")
    return {
        "event_id": str(event.id),
        "well": (well.legal_well_name if well else None) or (event.event_code or "—"),
        "event_code": event.event_code,
        "final_md": md,
        "days": days,
        "cost": cost,
        "npt_pct": k.get("npt_pct"),
        "cost_per_ft": (round(_safe_div(cost, md), 1) if _safe_div(cost, md) is not None else None),
        "days_per_1000ft": (round(_safe_div(days, md / 1000.0), 2) if md else None),
        "avg_ft_per_day": (round(_safe_div(md, days), 1) if _safe_div(md, days) is not None else None),
        "cost_pct": k.get("cost_pct"),
    }


def benchmark_field(db: Session) -> list[dict]:
    """Every event that has at least one daily report, best performers first
    (fewest days per 1000 ft)."""
    events = db.execute(select(Event)).scalars().all()
    rows = []
    for ev in events:
        row = benchmark_row(db, ev)
        if row["days"]:  # only wells with captured operations
            rows.append(row)
    rows.sort(key=lambda r: (r["days_per_1000ft"] is None, r["days_per_1000ft"] or 0))
    return rows
