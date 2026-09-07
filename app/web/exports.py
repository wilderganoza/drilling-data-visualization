from fastapi import APIRouter, Depends, Form, Request  # Piezas de FastAPI para rutas, formularios e inyección
from fastapi.responses import HTMLResponse  # Respuesta HTML para páginas y partials
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.services.exports import download_xlsx, list_columns  # Servicios de negocio: generación del xlsx y listado de columnas disponibles
from app.core.deps import get_current_user_web  # Dependencia que resuelve el usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario
from app.repositories.well_repository import WellRepository  # Repositorio para listar pozos
from app.db.session import get_db, get_depth_db  # Dependencias de sesión: BD general y BD del dominio profundidad
from app.schemas.exports import ExportCaseType, ExportXlsxRequest  # Esquemas para tipar el caso de exportación y la petición del xlsx
from app.web.shared import dataset_options, parse_dataset_id  # Helpers compartidos entre módulos web
from app.web.templating import templates  # Motor de templates Jinja compartido

router = APIRouter()


@router.get("/exports", response_class=HTMLResponse)
async def exports_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos disponibles para poblar el selector
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Renderizamos la página principal de exportaciones
    return templates.TemplateResponse(
        request,
        "pages/exports.html",
        {"request": request, "wells": wells, "current_user": current_user},
    )


@router.get("/exports/datasets", response_class=HTMLResponse)
async def exports_dataset_options(
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
            "select_id": "export-dataset-select",
            "select_name": "dataset_id",
        },
    )


@router.post("/exports/columns", response_class=HTMLResponse)
async def exports_columns(
    request: Request,
    well_id: str = Form(""),
    dataset_id: str = Form("raw"),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # well_id arrives as a string so clicking Continue with none selected
    # renders a message instead of a silent 422 (same fix pattern as wells.py).
    try:
        # Convertimos well_id a entero para poder consultar
        well_id = int(well_id)
    except (TypeError, ValueError):
        # Si no hay pozo seleccionado, mostramos un mensaje en vez de fallar
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">Select a well above, then click Continue.</p>')

    # Resolvemos el id del dataset procesado (o None si se pidió el crudo)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Determinamos el tipo de caso de exportación según si hay dataset procesado o no
    case_type = ExportCaseType.RAW if processed_dataset_id is None else ExportCaseType.PROCESSED

    # Pedimos al servicio la lista de columnas disponibles para ese pozo/caso
    result = await list_columns(
        well_id=well_id,
        case_type=case_type,
        processed_dataset_id=processed_dataset_id,
        db=db,
    )

    # Renderizamos el partial con las columnas disponibles para que el usuario elija
    return templates.TemplateResponse(
        request,
        "partials/exports_columns.html",
        {
            "request": request,
            "well_id": well_id,
            "dataset_id": dataset_id,
            "case_type": case_type.value,
            "columns": result.columns,
        },
    )


@router.post("/exports/download")
async def exports_download(
    request: Request,
    well_id: int = Form(...),
    dataset_id: str = Form("raw"),
    include_all_columns: bool = Form(False),
    include_outliers: bool = Form(False),
    columns: list[str] = Form([]),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Resolvemos el id del dataset procesado (o None si se pidió el crudo)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Determinamos el tipo de caso de exportación según si hay dataset procesado o no
    case_type = ExportCaseType.RAW if processed_dataset_id is None else ExportCaseType.PROCESSED

    # Armamos el payload de la petición de exportación con las columnas elegidas
    payload = ExportXlsxRequest(
        well_id=well_id,
        case_type=case_type,
        processed_dataset_id=processed_dataset_id,
        include_all_columns=include_all_columns,
        columns=None if include_all_columns else columns,
        include_outliers=include_outliers,
    )
    # Generamos y devolvemos el archivo xlsx como descarga
    return await download_xlsx(payload, db)
