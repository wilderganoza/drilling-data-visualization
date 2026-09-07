"""Read-only Company/Project/Site/Well viewer pages for Planning and Daily
Operations. Master Data owns CRUD on this hierarchy; Planning and Daily
Operations only need to browse down to a Wellbore without ever leaving their
own workspace — before this, their sidebar tree linked these intermediate
levels straight to Master Data, which silently dropped the user into a
different module on every click. One factory generates both workspaces'
routes/pages since the shape is identical, only the prefix differs."""
from fastapi import APIRouter, Depends, HTTPException, Request  # Piezas de FastAPI para rutas, inyección y errores HTTP
from fastapi.responses import HTMLResponse  # Respuesta HTML para las páginas de la jerarquía
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.core.deps import get_current_user_web  # Dependencia que resuelve el usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario
from app.db.session import get_db  # Dependencia que entrega la sesión de base de datos
from app.repositories.hierarchy_repository import (  # Repositorios de cada nivel de la jerarquía operacional
    CompanyRepository,
    ProjectRepository,
    SiteRepository,
    WellRepository,
    WellboreRepository,
)
from app.web.tree import chain_for_company, chain_for_project, chain_for_site, chain_for_well  # Helpers que arman la cadena de nodos abiertos para el árbol lateral
from app.web.templating import templates  # Motor de templates Jinja compartido


def _render(request: Request, current_user: User, *, item_name: str, item_type: str, back_href: str | None,
            back_label: str, children, columns, child_link_prefix: str, children_label: str,
            empty_message: str, edit_href: str, workspace_label: str, tree_open_ids, tree_active_id) -> HTMLResponse:
    # Renderizamos la plantilla genérica de "nivel de jerarquía de solo lectura" con los datos del nivel actual
    return templates.TemplateResponse(
        request, "ops/pages/readonly_hierarchy_level.html",
        {
            "request": request, "current_user": current_user, "item_name": item_name, "item_type": item_type,
            "back_href": back_href, "back_label": back_label, "children": children, "columns": columns,
            "child_link_prefix": child_link_prefix, "children_label": children_label, "empty_message": empty_message,
            "edit_href": edit_href, "workspace_label": workspace_label,
            "tree_open_ids": tree_open_ids, "tree_active_id": tree_active_id,
        },
    )


def build_readonly_hierarchy_router(*, url_prefix: str, workspace_label: str) -> APIRouter:
    # Creamos un router propio para este workspace (Planning o Daily Operations)
    router = APIRouter(prefix=url_prefix)

    @router.get("/companies/{company_id}", response_class=HTMLResponse)
    async def company_view(request: Request, company_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Buscamos la empresa por id
        company = CompanyRepository(db).get(company_id)
        if company is None:
            raise HTTPException(404)
        # Listamos los proyectos hijos de esta empresa, ordenados por nombre
        projects = ProjectRepository(db).list(filters={"company_id": company_id}, order_by=ProjectRepository.model.name)
        # Calculamos la cadena de nodos que deben quedar abiertos en el árbol lateral
        chain = chain_for_company(company)
        return _render(
            request, current_user, item_name=company.name, item_type="Company", back_href=None, back_label="",
            children=projects, columns=[("name", "Name")], child_link_prefix=f"{url_prefix}/projects",
            children_label="Projects", empty_message="No projects yet.", edit_href=f"/master-data/companies/{company_id}",
            workspace_label=workspace_label, tree_open_ids=chain, tree_active_id=chain[-1],
        )

    @router.get("/projects/{project_id}", response_class=HTMLResponse)
    async def project_view(request: Request, project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Buscamos el proyecto por id
        project = ProjectRepository(db).get(project_id)
        if project is None:
            raise HTTPException(404)
        # Buscamos la empresa dueña, para el enlace "volver"
        company = CompanyRepository(db).get(project.company_id)
        # Listamos los sitios hijos de este proyecto, ordenados por nombre
        sites = SiteRepository(db).list(filters={"project_id": project_id}, order_by=SiteRepository.model.name)
        # Calculamos la cadena de nodos que deben quedar abiertos en el árbol lateral
        chain = chain_for_project(project)
        return _render(
            request, current_user, item_name=project.name, item_type="Project",
            back_href=f"{url_prefix}/companies/{company.id}", back_label=company.name,
            children=sites, columns=[("name", "Name"), ("location", "Location")], child_link_prefix=f"{url_prefix}/sites",
            children_label="Sites", empty_message="No sites yet.", edit_href=f"/master-data/projects/{project_id}",
            workspace_label=workspace_label, tree_open_ids=chain, tree_active_id=chain[-1],
        )

    @router.get("/sites/{site_id}", response_class=HTMLResponse)
    async def site_view(request: Request, site_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Buscamos el sitio por id
        site = SiteRepository(db).get(site_id)
        if site is None:
            raise HTTPException(404)
        # Buscamos el proyecto dueño, para el enlace "volver"
        project = ProjectRepository(db).get(site.project_id)
        # Listamos los pozos hijos de este sitio, ordenados por nombre legal
        wells = WellRepository(db).list(filters={"site_id": site_id}, order_by=WellRepository.model.legal_well_name)
        # Calculamos la cadena de nodos que deben quedar abiertos en el árbol lateral
        chain = chain_for_site(site)
        return _render(
            request, current_user, item_name=site.name, item_type="Site",
            back_href=f"{url_prefix}/projects/{project.id}", back_label=project.name,
            children=wells, columns=[("legal_well_name", "Legal name"), ("common_well_name", "Common name"), ("uwi", "UWI")],
            child_link_prefix=f"{url_prefix}/wells", children_label="Wells", empty_message="No wells yet.",
            edit_href=f"/master-data/sites/{site_id}", workspace_label=workspace_label,
            tree_open_ids=chain, tree_active_id=chain[-1],
        )

    @router.get("/wells/{well_id}", response_class=HTMLResponse)
    async def well_view(request: Request, well_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
        # Buscamos el pozo por id
        well = WellRepository(db).get(well_id)
        if well is None:
            raise HTTPException(404)
        # Buscamos el sitio dueño, para el enlace "volver"
        site = SiteRepository(db).get(well.site_id)
        # Listamos los wellbores hijos de este pozo, ordenados por nombre
        wellbores = WellboreRepository(db).list(filters={"well_id": well_id}, order_by=WellboreRepository.model.name)
        # Calculamos la cadena de nodos que deben quedar abiertos en el árbol lateral
        chain = chain_for_well(well)
        return _render(
            request, current_user, item_name=well.legal_well_name, item_type="Well" + (" — UWI " + well.uwi if well.uwi else ""),
            back_href=f"{url_prefix}/sites/{site.id}", back_label=site.name,
            children=wellbores, columns=[("name", "Name"), ("sidetrack_no", "Sidetrack No."), ("trajectory_type", "Trajectory")],
            child_link_prefix=f"{url_prefix}/wellbores", children_label="Wellbores", empty_message="No wellbores yet.",
            edit_href=f"/master-data/wells/{well_id}", workspace_label=workspace_label,
            tree_open_ids=chain, tree_active_id=chain[-1],
        )

    # Devolvemos el router ya con las cuatro rutas de solo lectura registradas
    return router


# Instanciamos el router de jerarquía de solo lectura para el workspace de Planning
planning_hierarchy_router = build_readonly_hierarchy_router(url_prefix="/planning", workspace_label="Planning")
# Instanciamos el router de jerarquía de solo lectura para el workspace de Daily Operations
daily_ops_hierarchy_router = build_readonly_hierarchy_router(url_prefix="/ops", workspace_label="Daily Operations")
