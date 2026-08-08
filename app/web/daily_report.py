"""Daily Operations Report shell, General subsection, and Time Summary grid.
Only these two subsections are active for now — the remaining 11+ (Fluids,
Mud Inventory, Daily Cost, Personnel, Safety, Hole Sections, Drillstrings,
Surveys, LOT/FIT, Wellbore Obstructions, Remarks...) land as their own
modules per the build sequence, reusing this same tab shell."""
# Importamos utilidades de fecha para parsear los campos de formulario tipo fecha
from datetime import date, datetime
# Importamos Optional para tipar los parámetros de formulario que pueden venir vacíos
from typing import Optional

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias, leer formularios y lanzar errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos el tipo de respuesta HTML usado por todas las rutas de este módulo
from fastapi.responses import HTMLResponse
# Importamos la sesión de SQLAlchemy para tipar la dependencia de base de datos
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado desde la cookie de sesión
from app.core.deps import get_current_user_web
# Importamos el modelo User y el helper utcnow (hora UTC actual) para los timestamps de auditoría
from app.models.legacy import User, utcnow
# Importamos la dependencia que nos entrega una sesión de base de datos por request
from app.db.session import get_db
# Importamos el helper de permisos que bloquea una ruta si el usuario no tiene el rol requerido
from app.core.permissions import require_ops_role
# Importamos el enum de roles operativos usados en los chequeos de permisos
from app.core.ops_roles import OpsRole
# Importamos el repositorio de reportes diarios
from app.repositories.daily_report_repository import DailyReportRepository
# Importamos los repositorios de Event y Wellbore para resolver el contexto del reporte
from app.repositories.hierarchy_repository import EventRepository, WellboreRepository
# Importamos los repositorios del catálogo de pasos y de las filas del resumen de tiempo
from app.repositories.time_summary_repository import StepCatalogRepository, TimeSummaryRowRepository
# Importamos el servicio que arrastra (carry-over) las líneas de costo recurrentes al crear un nuevo reporte
from app.services.carry_over import carry_over_costs
# Importamos el motor de validación de la subsección General
from app.services.validation_engine import validate_general
# Importamos la configuración de las subsecciones de captura (tabs) del reporte
from app.web.capture import CAPTURE_CONFIGS
# Importamos el helper que arma la cadena de "breadcrumb" (árbol abierto/activo) para un evento
from app.web.tree import chain_for_event
# Importamos el motor de templates compartido por toda la app
from app.web.templating import templates

# Creamos el router de Operaciones (Daily Report vive bajo /ops)
router = APIRouter(prefix="/ops")

# Definimos la dependencia que exige rol de Admin u Office Engineer para poder editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
# Definimos la dependencia que exige rol de Admin para aprobar/reabrir reportes
CAN_APPROVE = require_ops_role(OpsRole.ADMIN)


# Verificamos que el reporte no esté bloqueado (aprobado) antes de permitir cualquier edición
def ensure_unlocked(report) -> None:
    """Approved reports are locked — reject edits to preserve the audit record."""
    # Si el reporte existe y está marcado como bloqueado, rechazamos la edición con un 423
    if report is not None and getattr(report, "is_locked", False):
        raise HTTPException(status_code=423, detail="Report is approved and locked; reopen it to edit.")


# Normalizamos un campo de texto de formulario: recortamos espacios y devolvemos None si queda vacío
def _opt(value: Optional[str]) -> Optional[str]:
    return value.strip() if value and value.strip() else None


# Convertimos un campo de texto de formulario a fecha, devolviendo None si viene vacío
def _opt_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# Convertimos un campo de texto de formulario a número flotante, devolviendo None si viene vacío
def _opt_num(value: Optional[str]) -> Optional[float]:
    return float(value) if value and value.strip() else None


# Calculamos la duración en horas entre dos horas "HH:MM" de una fila del resumen de tiempo
def _duration_hours(time_from: Optional[str], time_to: Optional[str]) -> Optional[float]:
    # Si falta cualquiera de las dos horas, no podemos calcular la duración
    if not time_from or not time_to:
        return None
    try:
        # Descomponemos cada hora en horas y minutos
        h1, m1 = (int(x) for x in time_from.split(":"))
        h2, m2 = (int(x) for x in time_to.split(":"))
    except ValueError:
        # Si el formato no es válido, no calculamos duración
        return None
    # Calculamos la diferencia en minutos entre ambas horas
    minutes = (h2 * 60 + m2) - (h1 * 60 + m1)
    if minutes < 0:
        minutes += 24 * 60  # crosses midnight (e.g. 23:00 -> 01:00)
    # Devolvemos la duración en horas, redondeada a 2 decimales
    return round(minutes / 60, 2)


