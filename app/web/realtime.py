"""Real-time connection control for a single Event: pick which rig is
drilling it, activate the WITS0 channel, watch its status, deactivate it
when the rig moves to a different well. The actual socket/parsing work
lives in app.services.realtime.ingest_manager — this module only flips the
RealtimeSource row and tells the manager to start/stop the matching task."""
# Importamos la clase Request de FastAPI para pasarla al motor de templates
from fastapi import APIRouter, Depends, HTTPException, Request
# Importamos HTMLResponse, ya que cada ruta devuelve el fragmento de estado renderizado
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado, y utcnow para sellar la desactivación
from app.models.legacy import User, utcnow
# Importamos la dependencia que nos entrega una sesión de base de datos por request
from app.db.session import get_db
# Importamos los helpers de permisos: require_ops_role bloquea la ruta, has_ops_role solo consulta si el usuario puede editar
from app.core.permissions import require_ops_role, has_ops_role
# Importamos el enum de roles operativos usados en los chequeos de permisos
from app.core.ops_roles import OpsRole
# Importamos el repositorio de eventos, para validar que el evento exista
from app.repositories.hierarchy_repository import EventRepository
# Importamos los repositorios de taladros y fuentes en tiempo real
from app.repositories.realtime_repository import RigRepository, RealtimeSourceRepository
# Importamos el manager que mantiene las conexiones WITS0 vivas — le avisamos cuándo arrancar/parar una
from app.services.realtime.ingest_manager import realtime_manager
# Importamos el motor de templates compartido por toda la app
from app.web.templating import templates

# Creamos el router de tiempo real bajo /ops (vive junto al resto de Daily Operations/Dashboard)
router = APIRouter(prefix="/ops")

# Definimos la dependencia de permisos: quién puede activar/desactivar un canal en el wellsite
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER, OpsRole.RIG_SUPERVISOR)


# Armamos el contexto compartido por la sección de tiempo real de un evento (activo o no)
def _realtime_context(db: Session, event_id: str, current_user: User) -> dict:
    # Buscamos si el evento ya tiene un canal activo ahora mismo
    source = RealtimeSourceRepository(db).get_enabled_for_event(event_id)
    # Listamos los taladros activos para el selector, junto con cuál de ellos (si alguno) está
    # ocupado ahora mismo con OTRO evento, para no ofrecerlo como si estuviera libre
    rigs = RigRepository(db).list_active()
    busy_rig_ids = set()
    for rig in rigs:
        busy = RealtimeSourceRepository(db).get_enabled_for_rig(rig.id)
        if busy is not None and str(busy.event_id) != str(event_id):
            busy_rig_ids.add(str(rig.id))
    # Verificamos si el usuario actual puede activar/desactivar el canal
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER, OpsRole.RIG_SUPERVISOR)
    # Devolvemos el contexto que consume el partial realtime_section.html
    return {
        "event_id": event_id, "source": source, "rigs": rigs, "busy_rig_ids": busy_rig_ids,
        "manager_running": realtime_manager.is_running(str(source.id)) if source else False,
        "can_edit": can_edit,
    }


# Mostramos la sección de tiempo real de un evento (estado actual, o el selector para activarla)
@router.get("/events/{event_id}/realtime", response_class=HTMLResponse)
async def realtime_section(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos que el evento exista
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Armamos el contexto y renderizamos el partial — este mismo endpoint también lo usa el
    # polling periódico (hx-trigger="every 5s") para refrescar el estado sin recargar la página
    ctx = _realtime_context(db, event_id, current_user)
    return templates.TemplateResponse(request, "ops/partials/realtime_section.html", {"request": request, **ctx})


# Activamos el canal en tiempo real de un evento, conectándolo a un taladro elegido
@router.post("/events/{event_id}/realtime/enable", response_class=HTMLResponse)
async def realtime_enable(request: Request, event_id: str, rig_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Verificamos que el evento exista
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Verificamos que el taladro elegido exista
    rig = RigRepository(db).get(rig_id)
    if rig is None:
        raise HTTPException(404, "Taladro no encontrado.")

    source_repo = RealtimeSourceRepository(db)
    # Rechazamos activar si este evento ya tiene un canal activo (hay que desactivarlo primero)
    if source_repo.get_enabled_for_event(event_id) is not None:
        raise HTTPException(400, "Este evento ya tiene un canal en tiempo real activo. Desactívalo antes de cambiar de taladro.")
    # Rechazamos activar si el taladro elegido ya está transmitiendo a OTRO evento — nunca
    # desconectamos silenciosamente un pozo distinto solo porque alguien activó el mismo taladro acá
    busy = source_repo.get_enabled_for_rig(rig_id)
    if busy is not None:
        raise HTTPException(400, f"El taladro «{rig.name}» ya está transmitiendo a otro evento. Desactívalo ahí primero.")

    # Creamos la fuente habilitada
    source = source_repo.create(event_id=event_id, rig_id=rig_id, enabled=True, status="connecting", created_by=current_user.id)
    # Confirmamos la transacción antes de que el manager la lea desde su propia sesión
    db.commit()
    # Le avisamos al manager que arranque la conexión de esta fuente recién creada
    realtime_manager.spawn(str(source.id))
    # Devolvemos la sección actualizada
    ctx = _realtime_context(db, event_id, current_user)
    return templates.TemplateResponse(request, "ops/partials/realtime_section.html", {"request": request, **ctx})


# Desactivamos el canal en tiempo real activo de un evento
@router.post("/events/{event_id}/realtime/disable", response_class=HTMLResponse)
async def realtime_disable(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Verificamos que el evento exista
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    source_repo = RealtimeSourceRepository(db)
    # Buscamos el canal activo de este evento
    source = source_repo.get_enabled_for_event(event_id)
    if source is not None:
        # Le avisamos al manager que corte la conexión de red antes de tocar la fila en la base
        realtime_manager.cancel(str(source.id))
        # Marcamos la fuente como deshabilitada, conservando su historial (no la borramos)
        source_repo.update(source, enabled=False, status="disconnected", stopped_at=utcnow(), updated_by=current_user.id)
        db.commit()
    # Devolvemos la sección actualizada (ahora mostrará el selector para activar de nuevo)
    ctx = _realtime_context(db, event_id, current_user)
    return templates.TemplateResponse(request, "ops/partials/realtime_section.html", {"request": request, **ctx})
