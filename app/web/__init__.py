"""Aggregates every HTML route module into one router, mounted once in
app.main. Historically split into two files (legacy sensor-viz pages here,
Ops/Planning/Analytics pages in app.ops.web) -- merged into one package as
part of the app/ops -> app/* layer merge; the include_router() order below
is unchanged from before the merge (legacy modules first, then ops modules,
each group in its original relative order), so route-matching precedence
is identical to what it was."""
# Importamos las clases de FastAPI para definir el router, inyectar dependencias y tipar la request
from fastapi import APIRouter, Depends, Request
# Importamos la respuesta HTML para las rutas que renderizan páginas
from fastapi.responses import HTMLResponse

# Importamos la dependencia que resuelve el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos todos los submódulos de rutas web que vamos a montar en este router agregador
from app.web import (
    auth, cases, comparison, crossplots, exports, outliers, quality, users, wells, welllogs,
    admin, analytics, attachments, capture, daily_ops, daily_report, dashboard, engineering,
    hierarchy_readonly, master_data, npt, planning, planning_program, realtime, registers, reports,
    rigs, rop_prediction, search, tree,
)
# Importamos las plantillas Jinja2 configuradas para renderizar las páginas
from app.web.templating import templates

# Creamos el router agregador que va a incluir todos los sub-routers
web_router = APIRouter()


# Definimos la ruta raíz que muestra la página de inicio
@web_router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: User = Depends(get_current_user_web)):
    # Renderizamos la página home con el usuario actual en el contexto
    return templates.TemplateResponse(request, "pages/home.html", {"request": request, "current_user": current_user})


# Legacy sensor-viz pages (unchanged order)
# Montamos las rutas legacy de visualización de sensores en el mismo orden que tenían antes de la fusión
web_router.include_router(auth.router)
web_router.include_router(wells.router)
web_router.include_router(crossplots.router)
web_router.include_router(comparison.router)
web_router.include_router(welllogs.router)
web_router.include_router(outliers.router)
web_router.include_router(cases.router)
web_router.include_router(users.router)
web_router.include_router(exports.router)
web_router.include_router(quality.router)

# Ops / Planning / Analytics pages (unchanged order)
# Montamos las rutas de Ops/Planning/Analytics conservando su orden relativo original
web_router.include_router(admin.router)
web_router.include_router(attachments.router)
web_router.include_router(dashboard.router)
web_router.include_router(analytics.router)
web_router.include_router(rop_prediction.router)
web_router.include_router(reports.router)
web_router.include_router(search.router)
web_router.include_router(master_data.router)
web_router.include_router(planning.router)
web_router.include_router(planning_program.router)
web_router.include_router(engineering.router)
web_router.include_router(daily_ops.router)
web_router.include_router(rigs.router)
web_router.include_router(realtime.router)
web_router.include_router(registers.router)
web_router.include_router(daily_report.router)
web_router.include_router(npt.router)
web_router.include_router(capture.router)
web_router.include_router(hierarchy_readonly.planning_hierarchy_router)
web_router.include_router(hierarchy_readonly.daily_ops_hierarchy_router)
web_router.include_router(tree.master_data_tree_router)
web_router.include_router(tree.planning_tree_router)
web_router.include_router(tree.daily_ops_tree_router)
