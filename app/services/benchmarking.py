"""Cross-well benchmarking — one comparison row per drilling Event, derived
from the same analytics the dashboard uses. Normalised KPIs (days/1000ft,
cost/ft, NPT%) let wells of different depths be compared on the same footing."""
# Importamos Optional para tipar los valores numéricos que pueden faltar
from typing import Optional

# Importamos select para consultar todos los eventos
from sqlalchemy import select
# Importamos Session para tipar la sesión de base de datos recibida
from sqlalchemy.orm import Session

# Importamos los modelos de la jerarquía para navegar de evento a wellbore y pozo
from app.models.hierarchy import Event, Well, Wellbore
# Importamos event_metrics para reutilizar el mismo cálculo de KPIs que usa el dashboard
from app.services.event_analytics import event_metrics


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    # Evitamos división por cero o por un divisor ausente, devolviendo None en esos casos
    if a is None or not b:
        return None
    return a / b


def benchmark_row(db: Session, event: Event) -> dict:
    # Calculamos las métricas del evento reutilizando la misma lógica del dashboard
    m = event_metrics(db, str(event.id))
    k = m["kpis"]
    # Navegamos desde el evento hacia su wellbore y pozo para obtener el nombre del pozo
    wellbore = db.get(Wellbore, event.wellbore_id) if event.wellbore_id else None
    well = db.get(Well, wellbore.well_id) if wellbore else None
    md = k.get("current_md")
    days = k.get("days_elapsed")
    cost = k.get("total_actual_cost")
    # Armamos la fila de benchmarking con los KPIs normalizados (por pie, por 1000 ft) para comparar pozos de distinta profundidad
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
    # Traemos todos los eventos registrados
    events = db.execute(select(Event)).scalars().all()
    rows = []
    for ev in events:
        row = benchmark_row(db, ev)
        if row["days"]:  # only wells with captured operations
            # Incluimos solo los eventos que ya tienen operación capturada (con días transcurridos)
            rows.append(row)
    # Ordenamos por días/1000ft (mejor desempeño primero), dejando los que no tienen dato al final
    rows.sort(key=lambda r: (r["days_per_1000ft"] is None, r["days_per_1000ft"] or 0))
    # Devolvemos las filas de benchmarking ordenadas
    return rows
