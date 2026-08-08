"""Lazy-loaded sidebar tree for Company -> ... -> Event navigation.

The same tree shape is reused across three workspaces — Master Data,
Planning, and Daily Operations — which differ in two ways:

- Where the Wellbore node itself links (Master Data owns the CRUD page for
  it; Planning/Daily Operations each have their own Wellbore page scoped to
  what that workspace does — list Events with a "+ New Event" in Planning,
  read-only in Daily Operations).
- Whether Wellbore expands further to show Events at all: Events are
  operational campaigns, not master data, so Master Data's tree stops at
  Wellbore (a leaf, no CRUD-in-the-tree for something it doesn't own).

`build_tree_router` takes these as parameters instead of tripling this file.
Company/Project/Site/Well link into whichever workspace's own tree is being
rendered (`entity_link_prefix`) — Master Data gets CRUD pages there, Planning
and Daily Operations get read-only viewer pages (see hierarchy_readonly.py).
No workspace's tree may link a click into a different workspace.
"""
# Importamos las clases de FastAPI para el router, dependencias y requests
from fastapi import APIRouter, Depends, Request
# Importamos la respuesta HTML para los fragmentos renderizados
from fastapi.responses import HTMLResponse
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos los repositorios de cada nivel de la jerarquía (empresa, evento, proyecto, sitio, pozo, wellbore)
from app.repositories.hierarchy_repository import (
    CompanyRepository,
    EventRepository,
    ProjectRepository,
    SiteRepository,
    WellRepository,
    WellboreRepository,
)
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates


def _fragment(request: Request, items, link_prefix: str, label_key: str, children_url_prefix: str | None = None) -> HTMLResponse:
    # Renderizamos el fragmento genérico de nodos hijos del árbol
    return templates.TemplateResponse(
        request, "ops/partials/tree_fragment.html",
        {"request": request, "items": items, "link_prefix": link_prefix, "label_key": label_key, "children_url_prefix": children_url_prefix},
    )


