from fastapi import APIRouter, Depends, Form, Request  # Piezas de FastAPI para rutas, formularios e inyección
from fastapi.responses import HTMLResponse  # Respuesta HTML para las páginas y partials
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.services.exports import _get_label  # Función para obtener la etiqueta legible de un parámetro
from app.constants.parameters import get_tracked_parameters  # Lista de parámetros que la app rastrea/grafica
from app.core.deps import get_current_user_web  # Dependencia que resuelve el usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario
from app.repositories.well_repository import WellRepository  # Repositorio para listar pozos
from app.db.session import get_db, get_depth_db  # Dependencias de sesión: BD general y BD del dominio profundidad
from app.web.shared import dataset_options, fetch_records, num as _num, parse_dataset_id  # Helpers compartidos entre módulos web
from app.web.templating import templates  # Motor de templates Jinja compartido

router = APIRouter()

RAW_SAMPLE_SIZE = 50000
PROCESSED_PAGE_SIZE = 5000
DEPTH_KEY = "bit_depth_feet"


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos disponibles para poblar el selector
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Renderizamos la página principal de logs de pozo
    return templates.TemplateResponse(
        request,
        "pages/logs.html",
        {"request": request, "wells": wells, "current_user": current_user},
    )


@router.get("/logs/datasets", response_class=HTMLResponse)
async def logs_dataset_options(
    request: Request,
    well_id: int,
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Calculamos las opciones de dataset (crudo + casos de limpieza) para el pozo elegido
    options = dataset_options(db, well_id)
    # Renderizamos el partial del selector de dataset
    return templates.TemplateResponse(
        request,
        "partials/dataset_select.html",
        {
            "request": request,
            "options": options,
            "select_id": "logs-dataset-select",
            "select_name": "dataset_id",
        },
    )


@router.post("/logs/open", response_class=HTMLResponse)
async def logs_open(
    request: Request,
    well_id: str = Form(""),
    dataset_id: str = Form("raw"),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # well_id arrives as a string so submitting with none selected renders an
    # empty state instead of a silent 422 (same fix pattern as wells.py).
    try:
        # Convertimos well_id a entero para poder consultar
        well_id = int(well_id)
    except (TypeError, ValueError):
        # Si no hay pozo seleccionado, devolvemos un estado vacío en vez de fallar
        return HTMLResponse('<div class="card p-4"><p class="text-sm" style="color:var(--color-text-muted);">Select a well above to open its log view.</p></div>')

    # Resolvemos el id del dataset procesado (o None si se pidió el crudo)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Obtenemos la lista de parámetros que la app rastrea
    tracked = get_tracked_parameters()
    # Armamos el orden de columnas a conservar: primero la profundidad, luego el resto
    keep_keys = [DEPTH_KEY] + [p for p in tracked if p != DEPTH_KEY]

    # Obtenemos los registros crudos o procesados del pozo, según corresponda
    raw_records = fetch_records(
        db, well_id, processed_dataset_id,
        raw_sample_size=RAW_SAMPLE_SIZE, processed_page_size=PROCESSED_PAGE_SIZE,
    )

    records = []
    for r in raw_records:
        # Recortamos cada registro a solo las claves rastreadas, convirtiendo a número
        trimmed = {k: _num(r.get(k)) for k in keep_keys if k in r}
        # Solo conservamos filas que tengan un valor de profundidad válido
        if trimmed.get(DEPTH_KEY) is not None:
            records.append(trimmed)

    available_parameters = []
    if records:
        # Detectamos qué parámetros están realmente presentes en los datos, usando la primera fila
        first = records[0]
        available_parameters = [p for p in tracked if p in first and p != DEPTH_KEY]

    # Armamos el diccionario de etiquetas legibles para cada parámetro rastreado
    param_labels = {p: _get_label(p) for p in tracked}

    # Renderizamos el visor de log de pozo con los datos preparados
    return templates.TemplateResponse(
        request,
        "partials/welllog_view.html",
        {
            "request": request,
            "has_data": len(records) > 0,
            "records": records,
            "depth_key": DEPTH_KEY,
            "axis_label": "Depth (ft)",
            "available_parameters": available_parameters,
            "param_labels": param_labels,
        },
    )
