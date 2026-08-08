"""Analytics workspace — advanced analytics / ML-ready surfaces on top of the
operational data: data cleaning (outliers), EAC cost/time forecast (earned
value), cross-well learning curves + lessons mining, NPT categorization /
anomaly / risk, ROP optimization and drilling-dysfunction detection.

Its own top-level workspace (like Dashboard / Planning / Daily Operations); each
submodule is one route rendering a page that includes its result partial. The
heavy lifting lives in app/ops/services/analytics_ml/*."""
# Importamos las clases de FastAPI para el router, dependencias, errores HTTP y requests
from fastapi import APIRouter, Depends, HTTPException, Request
# Importamos la respuesta HTML para las páginas renderizadas
from fastapi.responses import HTMLResponse
# Importamos select para armar consultas explícitas con la API 2.0 de SQLAlchemy
from sqlalchemy import select
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos los modelos de la jerarquía operacional que necesitamos para armar etiquetas
from app.models.hierarchy import Event, Well, Wellbore
# Importamos los servicios de analítica ML: dysfunction, forecast, learning, npt_analytics, rop
from app.services.analytics_ml import dysfunction, forecast, learning, npt_analytics, rop
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates

# Creamos el router y lo montamos bajo el prefijo /analytics
router = APIRouter(prefix="/analytics")

# `svg` is a pipe-separated set of stroke path `d` attributes (viewBox 0 0 24 24),
# matching the app's line-icon language — no emoji.
# `hidden: True` keeps the route/context working but drops the item from the nav.
# Only Data Cleaning, ROP Prediction and Saved Cases are active right now; the
# analytics suite (forecast/learning/NPT/dysfunction) and ROP Optimization are
# suspended until the ML prediction pipeline is built out.
# Definimos la lista de submódulos del workspace, con su ícono y descripción
SUBMODULES = [
    {"key": "cleaning", "title": "Data Cleaning",
     "svg": "M4 5h16l-6 7v6l-4 2v-8L4 5z",
     "desc": "Outlier detection and removal on sensor datasets (the data-quality pipeline)."},
    {"key": "rop-prediction", "title": "ROP Prediction",
     "svg": "M3 3v18h18|M7 14l3-4 3 3 4-6",
     "desc": "Train ML models (XGBoost, LightGBM, …) to predict ROP from drilling parameters across wells."},
    {"key": "forecast", "title": "Cost & Time Forecast (EAC)", "hidden": True,
     "svg": "M3 3v18h18|M18 8l-5 6-3-3-4 5",
     "desc": "Earned-value SPI/CPI and forecast final cost and days at completion."},
    {"key": "learning", "title": "Learning Curves", "hidden": True,
     "svg": "M3 3v18h18|M7 8c4 8 9 9 12 3",
     "desc": "Cross-well days/1000 ft & cost/ft by section, learning-curve fit and lessons mining."},
    {"key": "npt", "title": "NPT Analytics", "hidden": True,
     "svg": "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z|M12 9v4|M12 17h.01",
     "desc": "NPT categorization, statistical anomaly flags and heuristic risk scoring."},
    {"key": "rop", "title": "ROP Optimization", "hidden": True,
     "svg": "M12 15a3 3 0 100-6 3 3 0 000 6z|M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z",
     "desc": "MSE founder-point analysis and parameter recommendations (WOB / RPM / flow)."},
    {"key": "dysfunction", "title": "Dysfunction Detection", "hidden": True,
     "svg": "M14.7 6.3a4 4 0 00-5.66 5.66l-5.66 5.66a2 2 0 002.83 2.83l5.66-5.66a4 4 0 005.66-5.66l-2.83 2.83-2.12-2.12 2.12-2.12z",
     "desc": "Bit balling, stick-slip and founder screening from the drilling record."},
    {"key": "cases", "title": "Saved Cases",
     "svg": "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
     "desc": "Saved outlier-detection cases (cleaned datasets) across all wells."},
]


def _events(db: Session) -> list[dict]:
    """Events with a well/wellbore label for the selector, most recent first."""
    # Preparamos la lista de salida
    out = []
    # Recorremos todos los eventos de la base de datos
    for ev in db.execute(select(Event)).scalars().all():
        # Buscamos el wellbore del evento
        wb = db.get(Wellbore, ev.wellbore_id)
        # Buscamos el pozo del wellbore, si existe
        well = db.get(Well, wb.well_id) if wb else None
        # Armamos la etiqueta combinando nombre de pozo y código de evento (o el id como respaldo)
        label = " · ".join([x for x in [(well.legal_well_name if well else None), ev.event_code] if x]) or str(ev.id)
        out.append({"id": str(ev.id), "label": label, "start": ev.start_date})
    # Dated events first, newest first; undated ones last — under the previous
    # reverse=True sort the (True, None) tuples came FIRST, so an undated event
    # topped the dropdown and became the silently auto-selected default.
    # Importamos datetime localmente solo para obtener la fecha mínima usada en el ordenamiento
    import datetime as _dt
    _MIN = _dt.date.min
    # Ordenamos: primero los eventos con fecha (más recientes primero), luego los sin fecha
    out.sort(key=lambda e: (e["start"] is not None, e["start"] or _MIN), reverse=True)
    return out


