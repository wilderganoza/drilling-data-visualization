"""Rig catalog — the physical drilling rigs that carry a WITS0-capable
instrumentation system (e.g. SZJ-II). Created once per rig and rarely
edited; each Event picks which rig is feeding it live data from here
(see app/web/realtime.py)."""
# Importamos Optional para tipar los campos de formulario opcionales
from typing import Optional

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias, leer formularios y lanzar errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos HTMLResponse, ya que cada ruta devuelve el fragmento (o la página) renderizado
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos la dependencia que nos entrega una sesión de base de datos por request
from app.db.session import get_db
# Importamos los helpers de permisos: require_ops_role bloquea la ruta, has_ops_role solo consulta si el usuario puede editar
from app.core.permissions import require_ops_role, has_ops_role
# Importamos el enum de roles operativos usados en los chequeos de permisos
from app.core.ops_roles import OpsRole
# Importamos los modos WITS válidos, para validar el formulario
from app.models.realtime import WITS_MODES
# Importamos el repositorio del catálogo de taladros
from app.repositories.realtime_repository import RigRepository
# Importamos el motor de templates compartido por toda la app
from app.web.templating import templates

# Creamos el router de taladros bajo /master-data (vive junto al resto de Master Data)
router = APIRouter(prefix="/master-data/rigs")

# Definimos la dependencia que exige rol de Admin u Office Engineer para poder editar el catálogo
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)


# Normalizamos un campo de texto de formulario: recortamos espacios y devolvemos None si queda vacío
def _opt(value: Optional[str]) -> Optional[str]:
    return value.strip() if value and value.strip() else None


# Armamos el contexto que consume el partial de la tabla de taladros
def _table_context(db: Session, current_user: User) -> dict:
    rigs = RigRepository(db).list(order_by=RigRepository.model.name, limit=200)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return {"rigs": rigs, "wits_modes": WITS_MODES, "can_edit": can_edit}


# Mostramos la página completa del catálogo de taladros
@router.get("", response_class=HTMLResponse)
async def rigs_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Renderizamos la página, que a su vez incluye el partial de la tabla
    return templates.TemplateResponse(
        request, "ops/pages/rigs.html",
        {"request": request, "current_user": current_user, **_table_context(db, current_user)},
    )


# Creamos un taladro nuevo en el catálogo
@router.post("/table", response_class=HTMLResponse)
async def create_rig(
    request: Request,
    name: str = Form(...),
    wits_mode: str = Form("client"),
    wits_host: str = Form(""),
    wits_port: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(CAN_EDIT),
):
    # Validamos que el modo de conexión sea uno de los soportados
    if wits_mode not in WITS_MODES:
        raise HTTPException(400, f"wits_mode debe ser uno de: {', '.join(WITS_MODES)}")
    # Convertimos el puerto a entero si vino, o lo dejamos vacío
    port = int(wits_port) if wits_port.strip() else None
    # Creamos el taladro con los datos del formulario
    RigRepository(db).create(
        name=name.strip(), wits_mode=wits_mode, wits_host=_opt(wits_host), wits_port=port,
        notes=_opt(notes), created_by=current_user.id,
    )
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la tabla actualizada
    return templates.TemplateResponse(request, "ops/partials/rigs_table.html", {"request": request, **_table_context(db, current_user)})


# Actualizamos los datos de conexión de un taladro existente
@router.put("/table/{rig_id}", response_class=HTMLResponse)
async def update_rig(
    request: Request,
    rig_id: str,
    name: str = Form(...),
    wits_mode: str = Form("client"),
    wits_host: str = Form(""),
    wits_port: str = Form(""),
    is_active: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(CAN_EDIT),
):
    # Buscamos el taladro a editar
    repo = RigRepository(db)
    rig = repo.get(rig_id)
    # Si no existe, respondemos 404
    if rig is None:
        raise HTTPException(404)
    # Validamos que el modo de conexión sea uno de los soportados
    if wits_mode not in WITS_MODES:
        raise HTTPException(400, f"wits_mode debe ser uno de: {', '.join(WITS_MODES)}")
    # Convertimos el puerto a entero si vino, o lo dejamos vacío
    port = int(wits_port) if wits_port.strip() else None
    # Aplicamos los cambios del formulario (is_active viaja como "1"/"" desde un <select>, igual que is_active en las reglas de validación)
    repo.update(
        rig, name=name.strip(), wits_mode=wits_mode, wits_host=_opt(wits_host), wits_port=port,
        is_active=bool(is_active), notes=_opt(notes), updated_by=current_user.id,
    )
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la tabla actualizada
    return templates.TemplateResponse(request, "ops/partials/rigs_table.html", {"request": request, **_table_context(db, current_user)})
