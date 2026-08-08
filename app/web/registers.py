"""Generic CRUD for the event-level operations registers (HSE incidents, BOP
tests, certifications, lessons learned, materials/inventory). Same grid engine
as the daily-capture and well-plan program routes, but rows hang off the Event.
Mounted under /ops so it lives with Daily Operations."""
# Importamos las clases de FastAPI para definir el router, inyectar dependencias, leer forms y lanzar errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos la respuesta HTML para devolver fragmentos renderizados
from fastapi.responses import HTMLResponse
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session
# Importamos FormData para tipar los datos del formulario que recibimos
from starlette.datastructures import FormData

# Importamos la dependencia que nos entrega el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos los helpers de permisos: exigir un rol o solo verificarlo
from app.core.permissions import require_ops_role, has_ops_role
# Importamos el enum de roles operacionales
from app.core.ops_roles import OpsRole
# Importamos la configuración de grillas y la función que calcula valores derivados
from app.models.capture import GridConfig, compute_values
# Importamos las configuraciones de los registros y el getter por clave
from app.models.registers import REGISTER_CONFIGS, get_register_config
# Importamos el repositorio genérico de grillas
from app.repositories.capture_repository import GridRepository
# Importamos el repositorio de eventos, para validar que el evento padre existe
from app.repositories.hierarchy_repository import EventRepository
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates

# Creamos el router y lo montamos bajo el prefijo /ops
router = APIRouter(prefix="/ops")

# Definimos la dependencia que exige alguno de estos roles para poder editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER, OpsRole.RIG_SUPERVISOR)


def _coerce(kind: str, raw):
    """Raises ValueError (caller turns it into a 400 naming the field) on a
    non-empty value that doesn't parse — a bad paste/import value used to
    disappear silently into a blank cell instead of being rejected."""
    # Recortamos espacios si el valor es un string
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    # Si queda vacío, lo tratamos como ausente
    if raw in (None, ""):
        return None
    # Si el campo es numérico decimal, convertimos a float
    if kind == "number":
        return float(raw)
    # Si el campo es entero, convertimos pasando primero por float (soporta "3.0")
    if kind == "int":
        return int(float(raw))
    # Para el resto de tipos devolvemos el valor tal cual
    return raw


def _parse(cfg: GridConfig, form: FormData) -> dict:
    # Preparamos el diccionario de valores parseados
    values = {}
    # Recorremos los campos de la configuración de la grilla
    for f in cfg.fields:
        # Omitimos los campos que no vienen del formulario
        if not f.form:
            continue
        try:
            # Coercionamos cada valor según su tipo declarado
            values[f.name] = _coerce(f.kind, form.get(f.name))
        except ValueError:
            # Si no parsea, devolvemos un 400 indicando qué campo falló
            raise HTTPException(status_code=400, detail=f'"{form.get(f.name)}" is not a valid number for {f.label}.')
    # Calculamos los valores derivados (fórmulas de la grilla) antes de devolver
    return compute_values(cfg, values)


def _repo(db: Session, cfg: GridConfig) -> GridRepository:
    # Construimos el repositorio genérico para el modelo de esta grilla, filtrando por evento padre
    return GridRepository(db, cfg.model, parent_field="event_id")


def _require_cfg(key: str) -> GridConfig:
    # Buscamos la configuración del registro por su clave
    cfg = get_register_config(key)
    # Si no existe, respondemos 404
    if cfg is None:
        raise HTTPException(404)
    return cfg


def _grid_response(request: Request, db: Session, cfg: GridConfig, event_id: str, can_edit: bool = True) -> HTMLResponse:
    # Verificamos que el evento padre exista antes de listar filas
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Obtenemos todas las filas de esta grilla para el evento
    rows = _repo(db, cfg).list_for_parent(event_id)
    # Renderizamos el fragmento de grilla reutilizable
    return templates.TemplateResponse(
        request, "ops/partials/grid.html",
        {"request": request, "cfg": cfg, "rows": rows, "can_edit": can_edit,
         "base_url": f"/ops/events/{event_id}/registers/{cfg.key}", "content_id": "reg-tab-content"},
    )


@router.get("/events/{event_id}/registers", response_class=HTMLResponse)
async def registers_page(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento; si no existe, respondemos 404
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Importamos aquí para evitar import circular con tree.py y el repositorio de wellbores
    from app.repositories.hierarchy_repository import WellboreRepository
    from app.web.tree import chain_for_event
    # Obtenemos el wellbore del evento, para mostrar contexto en la página
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Calculamos la cadena de ancestros para pre-expandir el árbol lateral
    chain = chain_for_event(event)
    # Renderizamos la página completa de registros con las pestañas disponibles
    return templates.TemplateResponse(
        request, "ops/pages/registers.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore,
         "configs": REGISTER_CONFIGS, "first_key": REGISTER_CONFIGS[0].key,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


@router.get("/events/{event_id}/registers/{key}", response_class=HTMLResponse)
async def register_tab(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos si el usuario actual tiene alguno de los roles habilitados para editar
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER, OpsRole.RIG_SUPERVISOR)
    # Devolvemos el fragmento de grilla para esta pestaña/registro
    return _grid_response(request, db, _require_cfg(key), event_id, can_edit=can_edit)


@router.post("/events/{event_id}/registers/{key}/rows", response_class=HTMLResponse)
async def create_row(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración del registro
    cfg = _require_cfg(key)
    # Verificamos que el evento padre exista
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Obtenemos el repositorio de esta grilla
    repo = _repo(db, cfg)
    # Creamos la fila nueva al final del orden actual, con los valores parseados del formulario
    repo.create(event_id=event_id, sort_order=repo.next_sort_order(event_id),
                **_parse(cfg, await request.form()), created_by=current_user.id)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la grilla actualizada
    return _grid_response(request, db, cfg, event_id)


@router.put("/events/{event_id}/registers/{key}/rows/{row_id}", response_class=HTMLResponse)
async def update_row(request: Request, event_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración del registro
    cfg = _require_cfg(key)
    repo = _repo(db, cfg)
    # Buscamos la fila a actualizar
    row = repo.get(row_id)
    # Verificamos que exista y que pertenezca al evento indicado en la URL
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Actualizamos la fila con los valores parseados del formulario
    repo.update(row, **_parse(cfg, await request.form()), updated_by=current_user.id)
    db.commit()
    return _grid_response(request, db, cfg, event_id)


@router.delete("/events/{event_id}/registers/{key}/rows/{row_id}", response_class=HTMLResponse)
async def delete_row(request: Request, event_id: str, key: str, row_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración del registro
    cfg = _require_cfg(key)
    repo = _repo(db, cfg)
    # Buscamos la fila a eliminar
    row = repo.get(row_id)
    # Verificamos que exista y pertenezca al evento
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Eliminamos la fila
    repo.delete(row)
    db.commit()
    return _grid_response(request, db, cfg, event_id)


@router.post("/events/{event_id}/registers/{key}/rows/{row_id}/move", response_class=HTMLResponse)
async def move_row(request: Request, event_id: str, key: str, row_id: str, direction: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Resolvemos la configuración del registro
    cfg = _require_cfg(key)
    repo = _repo(db, cfg)
    # Buscamos la fila a mover
    row = repo.get(row_id)
    # Verificamos que exista y pertenezca al evento
    if row is None or str(row.event_id) != event_id:
        raise HTTPException(404)
    # Movemos la fila en la dirección indicada (reordenamiento)
    repo.move(row, direction)
    db.commit()
    return _grid_response(request, db, cfg, event_id)
