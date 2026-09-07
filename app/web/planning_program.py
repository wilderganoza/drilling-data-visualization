"""Generic CRUD routes for the Well-Plan program subsections (formation tops,
casing/hole/mud/cement programs, directional plan, time-depth, cost estimate,
risks). Same engine as the daily-report capture routes, but rows hang off the
Event (`event_id`) instead of a daily report, and the directional plan is
self-contained (no cross-report tie-in). Mounted under /planning."""
# Importamos las clases de FastAPI para el router, dependencias, forms y errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos la respuesta HTML para los fragmentos renderizados
from fastapi.responses import HTMLResponse
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session
# Importamos FormData para tipar los datos de formulario
from starlette.datastructures import FormData

# Importamos la dependencia que nos entrega el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos los helpers de permisos: exigir un rol o solo verificarlo
from app.core.permissions import require_ops_role, has_ops_role
# Importamos el enum de roles operacionales
from app.core.ops_roles import OpsRole
# Importamos la configuración de grillas y la función que calcula valores derivados
from app.models.capture import GridConfig, compute_values
# Importamos las configuraciones del programa de planeación y su getter por clave
from app.models.planning_capture import PLAN_CONFIGS, get_plan_config
# Importamos el repositorio genérico de grillas
from app.repositories.capture_repository import GridRepository
# Importamos el repositorio de eventos, para validar que el evento padre existe
from app.repositories.hierarchy_repository import EventRepository
# Importamos el repositorio del plan de pozo, para saber si está bloqueado (aprobado)
from app.repositories.planning_repository import WellPlanRepository
# Importamos el servicio que recalcula la trayectoria direccional
from app.services.survey_calc import recompute_survey
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates

# Creamos el router y lo montamos bajo el prefijo /planning
router = APIRouter(prefix="/planning")

# Definimos la dependencia que exige alguno de estos roles para poder editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)


def ensure_plan_unlocked(db: Session, event_id: str) -> None:
    """Approved plans are locked — reject program edits to preserve the record."""
    # Buscamos el plan de pozo asociado al evento
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Si el plan existe y está bloqueado, rechazamos la edición con un 409
    if plan is not None and plan.is_locked:
        raise HTTPException(409, "Plan is approved and locked. Reopen it to edit the program.")


def _coerce(kind: str, raw):
    # Recortamos espacios si el valor es un string
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    # Si queda vacío, lo tratamos como ausente
    if raw in (None, ""):
        return None
    if kind == "number":
        try:
            # Intentamos convertir a float
            return float(raw)
        except ValueError:
            # Si no parsea, devolvemos None en vez de lanzar error (aquí es tolerante)
            return None
    if kind == "int":
        try:
            # Intentamos convertir a entero pasando primero por float
            return int(float(raw))
        except ValueError:
            return None
    # Para el resto de tipos devolvemos el valor tal cual
    return raw


def _parse(cfg: GridConfig, form: FormData) -> dict:
    # Coercionamos cada campo del formulario que pertenezca a esta grilla
    values = {f.name: _coerce(f.kind, form.get(f.name)) for f in cfg.fields if f.form}
    # Calculamos los valores derivados (fórmulas de la grilla) antes de devolver
    return compute_values(cfg, values)


def _repo(db: Session, cfg: GridConfig) -> GridRepository:
    # Construimos el repositorio genérico para el modelo de esta grilla, filtrando por evento padre
    return GridRepository(db, cfg.model, parent_field="event_id")


def _recompute(db: Session, cfg: GridConfig, event_id: str) -> None:
    # Solo recalculamos cuando la grilla es la de trayectoria direccional
    if cfg.recompute_kind == "survey":
        # Obtenemos todas las filas actuales de la grilla
        rows = _repo(db, cfg).list_for_parent(event_id)
        # Recalculamos la trayectoria planificada, que arranca en superficie (sin tie-in)
        recompute_survey(rows)  # planned trajectory starts at surface — no tie-in
        # Sincronizamos los cambios con la sesión sin hacer commit todavía
        db.flush()


