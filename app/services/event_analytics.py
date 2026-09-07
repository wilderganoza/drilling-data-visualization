"""Operational analytics for an Event — turns the captured daily-report and
well-plan data into the series and KPIs the dashboard, alerts and benchmarking
consume. Pure read/aggregate: no mutations. All outputs are plain
dicts/lists/floats, ready to hand straight to a template as JSON."""
from __future__ import annotations

# Importamos datetime para usar date.min como fecha centinela al ordenar reportes sin fecha
import datetime
# Importamos Optional para tipar los valores numéricos que pueden faltar
from typing import Optional

# Importamos Session solo para tipar los parámetros db de cada función
from sqlalchemy.orm import Session

# Importamos el catálogo de grids de captura (daily-report) para resolver cada config por clave
from app.models.capture import CONFIG_BY_KEY
# Importamos DailyReport (usado como referencia de tipo en el módulo)
from app.models.daily_report import DailyReport
# Importamos el catálogo de grids de planeación para resolver cada config por clave
from app.models.planning_capture import PLAN_CONFIG_BY_KEY
# Importamos el repositorio genérico de grids para leer filas de captura y de planeación
from app.repositories.capture_repository import GridRepository
# Importamos el repositorio de reportes diarios para listar los reportes del evento
from app.repositories.daily_report_repository import DailyReportRepository
# Importamos el repositorio de NPT para listar los eventos de tiempo no productivo
from app.repositories.npt_repository import NptRepository
# Importamos el repositorio de planes de pozo para leer el plan asociado al evento
from app.repositories.planning_repository import WellPlanRepository
# Importamos el repositorio de filas de Time Summary para la distribución de tiempo (P/NPT/SC)
from app.repositories.time_summary_repository import TimeSummaryRowRepository


def _f(v) -> Optional[float]:
    # Convertimos a float solo si el valor no es None
    return float(v) if v is not None else None


def _duration_hours(time_from, time_to) -> Optional[float]:
    # Si falta alguna de las dos horas, no podemos calcular una duración
    if not time_from or not time_to:
        return None
    try:
        # Parseamos ambas horas en formato "HH:MM"
        h1, m1 = (int(x) for x in str(time_from).split(":"))
        h2, m2 = (int(x) for x in str(time_to).split(":"))
    except ValueError:
        # Si el formato no es válido, no podemos calcular la duración
        return None
    minutes = (h2 * 60 + m2) - (h1 * 60 + m1)
    # Si la hora de fin es menor que la de inicio, asumimos que cruzó la medianoche
    if minutes < 0:
        minutes += 24 * 60
    return minutes / 60.0


def _capture_rows(db: Session, key: str, report_id):
    # Resolvemos la config del grid de captura por su clave y devolvemos sus filas para el reporte
    cfg = CONFIG_BY_KEY[key]
    return GridRepository(db, cfg.model).list_for_report(report_id)


def _plan_rows(db: Session, key: str, event_id):
    # Resolvemos la config del grid de planeación por su clave y devolvemos sus filas para el evento
    cfg = PLAN_CONFIG_BY_KEY[key]
    return GridRepository(db, cfg.model, parent_field="event_id").list_for_parent(event_id)


