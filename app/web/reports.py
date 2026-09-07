"""Report generation: a print-optimised Daily Drilling Report and an
End-of-Well summary (both render as clean HTML the browser prints to PDF — no
server-side PDF dependency), plus CSV export of any grid. Read-only."""
import csv  # Para escribir las filas de la grilla en formato CSV
import io  # Para construir el buffer de texto/bytes que se envía como descarga

from fastapi import APIRouter, Depends, HTTPException, Request  # Piezas de FastAPI para rutas, inyección y errores HTTP
from fastapi.responses import HTMLResponse, StreamingResponse  # Respuesta HTML (páginas impresas) y de streaming (descarga CSV)
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.core.deps import get_current_user_web  # Dependencia que resuelve el usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario
from app.db.session import get_db  # Dependencia que entrega la sesión de base de datos
from app.models.capture import CONFIGS, get_config  # Configuraciones de las grillas de captura diaria y su búsqueda por clave
from app.models.planning_capture import get_plan_config  # Búsqueda de configuración de grillas del plan de pozo
from app.repositories.capture_repository import GridRepository  # Repositorio genérico para leer filas de cualquier grilla
from app.repositories.daily_report_repository import DailyReportRepository  # Repositorio del reporte diario
from app.repositories.hierarchy_repository import EventRepository, WellboreRepository, WellRepository  # Repositorios de evento, wellbore y pozo
from app.repositories.npt_repository import NptRepository  # Repositorio de eventos de tiempo no productivo (NPT)
from app.repositories.planning_repository import WellPlanRepository  # Repositorio del plan de pozo
from app.repositories.time_summary_repository import TimeSummaryRowRepository  # Repositorio de filas del resumen de tiempo
from app.services.event_analytics import _duration_hours, event_metrics  # Cálculo de duración entre horas y de métricas agregadas del evento
from app.web.templating import templates  # Motor de templates Jinja compartido

router = APIRouter()  # full paths per route (spans /ops and /planning)


def _context(db: Session, report):
    # Buscamos el evento dueño del reporte
    event = EventRepository(db).get(report.event_id)
    # Buscamos el wellbore del evento (si el evento existe)
    wellbore = WellboreRepository(db).get(event.wellbore_id) if event else None
    # Buscamos el pozo del wellbore (si el wellbore existe)
    well = WellRepository(db).get(wellbore.well_id) if wellbore else None
    # Devolvemos la cadena completa evento/wellbore/pozo para armar el encabezado del reporte
    return event, wellbore, well


@router.get("/ops/reports/{report_id}/print", response_class=HTMLResponse)
async def print_daily_report(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el reporte diario a imprimir
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Resolvemos el evento/wellbore/pozo dueños del reporte
    event, wellbore, well = _context(db, report)

    # Obtenemos las filas del resumen de tiempo del reporte
    ts_rows = TimeSummaryRowRepository(db).list_for_report(report_id)
    # Calculamos la duración en horas de cada fila del resumen de tiempo
    time_summary = [(r, _duration_hours(r.time_from, r.time_to)) for r in ts_rows]
    # Sumamos el total de horas, ignorando las duraciones que no se pudieron calcular
    ts_total = sum(d for _r, d in time_summary if d is not None)
    # Obtenemos los eventos de tiempo no productivo (NPT) del reporte
    npt_rows = NptRepository(db).list_for_report(report_id)

    subsections = []
    for cfg in CONFIGS:
        # Leemos las filas de esta grilla de captura para el reporte
        rows = GridRepository(db, cfg.model).list_for_report(report_id)
        if rows:
            # Solo incluimos las columnas marcadas como visibles en tabla
            cols = [f for f in cfg.fields if f.table]
            subsections.append({"title": cfg.title, "columns": cols, "rows": rows})

    # Renderizamos la vista imprimible del reporte diario con todo el contexto armado
    return templates.TemplateResponse(
        request, "ops/pages/print_daily_report.html",
        {"request": request, "report": report, "event": event, "wellbore": wellbore, "well": well,
         "time_summary": time_summary, "ts_total": ts_total, "npt_rows": npt_rows, "subsections": subsections},
    )


@router.get("/ops/events/{event_id}/end-of-well", response_class=HTMLResponse)
async def end_of_well(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento (campaña) sobre el que se arma el resumen de fin de pozo
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Buscamos el wellbore y el pozo asociados al evento
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    well = WellRepository(db).get(wellbore.well_id) if wellbore else None
    # Buscamos el plan de pozo asociado al evento (si existe)
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Calculamos las métricas agregadas del evento (KPIs)
    metrics = event_metrics(db, event_id)
    # Listamos todos los reportes diarios del evento
    reports = list(DailyReportRepository(db).list_for_event(event_id))
    # Ordenamos los reportes por fecha, tratando fecha nula como la mínima posible
    reports.sort(key=lambda r: (r.report_date or __import__("datetime").date.min))

    # per-day phase summary line
    # Armamos una línea de resumen por día con los datos clave de cada reporte
    day_summary = [{"date": r.report_date, "no": r.report_no,
                    "md": r.md, "tvd": r.tvd,
                    "progress": r.progress, "status": r.current_status} for r in reports]

    # all NPT across the well
    # Recolectamos todos los eventos NPT de todos los reportes del pozo
    npt_all = []
    for r in reports:
        for e in NptRepository(db).list_for_report(r.id):
            npt_all.append((r, e))

    # Renderizamos la página de resumen de fin de pozo con todo el contexto armado
    return templates.TemplateResponse(
        request, "ops/pages/end_of_well.html",
        {"request": request, "event": event, "wellbore": wellbore, "well": well, "plan": plan,
         "metrics": metrics, "kpis": metrics["kpis"], "day_summary": day_summary, "npt_all": npt_all,
         "depth_unit": "ft"},
    )


def _csv_response(cfg, rows, filename):
    # Creamos un buffer de texto en memoria para escribir el CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    # Solo exportamos las columnas marcadas como visibles en tabla
    cols = [f for f in cfg.fields if f.table]
    # Escribimos la fila de encabezados con las etiquetas de cada columna
    writer.writerow([f.label for f in cols])
    for row in rows:
        # Escribimos cada fila, reemplazando valores None por cadena vacía
        writer.writerow(["" if getattr(row, f.name) is None else getattr(row, f.name) for f in cols])
    # Rebobinamos el buffer al inicio antes de leerlo
    buf.seek(0)
    # Devolvemos el CSV como descarga de streaming
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})


@router.get("/ops/reports/{report_id}/capture/{key}/export.csv")
async def export_capture_csv(report_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos la configuración de la grilla de captura por su clave
    cfg = get_config(key)
    if cfg is None:
        raise HTTPException(404)
    # Leemos las filas de esa grilla para el reporte
    rows = GridRepository(db, cfg.model).list_for_report(report_id)
    # Generamos y devolvemos el CSV, usando los primeros 8 caracteres del id del reporte en el nombre
    return _csv_response(cfg, rows, f"{key}_{report_id[:8]}")


@router.get("/planning/events/{event_id}/plan/{key}/export.csv")
async def export_plan_csv(event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos la configuración de la grilla del plan de pozo por su clave
    cfg = get_plan_config(key)
    if cfg is None:
        raise HTTPException(404)
    # Leemos las filas de esa grilla, filtrando por el evento como padre
    rows = GridRepository(db, cfg.model, parent_field="event_id").list_for_parent(event_id)
    # Generamos y devolvemos el CSV, usando los primeros 8 caracteres del id del evento en el nombre
    return _csv_response(cfg, rows, f"plan_{key}_{event_id[:8]}")