# Emparejamos cada fila del resumen de tiempo con su duración calculada
def _rows_with_duration(rows):
    return [(row, _duration_hours(row.time_from, row.time_to)) for row in rows]


# ---------------------------------------------------------------------------
# Report list + create
# ---------------------------------------------------------------------------

@router.get("/events/{event_id}/reports", response_class=HTMLResponse)
async def report_list(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento (campaña operativa) al que pertenecen los reportes
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Obtenemos el wellbore asociado al evento, para mostrarlo en el contexto de la página
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Listamos todos los reportes diarios de este evento
    reports = DailyReportRepository(db).list_for_event(event_id)
    # Calculamos la cadena de nodos para el árbol lateral (abiertos/activo)
    chain = chain_for_event(event)
    return templates.TemplateResponse(
        request, "ops/pages/daily_report_list.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore, "reports": reports,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


@router.post("/events/{event_id}/reports", response_class=HTMLResponse)
async def create_report(
    request: Request, event_id: str,
    report_date: str = Form(...), report_no: str = Form(""), description: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Verificamos que el evento padre exista
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    repo = DailyReportRepository(db)
    # Creamos el reporte diario con los campos normalizados
    report = repo.create(
        event_id=event_id, report_date=_opt_date(report_date),
        report_no=int(report_no) if report_no.strip() else None,
        description=_opt(description), created_by=current_user.id,
    )
    carry_over_costs(db, report, created_by=current_user.id)  # roll forward recurring cost lines
    db.commit()
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Refrescamos el listado de reportes del evento
    reports = repo.list_for_event(event_id)
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_list_section.html",
        {"request": request, "event": event, "wellbore": wellbore, "reports": reports},
    )


# ---------------------------------------------------------------------------
# Report shell + General
# ---------------------------------------------------------------------------

@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el reporte solicitado
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Resolvemos el evento y el wellbore asociados para dar contexto a la página shell
    event = EventRepository(db).get(report.event_id)
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    chain = chain_for_event(event)
    return templates.TemplateResponse(
        request, "ops/pages/daily_report_detail.html",
        {"request": request, "current_user": current_user, "report": report, "event": event, "wellbore": wellbore,
         "violations": [], "capture_configs": CAPTURE_CONFIGS, "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


@router.get("/reports/{report_id}/general", response_class=HTMLResponse)
async def general_tab(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    event = EventRepository(db).get(report.event_id)
    # Renderizamos el parcial de la subsección General sin violaciones (aún no se validó nada en un GET)
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_general.html",
        {"request": request, "report": report, "event": event, "violations": [], "saved": None},
    )


@router.put("/reports/{report_id}/general", response_class=HTMLResponse)
async def update_general(
    request: Request, report_id: str,
    supervisor: str = Form(""), engineer: str = Form(""), geologist: str = Form(""),
    dol: str = Form(""), dfs: str = Form(""), previous_md: str = Form(""), md: str = Form(""),
    tvd: str = Form(""), rotating_hrs: str = Form(""), sliding_hrs: str = Form(""), hole_size: str = Form(""),
    formation: str = Form(""), lithology: str = Form(""), current_status: str = Form(""),
    summary_24hr: str = Form(""), forecast_24hr: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Rechazamos la edición si el reporte ya fue aprobado y está bloqueado
    ensure_unlocked(report)

    # Armamos el diccionario de datos normalizados a partir del formulario
    data = dict(
        supervisor=_opt(supervisor), engineer=_opt(engineer), geologist=_opt(geologist),
        dol=_opt_num(dol), dfs=_opt_num(dfs), previous_md=_opt_num(previous_md), md=_opt_num(md), tvd=_opt_num(tvd),
        rotating_hrs=_opt_num(rotating_hrs), sliding_hrs=_opt_num(sliding_hrs), hole_size=_opt_num(hole_size),
        formation=_opt(formation), lithology=_opt(lithology), current_status=_opt(current_status),
        summary_24hr=_opt(summary_24hr), forecast_24hr=_opt(forecast_24hr),
    )
    # Ejecutamos el motor de validación sobre los datos ingresados
    violations = validate_general(db, data, report=report)
    # Filtramos solo las violaciones de nivel obligatorio (las de "notify" no bloquean el guardado)
    mandatory_violations = [v for v in violations if v.level == "mandatory"]

    if not mandatory_violations:
        # Calculamos el progreso (avance de profundidad) si tenemos ambos valores de MD
        progress = None
        if data["md"] is not None and data["previous_md"] is not None:
            progress = data["md"] - data["previous_md"]
        # "Complete" tracks the mandatory fields only — notify-level warnings
        # (e.g. missing Current Status) are surfaced but shouldn't block the
        # section from being marked done, same as OpenWells' rosado/blanco
        # (mandatory/notify) distinction.
        # Guardamos los datos validados, marcando la subsección General como completa
        DailyReportRepository(db).update(report, **data, progress=progress, general_complete=True, updated_by=current_user.id)
        db.commit()
    else:
        # Don't persist invalid data. Detach the row from the session before
        # mutating it for re-render, so these edits are never picked up by
        # SQLAlchemy's autoflush on the query below (relying on "close()
        # without commit() implicitly rolls back" would work too, but is an
        # easy thing to get wrong later — expunge makes "not saved" explicit).
        # Desvinculamos el objeto de la sesión para poder mutarlo sin que SQLAlchemy lo persista
        db.expunge(report)
        # Aplicamos los valores ingresados solo en memoria, para que el usuario vea lo que escribió al re-renderizar
        for key, value in data.items():
            setattr(report, key, value)

    event = EventRepository(db).get(report.event_id)
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_general.html",
        {"request": request, "report": report, "event": event, "violations": violations, "saved": not mandatory_violations},
    )


# ---------------------------------------------------------------------------
# Time Summary
# ---------------------------------------------------------------------------

# Armamos la respuesta HTML del grid de resumen de tiempo, reutilizada por todas las rutas de esta sección
def _time_summary_response(request: Request, db: Session, report_id: str) -> HTMLResponse:
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Obtenemos las filas del reporte junto con su duración calculada
    rows = _rows_with_duration(TimeSummaryRowRepository(db).list_for_report(report_id))
    # Combinamos el catálogo de pasos de los perfiles horizontal y vertical
    step_catalog = StepCatalogRepository(db).list_for_profile("horizontal") + StepCatalogRepository(db).list_for_profile("vertical")
    # Sumamos las horas totales de las filas que tienen duración válida
    total_hours = sum(duration for _row, duration in rows if duration is not None)
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_time_summary.html",
        {"request": request, "report": report, "rows": rows, "step_catalog": step_catalog, "total_hours": total_hours},
    )


@router.get("/reports/{report_id}/time-summary", response_class=HTMLResponse)
async def time_summary_tab(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Delegamos en el helper compartido que arma la respuesta del grid
    return _time_summary_response(request, db, report_id)


@router.post("/reports/{report_id}/time-summary/rows", response_class=HTMLResponse)
async def create_time_summary_row(
    request: Request, report_id: str,
    time_from: str = Form(""), time_to: str = Form(""), step_no: str = Form(""),
    phase: str = Form(""), op_class: str = Form(""), op_code: str = Form(""), operation_detail: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Rechazamos la edición si el reporte ya está bloqueado
    ensure_unlocked(report)
    repo = TimeSummaryRowRepository(db)
    # Creamos la fila al final del orden actual, normalizando los campos del formulario
    repo.create(
        daily_report_id=report_id, sort_order=repo.next_sort_order(report_id),
        time_from=_opt(time_from), time_to=_opt(time_to), step_no=int(step_no) if step_no.strip() else None,
        phase=_opt(phase), op_class=_opt(op_class), op_code=_opt(op_code), operation_detail=_opt(operation_detail),
        created_by=current_user.id,
    )
    db.commit()
    return _time_summary_response(request, db, report_id)


@router.put("/reports/{report_id}/time-summary/rows/{row_id}", response_class=HTMLResponse)
async def update_time_summary_row(
    request: Request, report_id: str, row_id: str,
    time_from: str = Form(""), time_to: str = Form(""), step_no: str = Form(""),
    phase: str = Form(""), op_class: str = Form(""), op_code: str = Form(""), operation_detail: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    repo = TimeSummaryRowRepository(db)
    row = repo.get(row_id)
    # Verificamos que la fila exista y pertenezca al reporte indicado en la URL
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    # Rechazamos la edición si el reporte padre está bloqueado
    ensure_unlocked(DailyReportRepository(db).get(report_id))
    # Actualizamos la fila con los valores normalizados del formulario
    repo.update(
        row, time_from=_opt(time_from), time_to=_opt(time_to), step_no=int(step_no) if step_no.strip() else None,
        phase=_opt(phase), op_class=_opt(op_class), op_code=_opt(op_code), operation_detail=_opt(operation_detail),
        updated_by=current_user.id,
    )
    db.commit()
    return _time_summary_response(request, db, report_id)


@router.delete("/reports/{report_id}/time-summary/rows/{row_id}", response_class=HTMLResponse)
async def delete_time_summary_row(request: Request, report_id: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = TimeSummaryRowRepository(db)
    row = repo.get(row_id)
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    ensure_unlocked(DailyReportRepository(db).get(report_id))
    # Eliminamos la fila encontrada
    repo.delete(row)
    db.commit()
    return _time_summary_response(request, db, report_id)


@router.post("/reports/{report_id}/time-summary/rows/{row_id}/move", response_class=HTMLResponse)
async def move_time_summary_row(request: Request, report_id: str, row_id: str, direction: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = TimeSummaryRowRepository(db)
    row = repo.get(row_id)
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    ensure_unlocked(DailyReportRepository(db).get(report_id))
    # Movemos la fila un puesto hacia arriba o abajo según la dirección indicada
    repo.move(row, direction)
    db.commit()
    return _time_summary_response(request, db, report_id)


# ---------------------------------------------------------------------------
# Approval workflow (Draft -> Submitted -> Approved) + audit
# ---------------------------------------------------------------------------

# Armamos la respuesta HTML del panel de estado/aprobación, reutilizada por todas las rutas de esta sección
def _status_response(request: Request, db: Session, report_id: str) -> HTMLResponse:
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Resolvemos los usuarios involucrados (quién envió, quién aprobó, quién creó) para mostrarlos en la auditoría
    submitter = db.get(User, report.submitted_by) if report.submitted_by else None
    approver = db.get(User, report.approved_by) if report.approved_by else None
    creator = db.get(User, report.created_by) if report.created_by else None
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_status.html",
        {"request": request, "report": report, "submitter": submitter, "approver": approver, "creator": creator},
    )


@router.get("/reports/{report_id}/status", response_class=HTMLResponse)
async def report_status(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Delegamos en el helper compartido que arma la respuesta del panel de estado
    return _status_response(request, db, report_id)


@router.post("/reports/{report_id}/submit", response_class=HTMLResponse)
async def submit_report(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Evitamos volver a enviar un reporte que ya fue aprobado
    if report.workflow_status == "Approved":
        raise HTTPException(409, "Already approved.")
    # Marcamos el reporte como enviado y registramos quién y cuándo lo envió
    report.workflow_status = "Submitted"
    report.submitted_at = utcnow()
    report.submitted_by = current_user.id
    db.commit()
    return _status_response(request, db, report_id)


@router.post("/reports/{report_id}/approve", response_class=HTMLResponse)
async def approve_report(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_APPROVE)):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Marcamos el reporte como aprobado, registramos quién y cuándo, y lo bloqueamos para conservar el registro de auditoría
    report.workflow_status = "Approved"
    report.approved_at = utcnow()
    report.approved_by = current_user.id
    report.is_locked = True
    db.commit()
    return _status_response(request, db, report_id)


@router.post("/reports/{report_id}/reopen", response_class=HTMLResponse)
async def reopen_report(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_APPROVE)):
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Regresamos el reporte a borrador, lo desbloqueamos y limpiamos los datos de aprobación
    report.workflow_status = "Draft"
    report.is_locked = False
    report.approved_at = None
    report.approved_by = None
    db.commit()
    return _status_response(request, db, report_id)