def event_metrics(db: Session, event_id: str) -> dict:
    # Cargamos todos los reportes diarios del evento y los ordenamos por fecha (sin fecha va al inicio)
    reports = list(DailyReportRepository(db).list_for_event(event_id))
    reports.sort(key=lambda r: (r.report_date or datetime.date.min))
    plan = WellPlanRepository(db).get_by_event(event_id)

    # --- Depth vs Days (plan vs actual) ---
    # Armamos la curva de profundidad real (MD/TVD) por día
    actual_depth = []
    for i, r in enumerate(reports):
        day = r.report_no if r.report_no is not None else i + 1
        actual_depth.append({"day": day, "md": _f(r.md), "tvd": _f(r.tvd)})
    # Armamos la curva de profundidad planeada a partir del grid time-depth
    plan_td = _plan_rows(db, "time-depth", event_id)
    planned_depth = [{"day": p.day, "md": _f(p.planned_md)} for p in plan_td if p.day is not None]
    planned_depth.sort(key=lambda x: x["day"])

    # --- Cost: cumulative actual vs AFE budget ---
    # Acumulamos el costo diario capturado para obtener la serie de costo acumulado
    cost_series = []
    cum = 0.0
    for i, r in enumerate(reports):
        day = r.report_no if r.report_no is not None else i + 1
        daily = sum((_f(c.amount) or 0.0) for c in _capture_rows(db, "cost", r.id))
        cum += daily
        cost_series.append({"day": day, "daily": round(daily, 2), "cumulative": round(cum, 2)})
    budget_total = _f(plan.budget_total) if plan else None
    plan_cost_est = sum((_f(c.amount) or 0.0) for c in _plan_rows(db, "cost-estimate", event_id))
    total_actual_cost = round(cum, 2)

    # --- Time distribution (P / NPT / SC) from Time Summary durations ---
    # Sumamos las horas de Time Summary por clase de operación (Productivo/NPT/No programado)
    dist = {"P": 0.0, "NPT": 0.0, "SC": 0.0}
    ts_cfg_rows_total = 0
    for r in reports:
        for row in _capture_rows_ts(db, r.id):
            dur = _duration_hours(row.time_from, row.time_to)
            if dur is None:
                continue
            ts_cfg_rows_total += 1
            cls = (row.op_class or "P").upper()
            dist[cls if cls in dist else "P"] += dur
    total_time = sum(dist.values())
    time_distribution = [
        {"label": "Productive", "key": "P", "hours": round(dist["P"], 2)},
        {"label": "NPT", "key": "NPT", "hours": round(dist["NPT"], 2)},
        {"label": "Unscheduled", "key": "SC", "hours": round(dist["SC"], 2)},
    ]

    # --- NPT detail from NptEvent records (by type/category) ---
    # Agrupamos las horas de NPT por tipo/categoría a partir de los registros de NptEvent
    npt_by_type: dict[str, float] = {}
    npt_total = 0.0
    npt_count = 0
    npt_repo = NptRepository(db)
    for r in reports:
        for e in npt_repo.list_for_report(r.id):
            hrs = _f(e.gross_hours) or 0.0
            npt_total += hrs
            npt_count += 1
            key = e.npt_type or "Unspecified"
            npt_by_type[key] = npt_by_type.get(key, 0.0) + hrs
    npt_by_category = sorted(
        [{"category": k, "hours": round(v, 2)} for k, v in npt_by_type.items()],
        key=lambda x: -x["hours"],
    )
    npt_pct = round((dist["NPT"] / total_time) * 100, 1) if total_time else 0.0

    # --- Trajectory: actual surveys vs planned directional ---
    # Armamos la trayectoria real a partir de los surveys capturados en cada reporte
    actual_traj = []
    for r in reports:
        for s in _capture_rows(db, "surveys", r.id):
            if s.md is not None and s.tvd is not None:
                actual_traj.append({"md": _f(s.md), "tvd": _f(s.tvd), "ns": _f(s.ns), "ew": _f(s.ew),
                                    "vs": _horiz(s.ns, s.ew)})
    actual_traj.sort(key=lambda x: x["md"])
    # Armamos la trayectoria planeada a partir del grid directional-plan
    plan_traj = []
    for s in _plan_rows(db, "directional-plan", event_id):
        if s.md is not None and s.tvd is not None:
            plan_traj.append({"md": _f(s.md), "tvd": _f(s.tvd), "ns": _f(s.ns), "ew": _f(s.ew),
                              "vs": _horiz(s.ns, s.ew)})
    plan_traj.sort(key=lambda x: x["md"])

    # --- KPI roll-up ---
    # Tomamos el último reporte para conocer la profundidad actual
    last = reports[-1] if reports else None
    current_md = _f(last.md) if last else None
    current_tvd = _f(last.tvd) if last else None
    days_elapsed = len(reports)
    planned_days = _f(plan.est_days) if plan else (max((p["day"] for p in planned_depth), default=None))
    planned_final_md = _f(plan.authorized_md) if plan and plan.authorized_md is not None else (
        planned_depth[-1]["md"] if planned_depth else None)
    # days ahead(-)/behind(+): while still drilling, compare elapsed days to the
    # planned day for the current MD; once the planned final depth is reached the
    # depth curve plateaus (logging/casing/completion), so compare total days.
    # Calculamos si vamos adelantados(-) o atrasados(+) respecto al plan
    reached_td = bool(current_md and planned_final_md and current_md >= planned_final_md)
    if reached_td and planned_days is not None:
        # Si ya llegamos a la profundidad final planeada, comparamos días totales
        days_delta = round(days_elapsed - planned_days, 1)
    else:
        # Si aún estamos perforando, comparamos contra el día planeado para el MD actual
        plan_day_at_md = _plan_day_for_md(planned_depth, current_md)
        days_delta = (round(days_elapsed - plan_day_at_md, 1) if plan_day_at_md is not None else None)

    # Armamos el diccionario de KPIs consolidados para el dashboard
    kpis = {
        "days_elapsed": days_elapsed,
        "planned_days": planned_days,
        "current_md": current_md,
        "current_tvd": current_tvd,
        "planned_final_md": planned_final_md,
        "pct_complete": (round(current_md / planned_final_md * 100, 1) if current_md and planned_final_md else None),
        "total_actual_cost": total_actual_cost,
        "budget_total": budget_total,
        "plan_cost_estimate": round(plan_cost_est, 2) if plan_cost_est else None,
        "cost_pct": (round(total_actual_cost / budget_total * 100, 1) if budget_total else None),
        "npt_hours": round(npt_total, 2),
        "npt_events": npt_count,
        "npt_pct": npt_pct,
        "days_delta": days_delta,  # +behind / -ahead of plan
        "productive_hours": round(dist["P"], 2),
        "total_time_hours": round(total_time, 2),
    }

    # Devolvemos todas las series y KPIs listos para el dashboard/reportes
    return {
        "kpis": kpis,
        "actual_depth": actual_depth,
        "planned_depth": planned_depth,
        "cost_series": cost_series,
        "budget_total": budget_total,
        "time_distribution": time_distribution,
        "npt_by_category": npt_by_category,
        "actual_traj": actual_traj,
        "plan_traj": plan_traj,
    }