def _response(request: Request, db: Session, cfg: GridConfig, event_id: str, can_edit: bool = True) -> HTMLResponse:
    # Buscamos el evento padre; si no existe, respondemos 404
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Obtenemos todas las filas de esta grilla para el evento
    rows = _repo(db, cfg).list_for_parent(event_id)
    # Determinamos si el plan está bloqueado (aprobado)
    locked = bool(event.well_plan and event.well_plan.is_locked)
    # Renderizamos el fragmento de grilla, deshabilitando edición si el plan está bloqueado
    return templates.TemplateResponse(
        request, "ops/partials/grid.html",
        {"request": request, "cfg": cfg, "rows": rows, "can_edit": can_edit and not locked,
         "base_url": f"/planning/events/{event_id}/plan/{cfg.key}", "content_id": "plan-tab-content"},
    )


def _require_cfg(key: str) -> GridConfig:
    # Buscamos la configuración del subsección del plan por su clave
    cfg = get_plan_config(key)
    # Si no existe, respondemos 404
    if cfg is None:
        raise HTTPException(404)
    return cfg


@router.get("/events/{event_id}/plan/{key}", response_class=HTMLResponse)
async def plan_tab(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos si el usuario actual tiene alguno de los roles habilitados para editar
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    # Devolvemos el fragmento de grilla para esta pestaña del plan
    return _response(request, db, _require_cfg(key), event_id, can_edit=can_edit)


@router.post("/events/{event_id}/plan/{key}/rows", response_class=HTMLResponse)
async def create_row(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el evento padre exista
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Verificamos que el plan no esté bloqueado antes de editar
    ensure_plan_unlocked(db, event_id)
    repo = _repo(db, cfg)
    # Creamos la fila nueva al final del orden actual, con los valores parseados del formulario
    repo.create(event_id=event_id, sort_order=repo.next_sort_order(event_id),
                **_parse(cfg, await request.form()), created_by=current_user.id)
    # Recalculamos la trayectoria si esta grilla lo requiere
    _recompute(db, cfg, event_id)
    db.commit()
    return _response(request, db, cfg, event_id)


@router.put("/events/{event_id}/plan/{key}/rows/{row_id}", response_class=HTMLResponse)
async def update_row(request: Request, event_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el plan no esté bloqueado antes de editar
    ensure_plan_unlocked(db, event_id)
    repo = _repo(db, cfg)
    # Buscamos la fila a actualizar
    row = repo.get(row_id)
    # Verificamos que exista y pertenezca al evento indicado en la URL
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Actualizamos la fila con los valores parseados del formulario
    repo.update(row, **_parse(cfg, await request.form()), updated_by=current_user.id)
    # Recalculamos la trayectoria si esta grilla lo requiere
    _recompute(db, cfg, event_id)
    db.commit()
    return _response(request, db, cfg, event_id)


@router.delete("/events/{event_id}/plan/{key}/rows/{row_id}", response_class=HTMLResponse)
async def delete_row(request: Request, event_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el plan no esté bloqueado antes de editar
    ensure_plan_unlocked(db, event_id)
    repo = _repo(db, cfg)
    # Buscamos la fila a eliminar
    row = repo.get(row_id)
    # Verificamos que exista y pertenezca al evento
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Eliminamos la fila
    repo.delete(row)
    # Recalculamos la trayectoria si esta grilla lo requiere
    _recompute(db, cfg, event_id)
    db.commit()
    return _response(request, db, cfg, event_id)


@router.post("/events/{event_id}/plan/{key}/rows/{row_id}/move", response_class=HTMLResponse)
async def move_row(request: Request, event_id: str, key: str, row_id: str, direction: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración de la subsección
    cfg = _require_cfg(key)
    # Verificamos que el plan no esté bloqueado antes de editar
    ensure_plan_unlocked(db, event_id)
    repo = _repo(db, cfg)
    # Buscamos la fila a mover
    row = repo.get(row_id)
    # Verificamos que exista y pertenezca al evento
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Movemos la fila en la dirección indicada (reordenamiento)
    repo.move(row, direction)
    db.commit()
    return _response(request, db, cfg, event_id)


# Exportamos las configuraciones del plan con un alias, usado por otros módulos
PLAN_CONFIGS_EXPORT = PLAN_CONFIGS
