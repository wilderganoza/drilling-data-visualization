"""Daily Operations workspace: day-to-day report capture for an Event
(Daily Report and its subsections, Casing, Cementing, Surveys, NPT, etc.).
Hierarchy CRUD lives in Master Data; this workspace only navigates down to
an Event via its own sidebar tree and works within it."""
# Importamos las clases de FastAPI para el router, inyección de dependencias, errores HTTP y la request
from fastapi import APIRouter, Depends, HTTPException, Request
# Importamos la respuesta HTML para las páginas renderizadas
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos la dependencia que resuelve el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos la dependencia que nos entrega una sesión de base de datos
from app.db.session import get_db
# Importamos los repositorios de Event, Well y Wellbore para consultar la jerarquía
from app.repositories.hierarchy_repository import EventRepository, WellRepository, WellboreRepository
# Importamos los helpers que arman la cadena de nodos abiertos del árbol lateral
from app.web.tree import chain_for_event, chain_for_wellbore
# Importamos las plantillas Jinja2 para renderizar las páginas
from app.web.templating import templates

# Creamos el router de Daily Operations bajo el prefijo /ops
router = APIRouter(prefix="/ops")


# Definimos la ruta de entrada del workspace de Daily Operations
@router.get("", response_class=HTMLResponse)
async def daily_ops_index(request: Request, current_user: User = Depends(get_current_user_web)):
    # Renderizamos la página de aterrizaje (landing) de Daily Ops
    return templates.TemplateResponse(request, "ops/pages/daily_ops_landing.html", {"request": request, "current_user": current_user})


# Definimos la ruta de detalle de un wellbore dentro de Daily Operations
@router.get("/wellbores/{wellbore_id}", response_class=HTMLResponse)
async def daily_ops_wellbore_detail(request: Request, wellbore_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el wellbore solicitado
    wellbore = WellboreRepository(db).get(wellbore_id)
    # Si no existe, devolvemos 404
    if wellbore is None:
        raise HTTPException(404)
    # Buscamos el pozo (well) al que pertenece el wellbore
    well = WellRepository(db).get(wellbore.well_id)
    # Listamos los eventos del wellbore, ordenados por fecha de inicio
    events = EventRepository(db).list(filters={"wellbore_id": wellbore_id}, order_by=EventRepository.model.start_date)
    # Calculamos la cadena de nodos del árbol lateral hasta este wellbore
    chain = chain_for_wellbore(wellbore)
    # Renderizamos la página de detalle del wellbore, marcando el árbol abierto hasta el nodo activo
    return templates.TemplateResponse(
        request, "ops/pages/daily_ops_wellbore_detail.html",
        {"request": request, "current_user": current_user, "wellbore": wellbore, "well": well, "events": events,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


# Definimos la ruta de detalle de un evento dentro de Daily Operations
@router.get("/events/{event_id}", response_class=HTMLResponse)
async def daily_ops_event_detail(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Si no existe, devolvemos 404
    if event is None:
        raise HTTPException(404)
    # Buscamos el wellbore al que pertenece el evento
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Calculamos la cadena de nodos del árbol lateral hasta este evento
    chain = chain_for_event(event)
    # Renderizamos la página de detalle del evento, marcando el árbol abierto hasta el nodo activo
    return templates.TemplateResponse(
        request, "ops/pages/daily_ops_event_detail.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )
