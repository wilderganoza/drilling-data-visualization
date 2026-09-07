"""Global search across the ops hierarchy (companies, projects, sites, wells,
wellbores, events) and daily reports. Case-insensitive substring match on the
natural name/code fields, grouped by entity type. Returns an HTMX fragment so a
header search box can show live results."""
# Importamos las clases de FastAPI para el router, inyección de dependencias y la request
from fastapi import APIRouter, Depends, Request
# Importamos la respuesta HTML para las páginas y fragmentos renderizados
from fastapi.responses import HTMLResponse
# Importamos or_ y select para construir la condición combinada y la consulta
from sqlalchemy import or_, select
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos la dependencia que resuelve el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos la dependencia que nos entrega una sesión de base de datos
from app.db.session import get_db
# Importamos el modelo DailyReport para buscar entre los reportes diarios
from app.models.daily_report import DailyReport
# Importamos los modelos de la jerarquía ops sobre los que buscamos
from app.models.hierarchy import Company, Event, Project, Site, Well, Wellbore
# Importamos las plantillas Jinja2 para renderizar la página/fragmento de resultados
from app.web.templating import templates

# Creamos el router de búsqueda bajo el prefijo /ops
router = APIRouter(prefix="/ops")

# Definimos el máximo de resultados a mostrar por grupo/entidad
PER_GROUP = 8


def _like(col, q):
    # Construimos una condición ILIKE (case-insensitive) de coincidencia parcial
    return col.ilike(f"%{q}%")


def _search(db: Session, q: str) -> list[dict]:
    # Acumulamos aquí los grupos de resultados, uno por tipo de entidad
    groups = []

    def add(icon, label, model, where, link_fn, sub_fn=None):
        # Ejecutamos la consulta filtrada y limitada por grupo
        rows = db.execute(select(model).where(where).limit(PER_GROUP)).scalars().all()
        # Solo agregamos el grupo si hubo resultados
        if rows:
            groups.append({
                "label": label, "icon": icon,
                # Armamos cada resultado con su etiqueta, subetiqueta opcional y enlace
                "results": [{"label": link_fn(r)[0], "sublabel": (sub_fn(r) if sub_fn else ""), "href": link_fn(r)[1]} for r in rows],
            })

    # Buscamos coincidencias en el nombre de las empresas
    add("🏢", "Companies", Company, _like(Company.name, q), lambda r: (r.name, f"/master-data/companies/{r.id}"))
    # Buscamos coincidencias en el nombre de los proyectos
    add("📁", "Projects", Project, _like(Project.name, q), lambda r: (r.name, f"/master-data/projects/{r.id}"))
    # Buscamos coincidencias en el nombre de los sitios
    add("📍", "Sites", Site, _like(Site.name, q), lambda r: (r.name, f"/master-data/sites/{r.id}"))
    # Buscamos coincidencias en el nombre legal, nombre común o UWI de los pozos
    add("🛢️", "Wells", Well,
        or_(_like(Well.legal_well_name, q), _like(Well.common_well_name, q), _like(Well.uwi, q)),
        lambda r: (r.legal_well_name, f"/master-data/wells/{r.id}"), lambda r: (r.uwi or ""))
    # Buscamos coincidencias en el nombre de los wellbores
    add("⛏️", "Wellbores", Wellbore, _like(Wellbore.name, q), lambda r: (r.name, f"/master-data/wellbores/{r.id}"))
    # Buscamos coincidencias en el código o el objetivo de los eventos
    add("📋", "Events", Event,
        or_(_like(Event.event_code, q), _like(Event.objective, q)),
        lambda r: (r.event_code or "Event", f"/planning/events/{r.id}"), lambda r: (r.objective or ""))
    # Buscamos coincidencias en la descripción de los reportes diarios
    add("📅", "Daily reports", DailyReport, _like(DailyReport.description, q),
        lambda r: (f"Report #{r.report_no or '—'} · {r.report_date}", f"/ops/reports/{r.id}"), lambda r: (r.description or ""))
    # Devolvemos todos los grupos armados
    return groups


# Definimos la ruta de búsqueda global
@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "", db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Limpiamos espacios en blanco del término de búsqueda
    q = (q or "").strip()
    # Solo ejecutamos la búsqueda si el término tiene al menos 2 caracteres
    groups = _search(db, q) if len(q) >= 2 else []
    # Si la request viene de HTMX devolvemos solo el fragmento de resultados, si no la página completa
    template = "ops/partials/search_results.html" if request.headers.get("HX-Request") else "ops/pages/search.html"
    # Renderizamos la plantilla elegida con los grupos de resultados
    return templates.TemplateResponse(request, template, {"request": request, "current_user": current_user, "q": q, "groups": groups})