def _capture_rows_ts(db: Session, report_id):
    # Devolvemos las filas de Time Summary del reporte
    return TimeSummaryRowRepository(db).list_for_report(report_id)


def _horiz(ns, ew) -> Optional[float]:
    # Calculamos el desplazamiento horizontal (vertical section) a partir de NS/EW
    if ns is None or ew is None:
        return None
    return round((float(ns) ** 2 + float(ew) ** 2) ** 0.5, 2)


def _plan_day_for_md(planned_depth: list[dict], md: Optional[float]) -> Optional[float]:
    """Interpolate which planned day corresponds to a given actual MD."""
    # Si no hay MD actual o no hay suficientes puntos planeados, no podemos interpolar
    if md is None or len(planned_depth) < 2:
        return None
    pts = [(p["day"], p["md"]) for p in planned_depth if p["md"] is not None]
    if not pts:
        return None
    # Si el MD actual es menor o igual al primer punto planeado, devolvemos ese primer día
    if md <= pts[0][1]:
        return float(pts[0][0])
    # Interpolamos linealmente entre los dos puntos planeados que rodean el MD actual
    for (d1, m1), (d2, m2) in zip(pts, pts[1:]):
        if m1 <= md <= m2 and m2 != m1:
            return round(d1 + (d2 - d1) * (md - m1) / (m2 - m1), 2)
    # Si el MD actual supera el último punto planeado, devolvemos el último día
    return float(pts[-1][0])
