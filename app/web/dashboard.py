"""Operational dashboard for an Event — KPI roll-up plus the plan-vs-actual
charts (depth/days, cost, NPT, time distribution, trajectory). Read-only view
over the analytics service; no capture here."""
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
# Importamos los repositorios de Event y Wellbore para consultar la jerarquía
from app.repositories.hierarchy_repository import EventRepository, WellboreRepository
# Importamos el servicio que calcula las alertas del evento a partir de sus métricas
from app.services.alerts import event_alerts
# Importamos el servicio que calcula las métricas (KPIs) del evento
from app.services.event_analytics import event_metrics
# Importamos el servicio de benchmarking de campo
from app.services.benchmarking import benchmark_field
# Importamos el servicio que calcula la variación plan-vs-real
from app.services.variance import compute_variance
# Importamos el helper que arma la cadena de nodos abiertos del árbol lateral
from app.web.tree import chain_for_event
# Importamos las plantillas Jinja2 para renderizar las páginas
from app.web.templating import templates

# Creamos el router del dashboard bajo el prefijo /ops
router = APIRouter(prefix="/ops")


# Definimos la ruta de benchmarking entre pozos del campo
@router.get("/benchmark", response_class=HTMLResponse)
async def benchmark(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Calculamos las filas de benchmarking (una por pozo/evento comparado)
    rows = benchmark_field(db)
    # Calculamos el máximo de cada métrica para poder escalar las barras/gráficos en la plantilla
    maxes = {
        "days_per_1000ft": max((r["days_per_1000ft"] or 0) for r in rows) if rows else 0,
        "cost_per_ft": max((r["cost_per_ft"] or 0) for r in rows) if rows else 0,
        "npt_pct": max((r["npt_pct"] or 0) for r in rows) if rows else 0,
    }
    # Renderizamos la página de benchmarking con las filas y los máximos calculados
    return templates.TemplateResponse(
        request, "ops/pages/benchmark.html",
        {"request": request, "current_user": current_user, "rows": rows, "maxes": maxes},
    )


# Definimos la ruta de variación plan-vs-real de un evento
@router.get("/events/{event_id}/variance", response_class=HTMLResponse)
async def event_variance(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Si no existe, devolvemos 404
    if event is None:
        raise HTTPException(404)
    # Buscamos el wellbore al que pertenece el evento
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Calculamos la variación (plan vs real) del evento
    v = compute_variance(db, event_id)
    # Extraemos los KPIs desde las métricas ya calculadas dentro de la variación
    v["kpis"] = v["metrics"]["kpis"]
    # Calculamos la cadena de nodos del árbol lateral hasta este evento
    chain = chain_for_event(event)
    # Renderizamos la página de variación con los datos calculados
    return templates.TemplateResponse(
        request, "ops/pages/variance.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore,
         "v": v, "kpis": v["kpis"], "depth_unit": "ft",
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


# Definimos la ruta del dashboard de KPIs de un evento
@router.get("/events/{event_id}/dashboard", response_class=HTMLResponse)
async def event_dashboard(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Si no existe, devolvemos 404
    if event is None:
        raise HTTPException(404)
    # Buscamos el wellbore al que pertenece el evento
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Calculamos las métricas (KPIs) del evento
    metrics = event_metrics(db, event_id)
    alerts = event_alerts(metrics)  # alerts computed from field-unit metrics (thresholds are unit-agnostic %)
    # Calculamos la cadena de nodos del árbol lateral hasta este evento
    chain = chain_for_event(event)
    # Renderizamos la página del dashboard con las métricas, KPIs y alertas calculadas
    return templates.TemplateResponse(
        request, "ops/pages/dashboard.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore,
         "metrics": metrics, "kpis": metrics["kpis"], "alerts": alerts, "depth_unit": "ft",
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )
