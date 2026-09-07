"""Master Data workspace: full CRUD on the Company -> Project -> Site -> Well
-> Wellbore physical/organizational hierarchy. Events are operational
campaigns, not master data — they're created in Planning (planning a new
operation *is* creating its Event) and worked within Daily Operations; this
workspace only owns what rarely changes."""
# Importamos utilidades de fecha para parsear los campos de formulario tipo fecha
from datetime import date, datetime
# Importamos Optional para tipar los parámetros de formulario que pueden venir vacíos
from typing import Optional

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias, leer formularios y lanzar errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos los tipos de respuesta que usamos: HTML para las páginas/parciales y Redirect para el índice
from fastapi.responses import HTMLResponse, RedirectResponse
# Importamos la sesión de SQLAlchemy para tipar la dependencia de base de datos
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado desde la cookie de sesión
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos la dependencia que nos entrega una sesión de base de datos por request
from app.db.session import get_db
# Importamos los helpers de permisos: require_ops_role bloquea la ruta, has_ops_role solo consulta si el usuario puede editar
from app.core.permissions import require_ops_role, has_ops_role
# Importamos el enum de roles operativos usados en los chequeos de permisos
from app.core.ops_roles import OpsRole
# Importamos los repositorios de cada nivel de la jerarquía (Company, Project, Site, Well, Wellbore)
from app.repositories.hierarchy_repository import (
    CompanyRepository,
    ProjectRepository,
    SiteRepository,
    WellRepository,
    WellboreRepository,
)
# Importamos los helpers que arman la cadena de "breadcrumb" (árbol abierto/activo) para cada nivel
from app.web.tree import chain_for_company, chain_for_project, chain_for_site, chain_for_well, chain_for_wellbore
# Importamos el motor de templates compartido por toda la app
from app.web.templating import templates

# Creamos el router de Master Data con el prefijo /master-data
router = APIRouter(prefix="/master-data")

# Definimos la dependencia que exige rol de Admin u Office Engineer para poder editar (crear/borrar)
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)


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


# Redirigimos la raíz de Master Data hacia el listado de compañías
@router.get("/", response_class=RedirectResponse)
async def master_data_index():
    return RedirectResponse(url="/master-data/companies", status_code=302)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

@router.get("/companies", response_class=HTMLResponse)
async def companies_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Listamos todas las compañías ordenadas por nombre
    companies = CompanyRepository(db).list(order_by=CompanyRepository.model.name)
    # Verificamos si el usuario actual tiene permiso de edición para mostrar/ocultar los controles de la UI
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    # Renderizamos la página completa de compañías
    return templates.TemplateResponse(request, "ops/pages/companies.html", {"request": request, "current_user": current_user, "companies": companies, "can_edit": can_edit})