def build_tree_router(*, url_prefix: str, entity_link_prefix: str, wellbore_link_prefix: str, event_link_prefix: str, expand_events: bool) -> APIRouter:
    # Creamos el router propio de este workspace, montado bajo su prefijo
    router = APIRouter(prefix=url_prefix)

    # (repo, parent-filter key, label attr, href prefix, order-by, child url segment)
    # Definimos las especificaciones de cada nivel de la jerarquía: repositorio, clave de filtro por padre,
    # atributo usado como etiqueta, prefijo del enlace, columna de orden y segmento de URL para hijos
    level_specs = [
        (CompanyRepository, None, "name", f"{entity_link_prefix}/companies", CompanyRepository.model.name, "companies"),
        (ProjectRepository, "company_id", "name", f"{entity_link_prefix}/projects", ProjectRepository.model.name, "projects"),
        (SiteRepository, "project_id", "name", f"{entity_link_prefix}/sites", SiteRepository.model.name, "sites"),
        (WellRepository, "site_id", "legal_well_name", f"{entity_link_prefix}/wells", WellRepository.model.legal_well_name, "wells"),
        (WellboreRepository, "well_id", "name", wellbore_link_prefix, WellboreRepository.model.name, "wellbores"),
    ]
    # Si este workspace expande eventos, agregamos el nivel de Evento al final de la jerarquía
    if expand_events:
        level_specs.append((EventRepository, "wellbore_id", "event_code", event_link_prefix, EventRepository.model.start_date, None))

    def _build_nodes(db: Session, level_idx: int, parent_id, open_set: set[str], active_id: str) -> list[dict]:
        # Obtenemos la especificación del nivel actual
        repo_cls, filt_key, label_attr, href_prefix, order, child_seg = level_specs[level_idx]
        # Armamos el filtro por el id del padre, si este nivel tiene padre
        filters = {filt_key: parent_id} if filt_key else None
        # Listamos los ítems de este nivel (hasta 500), ordenados
        items = repo_cls(db).list(filters=filters, order_by=order, limit=500)
        # Determinamos si este nivel puede expandirse (no es el último nivel de la jerarquía)
        expandable = level_idx < len(level_specs) - 1
        nodes = []
        # Recorremos cada ítem para armar su nodo del árbol
        for item in items:
            iid = str(item.id)
            node = {
                "id": iid, "label": getattr(item, label_attr) or "—", "href": f"{href_prefix}/{iid}",
                "active": iid == active_id, "is_leaf": not expandable, "open": False, "children": None,
                "children_url": (f"{url_prefix}/{child_seg}/{iid}/children" if expandable else None),
            }
            # Si el nodo es expandible y está en el conjunto de nodos abiertos, lo pre-expandimos recursivamente
            if expandable and iid in open_set:
                node["open"] = True
                node["children"] = _build_nodes(db, level_idx + 1, item.id, open_set, active_id)
            nodes.append(node)
        return nodes

    @router.get("", response_class=HTMLResponse)
    async def tree_root(request: Request, chain: str = "", active: str = "", db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # `chain` is the ancestor id list of the active entity (from base.html):
        # pre-expand those nodes server-side so a deep page loads the tree in one
        # request instead of one lazy round-trip per level.
        # Convertimos la cadena de ids de ancestros en un conjunto para búsqueda rápida
        open_set = {x for x in chain.split(",") if x}
        # Construimos el árbol completo desde la raíz, pre-expandiendo según open_set
        nodes = _build_nodes(db, 0, None, open_set, active)
        return templates.TemplateResponse(request, "ops/partials/tree_root.html", {"request": request, "nodes": nodes})

    @router.get("/companies/{company_id}/children", response_class=HTMLResponse)
    async def tree_company_children(request: Request, company_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Listamos los proyectos hijos de esta empresa
        projects = ProjectRepository(db).list(filters={"company_id": company_id}, order_by=ProjectRepository.model.name)
        return _fragment(request, projects, f"{entity_link_prefix}/projects", "name", f"{url_prefix}/projects")

    @router.get("/projects/{project_id}/children", response_class=HTMLResponse)
    async def tree_project_children(request: Request, project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Listamos los sitios hijos de este proyecto
        sites = SiteRepository(db).list(filters={"project_id": project_id}, order_by=SiteRepository.model.name)
        return _fragment(request, sites, f"{entity_link_prefix}/sites", "name", f"{url_prefix}/sites")

    @router.get("/sites/{site_id}/children", response_class=HTMLResponse)
    async def tree_site_children(request: Request, site_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Listamos los pozos hijos de este sitio
        wells = WellRepository(db).list(filters={"site_id": site_id}, order_by=WellRepository.model.legal_well_name)
        return _fragment(request, wells, f"{entity_link_prefix}/wells", "legal_well_name", f"{url_prefix}/wells")

    @router.get("/wells/{well_id}/children", response_class=HTMLResponse)
    async def tree_well_children(request: Request, well_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Listamos los wellbores hijos de este pozo
        wellbores = WellboreRepository(db).list(filters={"well_id": well_id}, order_by=WellboreRepository.model.name)
        # Solo exponemos la URL de hijos del wellbore si este workspace expande eventos
        children_prefix = f"{url_prefix}/wellbores" if expand_events else None
        return _fragment(request, wellbores, wellbore_link_prefix, "name", children_prefix)

    # Solo registramos la ruta de hijos de wellbore (eventos) si este workspace expande eventos
    if expand_events:
        @router.get("/wellbores/{wellbore_id}/children", response_class=HTMLResponse)
        async def tree_wellbore_children(request: Request, wellbore_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
            # Listamos los eventos hijos de este wellbore
            events = EventRepository(db).list(filters={"wellbore_id": wellbore_id}, order_by=EventRepository.model.start_date)
            return _fragment(request, events, event_link_prefix, "event_code")

    return router


# Construimos el router del árbol para Master Data (sin expandir eventos; el wellbore es hoja)
master_data_tree_router = build_tree_router(
    url_prefix="/master-data/tree", entity_link_prefix="/master-data", wellbore_link_prefix="/master-data/wellbores",
    event_link_prefix="/master-data/events", expand_events=False,
)
# Construimos el router del árbol para Planning (expandiendo hasta eventos)
planning_tree_router = build_tree_router(
    url_prefix="/planning/tree", entity_link_prefix="/planning", wellbore_link_prefix="/planning/wellbores",
    event_link_prefix="/planning/events", expand_events=True,
)
# Construimos el router del árbol para Daily Operations (expandiendo hasta eventos)
daily_ops_tree_router = build_tree_router(
    url_prefix="/ops/tree", entity_link_prefix="/ops", wellbore_link_prefix="/ops/wellbores",
    event_link_prefix="/ops/events", expand_events=True,
)


# ---------------------------------------------------------------------------
# Ancestor chains, for auto-expanding the sidebar tree down to whatever
# entity a detail page is showing. Every full page load re-fetches the tree
# from scratch (there's no SPA state to carry it across navigations), so
# without this the tree resets to fully-collapsed on every click — these
# chains are handed to the client as `data-open-ids`/`data-active-id` and
# walked by a small cascade in app.js that opens each <details> in turn via
# its native `toggle` event, reusing the existing lazy hx-get wiring instead
# of a second, parallel "pre-expanded" server-rendering path.
# ---------------------------------------------------------------------------

def chain_for_company(company) -> list[str]:
    # La cadena de una empresa es solo su propio id (nivel raíz)
    return [str(company.id)]


def chain_for_project(project) -> list[str]:
    # La cadena de un proyecto es la empresa seguida de su propio id
    return [str(project.company_id), str(project.id)]


def chain_for_site(site) -> list[str]:
    # La cadena de un sitio extiende la de su proyecto con su propio id
    return chain_for_project(site.project) + [str(site.id)]


def chain_for_well(well) -> list[str]:
    # La cadena de un pozo extiende la de su sitio con su propio id
    return chain_for_site(well.site) + [str(well.id)]


def chain_for_wellbore(wellbore) -> list[str]:
    # La cadena de un wellbore extiende la de su pozo con su propio id
    return chain_for_well(wellbore.well) + [str(wellbore.id)]


def chain_for_event(event) -> list[str]:
    # La cadena de un evento extiende la de su wellbore con su propio id
    return chain_for_wellbore(event.wellbore) + [str(event.id)]