def _base_ctx(request: Request, db: Session, current_user: User, active: str, event_id: str | None = None):
    # Obtenemos la lista de eventos disponibles para el selector
    events = _events(db)
    # Si no se especificó evento, seleccionamos el primero (el más reciente) por defecto
    if event_id is None and events:
        event_id = events[0]["id"]
    # Devolvemos el contexto base compartido por todas las páginas de submódulos
    return {"request": request, "current_user": current_user, "submodules": SUBMODULES,
            "active": active, "events": events, "event_id": event_id,
            "depth_unit": "ft"}


@router.get("", response_class=HTMLResponse)
async def analytics_landing(request: Request, current_user: User = Depends(get_current_user_web)):
    """The Analytics hub: one card per ACTIVE submodule. Previously a 302
    straight into Data Cleaning, which orphaned the workspace ("← Analytics"
    links self-looped) and left landing.html as dead code."""
    # Filtramos solo los submódulos activos (no ocultos) para mostrar en la landing
    active = [m for m in SUBMODULES if not m.get("hidden")]
    return templates.TemplateResponse(request, "ops/pages/analytics/landing.html",
                                      {"request": request, "current_user": current_user,
                                       "submodules": active})


@router.get("/forecast", response_class=HTMLResponse)
async def analytics_forecast(request: Request, event_id: str = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Armamos el contexto base para el submódulo de forecast
    ctx = _base_ctx(request, db, current_user, "forecast", event_id)
    # Ejecutamos el análisis de forecast solo si hay un evento seleccionado
    ctx["res"] = forecast.analyze(db, event_id=ctx["event_id"]) if ctx["event_id"] else {}
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/learning", response_class=HTMLResponse)
async def analytics_learning(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Armamos el contexto base para el submódulo de curvas de aprendizaje
    ctx = _base_ctx(request, db, current_user, "learning")
    # Ejecutamos el análisis de learning curves sobre todos los pozos
    ctx["res"] = learning.analyze(db)
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/npt", response_class=HTMLResponse)
async def analytics_npt(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Armamos el contexto base para el submódulo de analítica de NPT
    ctx = _base_ctx(request, db, current_user, "npt")
    # Ejecutamos el análisis de NPT (categorización, anomalías, riesgo)
    ctx["res"] = npt_analytics.analyze(db)
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/rop", response_class=HTMLResponse)
async def analytics_rop(request: Request, event_id: str = None, domain: str = "depth", db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Armamos el contexto base para el submódulo de optimización de ROP
    ctx = _base_ctx(request, db, current_user, "rop", event_id)
    # Guardamos el dominio (profundidad o tiempo) elegido
    ctx["domain"] = domain
    # Ejecutamos el análisis de ROP solo si hay un evento seleccionado
    ctx["res"] = rop.analyze(db, event_id=ctx["event_id"], domain=domain) if ctx["event_id"] else {}
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/dysfunction", response_class=HTMLResponse)
async def analytics_dysfunction(request: Request, event_id: str = None, domain: str = "depth", db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Armamos el contexto base para el submódulo de detección de disfunciones
    ctx = _base_ctx(request, db, current_user, "dysfunction", event_id)
    # Guardamos el dominio (profundidad o tiempo) elegido
    ctx["domain"] = domain
    # Ejecutamos el análisis de disfunciones solo si hay un evento seleccionado
    ctx["res"] = dysfunction.analyze(db, event_id=ctx["event_id"], domain=domain) if ctx["event_id"] else {}
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/cleaning", response_class=HTMLResponse)
async def analytics_cleaning(request: Request, well_id: int = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Data Cleaning = the full sklearn outlier-detection wizard (relocated here
    from the legacy Dashboard workspace). The wizard steps still POST to the
    /outliers/* endpoints; this just hosts its entry point inside Analytics.

    `?well_id=` (from Saved Cases' "Open in Data Cleaning" link) pre-selects the
    well and its saved-case list, so that link lands ready to pick a case
    instead of an empty well picker."""
    # Importamos aquí para evitar acoplar el módulo de outliers en el resto del router
    from app.models.legacy import Well
    from app.web.outliers import WizardState, _service

    # Armamos el contexto base para el submódulo de limpieza de datos
    ctx = _base_ctx(request, db, current_user, "cleaning")
    # Inicializamos el estado del wizard, pre-seleccionando el pozo si vino por query param
    wiz = WizardState({"well_id": str(well_id)} if well_id else {}).base_ctx()
    # Completamos el contexto del wizard: lista de pozos, paso inicial y datasets guardados (si hay pozo)
    wiz.update({"wells": db.query(Well).order_by(Well.well_name).all(),
                "current_step": "well", "errors": [],
                "datasets": _service(db).list_datasets(well_id) if well_id else []})
    ctx.update(wiz)
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)


@router.get("/cases", response_class=HTMLResponse)
async def analytics_cases(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Saved outlier-detection cases (relocated here from the legacy Dashboard).
    The delete action still hits DELETE /cases/{id}."""
    # Importamos aquí para reutilizar el contexto de casos guardados definido en cases.py
    from app.web.cases import _cases_context
    # Armamos el contexto base para el submódulo de casos guardados
    ctx = _base_ctx(request, db, current_user, "cases")
    # Agregamos la lista de casos guardados al contexto
    ctx.update(_cases_context(db))
    return templates.TemplateResponse(request, "ops/pages/analytics/submodule.html", ctx)