@router.post("/companies", response_class=HTMLResponse)
async def create_company(request: Request, name: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = CompanyRepository(db)
    # Creamos la compañía con el nombre recortado y registramos quién la creó
    repo.create(name=name.strip(), created_by=current_user.id)
    # Confirmamos la transacción en la base de datos
    db.commit()
    # Volvemos a listar las compañías ya actualizadas para refrescar la sección
    companies = repo.list(order_by=CompanyRepository.model.name)
    # Devolvemos solo el fragmento HTML de la sección (patrón HTMX)
    return templates.TemplateResponse(request, "ops/partials/company_section.html", {"request": request, "companies": companies})


@router.delete("/companies/{company_id}", response_class=HTMLResponse)
async def delete_company(request: Request, company_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = CompanyRepository(db)
    # Buscamos la compañía a eliminar
    instance = repo.get(company_id)
    # Si no existe, devolvemos 404
    if instance is None:
        raise HTTPException(404)
    # Eliminamos la compañía encontrada
    repo.delete(instance)
    db.commit()
    # Recalculamos el listado tras el borrado
    companies = repo.list(order_by=CompanyRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/company_section.html", {"request": request, "companies": companies})


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_detail(request: Request, company_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos la compañía solicitada
    company = CompanyRepository(db).get(company_id)
    if company is None:
        raise HTTPException(404)
    # Listamos los proyectos que pertenecen a esta compañía
    projects = ProjectRepository(db).list(filters={"company_id": company_id}, order_by=ProjectRepository.model.name)
    # Calculamos la cadena de nodos para el árbol lateral (abiertos/activo)
    chain = chain_for_company(company)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return templates.TemplateResponse(
        request, "ops/pages/company_detail.html",
        {"request": request, "current_user": current_user, "company": company, "projects": projects,
         "tree_open_ids": chain, "tree_active_id": chain[-1], "can_edit": can_edit},
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

@router.post("/companies/{company_id}/projects", response_class=HTMLResponse)
async def create_project(request: Request, company_id: str, name: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Verificamos que la compañía padre exista antes de crear el proyecto
    company = CompanyRepository(db).get(company_id)
    if company is None:
        raise HTTPException(404)
    repo = ProjectRepository(db)
    # Creamos el proyecto asociado a la compañía
    repo.create(company_id=company_id, name=name.strip(), created_by=current_user.id)
    db.commit()
    # Refrescamos el listado de proyectos de la compañía
    projects = repo.list(filters={"company_id": company_id}, order_by=ProjectRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/project_section.html", {"request": request, "company": company, "projects": projects})


@router.delete("/projects/{project_id}", response_class=HTMLResponse)
async def delete_project(request: Request, project_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = ProjectRepository(db)
    instance = repo.get(project_id)
    if instance is None:
        raise HTTPException(404)
    # Guardamos el id de la compañía padre antes de borrar, para poder recargar la sección después
    company_id = instance.company_id
    repo.delete(instance)
    db.commit()
    company = CompanyRepository(db).get(company_id)
    projects = repo.list(filters={"company_id": company_id}, order_by=ProjectRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/project_section.html", {"request": request, "company": company, "projects": projects})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    project = ProjectRepository(db).get(project_id)
    if project is None:
        raise HTTPException(404)
    # Obtenemos la compañía padre para mostrarla en el detalle
    company = CompanyRepository(db).get(project.company_id)
    # Listamos los sitios que pertenecen a este proyecto
    sites = SiteRepository(db).list(filters={"project_id": project_id}, order_by=SiteRepository.model.name)
    chain = chain_for_project(project)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return templates.TemplateResponse(
        request, "ops/pages/project_detail.html",
        {"request": request, "current_user": current_user, "project": project, "company": company, "sites": sites,
         "tree_open_ids": chain, "tree_active_id": chain[-1], "can_edit": can_edit},
    )


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/sites", response_class=HTMLResponse)
async def create_site(request: Request, project_id: str, name: str = Form(...), location: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Verificamos que el proyecto padre exista
    project = ProjectRepository(db).get(project_id)
    if project is None:
        raise HTTPException(404)
    repo = SiteRepository(db)
    # Creamos el sitio, normalizando la ubicación opcional
    repo.create(project_id=project_id, name=name.strip(), location=_opt(location), created_by=current_user.id)
    db.commit()
    sites = repo.list(filters={"project_id": project_id}, order_by=SiteRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/site_section.html", {"request": request, "project": project, "sites": sites})


@router.delete("/sites/{site_id}", response_class=HTMLResponse)
async def delete_site(request: Request, site_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = SiteRepository(db)
    instance = repo.get(site_id)
    if instance is None:
        raise HTTPException(404)
    # Guardamos el id del proyecto padre antes de borrar
    project_id = instance.project_id
    repo.delete(instance)
    db.commit()
    project = ProjectRepository(db).get(project_id)
    sites = repo.list(filters={"project_id": project_id}, order_by=SiteRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/site_section.html", {"request": request, "project": project, "sites": sites})


@router.get("/sites/{site_id}", response_class=HTMLResponse)
async def site_detail(request: Request, site_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    site = SiteRepository(db).get(site_id)
    if site is None:
        raise HTTPException(404)
    project = ProjectRepository(db).get(site.project_id)
    # Listamos los pozos (wells) que pertenecen a este sitio, ordenados por nombre legal
    wells = WellRepository(db).list(filters={"site_id": site_id}, order_by=WellRepository.model.legal_well_name)
    chain = chain_for_site(site)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return templates.TemplateResponse(
        request, "ops/pages/site_detail.html",
        {"request": request, "current_user": current_user, "site": site, "project": project, "wells": wells,
         "tree_open_ids": chain, "tree_active_id": chain[-1], "can_edit": can_edit},
    )


# ---------------------------------------------------------------------------
# Well
# ---------------------------------------------------------------------------

@router.post("/sites/{site_id}/wells", response_class=HTMLResponse)
async def create_well(
    request: Request, site_id: str,
    legal_well_name: str = Form(...), common_well_name: str = Form(""), uwi: str = Form(""),
    operator: str = Form(""), target_formation: str = Form(""), spud_date: str = Form(""),
    country: str = Form(""), well_classification: str = Form(""),
    datum_elevation: str = Form(""), ground_elevation: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Verificamos que el sitio padre exista
    site = SiteRepository(db).get(site_id)
    if site is None:
        raise HTTPException(404)
    repo = WellRepository(db)
    # Creamos el pozo normalizando todos los campos opcionales de texto, fecha y número
    repo.create(
        site_id=site_id, legal_well_name=legal_well_name.strip(), common_well_name=_opt(common_well_name),
        uwi=_opt(uwi), operator=_opt(operator), target_formation=_opt(target_formation),
        spud_date=_opt_date(spud_date), country=_opt(country), well_classification=_opt(well_classification),
        datum_elevation=_opt_num(datum_elevation), ground_elevation=_opt_num(ground_elevation),
        created_by=current_user.id,
    )
    db.commit()
    wells = repo.list(filters={"site_id": site_id}, order_by=WellRepository.model.legal_well_name)
    return templates.TemplateResponse(request, "ops/partials/well_section.html", {"request": request, "site": site, "wells": wells})


@router.delete("/wells/{well_id}", response_class=HTMLResponse)
async def delete_well(request: Request, well_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = WellRepository(db)
    instance = repo.get(well_id)
    if instance is None:
        raise HTTPException(404)
    # Guardamos el id del sitio padre antes de borrar
    site_id = instance.site_id
    repo.delete(instance)
    db.commit()
    site = SiteRepository(db).get(site_id)
    wells = repo.list(filters={"site_id": site_id}, order_by=WellRepository.model.legal_well_name)
    return templates.TemplateResponse(request, "ops/partials/well_section.html", {"request": request, "site": site, "wells": wells})


@router.get("/wells/{well_id}", response_class=HTMLResponse)
async def well_detail(request: Request, well_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    well = WellRepository(db).get(well_id)
    if well is None:
        raise HTTPException(404)
    site = SiteRepository(db).get(well.site_id)
    # Listamos los wellbores (ramales) que pertenecen a este pozo
    wellbores = WellboreRepository(db).list(filters={"well_id": well_id}, order_by=WellboreRepository.model.name)
    chain = chain_for_well(well)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return templates.TemplateResponse(
        request, "ops/pages/well_detail.html",
        {"request": request, "current_user": current_user, "well": well, "site": site, "wellbores": wellbores,
         "tree_open_ids": chain, "tree_active_id": chain[-1], "can_edit": can_edit},
    )


# ---------------------------------------------------------------------------
# Wellbore
# ---------------------------------------------------------------------------

@router.post("/wells/{well_id}/wellbores", response_class=HTMLResponse)
async def create_wellbore(
    request: Request, well_id: str, name: str = Form(...), sidetrack_no: str = Form(""), trajectory_type: str = Form(""),
    api12: str = Form(""), arch_no: str = Form(""), start_date: str = Form(""),
    vs_azimuth: str = Form(""), max_angle_est: str = Form(""),
    kick_off_top_md: str = Form(""), kick_off_top_tvd: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Verificamos que el pozo padre exista
    well = WellRepository(db).get(well_id)
    if well is None:
        raise HTTPException(404)
    repo = WellboreRepository(db)
    # Creamos el wellbore normalizando todos los campos opcionales
    repo.create(
        well_id=well_id, name=name.strip(), sidetrack_no=_opt(sidetrack_no), trajectory_type=_opt(trajectory_type),
        api12=_opt(api12), arch_no=_opt(arch_no), start_date=_opt_date(start_date),
        vs_azimuth=_opt_num(vs_azimuth), max_angle_est=_opt_num(max_angle_est),
        kick_off_top_md=_opt_num(kick_off_top_md), kick_off_top_tvd=_opt_num(kick_off_top_tvd),
        created_by=current_user.id,
    )
    db.commit()
    wellbores = repo.list(filters={"well_id": well_id}, order_by=WellboreRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/wellbore_section.html", {"request": request, "well": well, "wellbores": wellbores})


@router.delete("/wellbores/{wellbore_id}", response_class=HTMLResponse)
async def delete_wellbore(request: Request, wellbore_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = WellboreRepository(db)
    instance = repo.get(wellbore_id)
    if instance is None:
        raise HTTPException(404)
    # Guardamos el id del pozo padre antes de borrar
    well_id = instance.well_id
    repo.delete(instance)
    db.commit()
    well = WellRepository(db).get(well_id)
    wellbores = repo.list(filters={"well_id": well_id}, order_by=WellboreRepository.model.name)
    return templates.TemplateResponse(request, "ops/partials/wellbore_section.html", {"request": request, "well": well, "wellbores": wellbores})


@router.get("/wellbores/{wellbore_id}", response_class=HTMLResponse)
async def wellbore_detail(request: Request, wellbore_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    wellbore = WellboreRepository(db).get(wellbore_id)
    if wellbore is None:
        raise HTTPException(404)
    well = WellRepository(db).get(wellbore.well_id)
    chain = chain_for_wellbore(wellbore)
    can_edit = has_ops_role(db, current_user, OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
    return templates.TemplateResponse(
        request, "ops/pages/wellbore_detail.html",
        {"request": request, "current_user": current_user, "wellbore": wellbore, "well": well,
         "tree_open_ids": chain, "tree_active_id": chain[-1], "can_edit": can_edit},
    )
