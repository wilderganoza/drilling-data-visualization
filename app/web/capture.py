"""Routes for every spec-driven capture subsection (Casing, Cementing,
Surveys, Drillstring/BHA, Daily Cost, Pipe Tally, Fluids, Personnel, Safety,
Remarks). One route factory reads each subsection's `GridConfig` and mounts
the same 5 endpoints Time Summary has — tab / create / update / delete / move
— so adding a subsection is a data edit in app/ops/models/capture.py, not new
route code. Form values are read generically via `request.form()` and coerced
per each field's declared `kind`."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request  # Router y utilidades de FastAPI para las rutas web
from fastapi.responses import HTMLResponse  # Tipo de respuesta HTML para las rutas
from starlette.datastructures import FormData  # Tipado de los datos crudos que llegan desde un formulario

from app.core.deps import get_current_user_web  # Dependencia que exige un usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario autenticado
from app.db.session import get_db  # Dependencia que nos entrega una sesión de base de datos por request
from app.core.permissions import require_ops_role, has_ops_role  # Utilidades para exigir o verificar roles de operaciones
from app.core.ops_roles import OpsRole  # Enumeración de roles de operaciones (admin, ingeniero de oficina, etc.)
from app.models.capture import CONFIGS, GridConfig, compute_values, get_config  # Configuración y cálculo genérico de cada grilla de captura
from app.models.daily_report import DailyReport  # Modelo del reporte diario, usado para el tie-in de surveys
from app.repositories.capture_repository import GridRepository  # Repositorio genérico para las filas de cualquier grilla de captura
from app.repositories.daily_report_repository import DailyReportRepository  # Repositorio para consultar reportes diarios
from app.services.survey_calc import recompute_survey  # Servicio que recalcula la trayectoria (mínima curvatura) de los surveys
from app.web.templating import templates  # Motor de plantillas Jinja compartido
from sqlalchemy import select  # Constructor de consultas SQLAlchemy 2.0 style
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy inyectada

router = APIRouter(prefix="/ops")

# Definimos la dependencia que exige que el usuario sea admin o ingeniero de oficina para poder editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)


def _coerce(kind: str, raw):
    # Limpiamos espacios si el valor crudo es un string
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    # Un valor vacío lo tratamos como ausente (None)
    if raw in (None, ""):
        return None
    # Convertimos a número decimal cuando el campo es de tipo "number"
    if kind == "number":
        try:
            return float(raw)
        except ValueError:
            return None
    # Convertimos a entero cuando el campo es de tipo "int" (pasando por float para tolerar "3.0")
    if kind == "int":
        try:
            return int(float(raw))
        except ValueError:
            return None
    # Para el resto de tipos (texto, textarea, select, hora) devolvemos el valor tal cual
    return raw  # text | textarea | select | time


def _parse(cfg: GridConfig, form: FormData) -> dict:
    # Coercionamos cada campo del formulario según el tipo declarado en la configuración de la grilla
    values = {f.name: _coerce(f.kind, form.get(f.name)) for f in cfg.fields if f.form}
    # Aplicamos los cálculos derivados propios de esta grilla (por ejemplo totales o campos calculados)
    return compute_values(cfg, values)


def _response(request: Request, db: Session, cfg: GridConfig, report_id: str, can_edit: bool = True) -> HTMLResponse:
    # Buscamos el reporte diario al que pertenece esta grilla
    report = DailyReportRepository(db).get(report_id)
    # Si el reporte no existe, no podemos renderizar la grilla
    if report is None:
        raise HTTPException(404)
    # Obtenemos todas las filas de esta subsección para el reporte
    rows = GridRepository(db, cfg.model).list_for_report(report_id)
    # Renderizamos el fragmento genérico de grilla, deshabilitando edición si el reporte está bloqueado
    return templates.TemplateResponse(
        request, "ops/partials/grid.html",
        {"request": request, "report": report, "cfg": cfg, "rows": rows, "can_edit": can_edit and not getattr(report, "is_locked", False),
         "base_url": f"/ops/reports/{report_id}/capture/{cfg.key}", "content_id": "capture-tab-content"},
    )


def _require_cfg(key: str) -> GridConfig:
    # Buscamos la configuración de la subsección solicitada
    cfg = get_config(key)
    # Si la clave no corresponde a ninguna subsección conocida, devolvemos 404
    if cfg is None:
        raise HTTPException(404)
    return cfg


def _ensure_report_unlocked(db: Session, report_id: str) -> None:
    # Buscamos el reporte para verificar su estado de bloqueo
    rep = DailyReportRepository(db).get(report_id)
    # Si el reporte está aprobado y bloqueado, no permitimos modificarlo
    if rep is not None and getattr(rep, "is_locked", False):
        raise HTTPException(status_code=423, detail="Report is approved and locked; reopen it to edit.")


def _tie_in_station(db: Session, cfg: GridConfig, report_id: str):
    """Deepest survey station from earlier reports of the same event, used to
    keep the minimum-curvature calc continuous across daily reports."""
    # Buscamos el reporte actual para conocer su evento y fecha
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        return None
    # Buscamos todos los reportes previos del mismo evento (fecha anterior al reporte actual)
    prior = db.execute(
        select(DailyReport)
        .where(DailyReport.event_id == report.event_id, DailyReport.report_date < report.report_date)
    ).scalars().all()
    best = None
    # Recorremos los reportes previos buscando la estación de survey más profunda (mayor MD)
    for rep in prior:
        for st in GridRepository(db, cfg.model).list_for_report(rep.id):
            if st.md is not None and (best is None or float(st.md) > float(best.md)):
                best = st
    # Devolvemos la estación más profunda encontrada, o None si no hay ninguna
    return best


def _recompute(db: Session, cfg: GridConfig, report_id: str) -> None:
    """Refresh whole-list derived columns after any change (surveys only)."""
    # Solo recalculamos cuando la subsección es de tipo survey (trayectoria)
    if cfg.recompute_kind == "survey":
        rows = GridRepository(db, cfg.model).list_for_report(report_id)
        # Recalculamos la trayectoria completa, encadenando con la última estación del reporte anterior
        recompute_survey(rows, tie_in=_tie_in_station(db, cfg, report_id))
        # Enviamos los cambios calculados a la sesión sin hacer commit todavía
        db.flush()


@router.get("/reports/{report_id}/capture/{key}", response_class=HTMLResponse)
async def capture_tab(request: Request, report_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos si el usuario actual tiene permisos de edición para mostrar u ocultar los controles correspondientes
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    # Renderizamos la pestaña de la subsección solicitada
    return _response(request, db, _require_cfg(key), report_id, can_edit=can_edit)


@router.post("/reports/{report_id}/capture/{key}/rows", response_class=HTMLResponse)
async def create_row(request: Request, report_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el reporte exista
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de crear la fila
    _ensure_report_unlocked(db, report_id)
    repo = GridRepository(db, cfg.model)
    # Creamos la nueva fila al final de la grilla, con los valores parseados del formulario
    repo.create(daily_report_id=report_id, sort_order=repo.next_sort_order(report_id),
                **_parse(cfg, await request.form()), created_by=current_user.id)
    # Recalculamos columnas derivadas (si aplica) tras la creación
    _recompute(db, cfg, report_id)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _response(request, db, cfg, report_id)


@router.put("/reports/{report_id}/capture/{key}/rows/{row_id}", response_class=HTMLResponse)
async def update_row(request: Request, report_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    repo = GridRepository(db, cfg.model)
    # Buscamos la fila a actualizar
    row = repo.get(row_id)
    # Verificamos que la fila exista y pertenezca al reporte indicado
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de actualizar
    _ensure_report_unlocked(db, report_id)
    # Actualizamos la fila con los valores parseados del formulario
    repo.update(row, **_parse(cfg, await request.form()), updated_by=current_user.id)
    # Recalculamos columnas derivadas (si aplica) tras la actualización
    _recompute(db, cfg, report_id)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _response(request, db, cfg, report_id)


@router.delete("/reports/{report_id}/capture/{key}/rows/{row_id}", response_class=HTMLResponse)
async def delete_row(request: Request, report_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    repo = GridRepository(db, cfg.model)
    # Buscamos la fila a eliminar
    row = repo.get(row_id)
    # Verificamos que la fila exista y pertenezca al reporte indicado
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de eliminar
    _ensure_report_unlocked(db, report_id)
    # Eliminamos la fila
    repo.delete(row)
    # Recalculamos columnas derivadas (si aplica) tras la eliminación
    _recompute(db, cfg, report_id)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _response(request, db, cfg, report_id)


@router.post("/reports/{report_id}/capture/{key}/rows/{row_id}/move", response_class=HTMLResponse)
async def move_row(request: Request, report_id: str, key: str, row_id: str, direction: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    repo = GridRepository(db, cfg.model)
    # Buscamos la fila a mover
    row = repo.get(row_id)
    # Verificamos que la fila exista y pertenezca al reporte indicado
    if row is None or str(row.daily_report_id) != report_id:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de mover la fila
    _ensure_report_unlocked(db, report_id)
    # Movemos la fila un puesto arriba o abajo según la dirección indicada
    repo.move(row, direction)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _response(request, db, cfg, report_id)


# Exposed so the Daily Report shell can render one tab button per subsection.
# Exponemos las configuraciones para que el layout del reporte diario pueda renderizar un botón por subsección
CAPTURE_CONFIGS = CONFIGS


# ---------------------------------------------------------------------------
# Bulk import — paste tab/comma/whitespace-separated rows (Excel/clipboard).
# Columns are positional, in the order of the subsection's form fields.
# ---------------------------------------------------------------------------

def _split_line(line: str) -> list[str]:
    # Priorizamos tabulaciones (pegado directo desde Excel)
    if "\t" in line:
        return line.split("\t")
    # Si no hay tabulaciones, probamos con comas (CSV)
    if "," in line:
        return line.split(",")
    # Como último recurso, separamos por espacios en blanco
    return line.split()


@router.post("/reports/{report_id}/capture/{key}/import", response_class=HTMLResponse)
async def import_rows(request: Request, report_id: str, key: str, pasted: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el reporte exista
    if DailyReportRepository(db).get(report_id) is None:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de importar
    _ensure_report_unlocked(db, report_id)
    # Tomamos solo los campos que se muestran en el formulario, en su orden, para mapear columnas posicionalmente
    form_fields = [f for f in cfg.fields if f.form]
    repo = GridRepository(db, cfg.model)
    order = repo.next_sort_order(report_id)
    added = 0
    # Recorremos cada línea pegada por el usuario
    for line in pasted.splitlines():
        # Saltamos líneas en blanco
        if not line.strip():
            continue
        cells = _split_line(line)
        values = {}
        # Asociamos cada celda con su campo correspondiente según el orden posicional
        for f, raw in zip(form_fields, cells):
            values[f.name] = _coerce(f.kind, raw.strip())
        # Si todos los valores quedaron vacíos, asumimos que es una fila en blanco o de encabezado y la saltamos
        if all(v is None for v in values.values()):
            continue  # blank / header row
        # Aplicamos los cálculos derivados de la grilla antes de guardar
        values = compute_values(cfg, values)
        # Creamos la fila con los valores importados
        repo.create(daily_report_id=report_id, sort_order=order, **values, created_by=current_user.id)
        order += 1
        added += 1
    # Recalculamos columnas derivadas (si aplica) tras importar todas las filas
    _recompute(db, cfg, report_id)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _response(request, db, cfg, report_id)
