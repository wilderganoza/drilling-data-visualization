import pandas as pd  # Usamos pandas para calcular estadísticas y cuartiles de forma vectorizada
from fastapi import APIRouter, Depends, Form, Request  # Router y utilidades de FastAPI para las rutas web
from fastapi.responses import HTMLResponse  # Tipo de respuesta HTML para las rutas
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy inyectada

from app.services.exports import _get_label  # Traducimos el nombre técnico de cada parámetro a su etiqueta legible
from app.constants.parameters import get_tracked_parameters  # Obtenemos la lista de parámetros que seguimos en la app
from app.core.deps import get_current_user_web  # Dependencia que exige un usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario autenticado
from app.repositories.well_repository import WellRepository  # Repositorio para consultar los pozos
from app.db.session import db_manager, get_db, get_depth_db  # Gestor de BD + dependencias de sesión: BD principal y BD de dominio profundidad
from app.schemas.processing import DataQualityReport  # Esquema con la estructura del reporte de calidad de datos
from app.web.shared import dataset_options, fetch_records, parse_dataset_id, wells_for_domain  # Helpers compartidos entre vistas web
from app.web.templating import templates  # Motor de plantillas Jinja compartido

router = APIRouter()


def _build_report_from_records(records: list[dict], well_id: int) -> DataQualityReport:
    # Si no hay registros, devolvemos un reporte vacío con puntaje cero
    if not records:
        return DataQualityReport(
            well_id=well_id, total_records=0, columns_analyzed=0,
            missing_values={}, outliers_detected={}, data_ranges={}, quality_score=0.0,
        )

    # Cargamos los registros en un DataFrame para poder calcular estadísticas fácilmente
    df = pd.DataFrame(records)
    # Nos quedamos solo con los parámetros seguidos que efectivamente existen en el DataFrame
    tracked = [p for p in get_tracked_parameters() if p in df.columns]
    # Identificamos las columnas numéricas, excluyendo los identificadores
    numeric_cols = [c for c in df.select_dtypes(include=["number"]).columns if c not in ("id", "well_id")]

    # Contamos valores faltantes por columna: nulos reales más ceros (que aquí también consideramos "faltantes")
    missing_values = {c: int(df[c].isna().sum() + (df[c] == 0).sum()) for c in numeric_cols}
    outliers_detected: dict[str, int] = {}
    data_ranges: dict[str, dict] = {}

    for col in tracked:
        series = df[col]
        # Calculamos el rango intercuartílico para detectar valores atípicos
        Q1, Q3 = series.quantile(0.25), series.quantile(0.75)
        IQR = Q3 - Q1
        lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
        # Contamos cuántos valores caen fuera de los límites de Tukey
        outliers_detected[col] = int(((series < lower) | (series > upper)).sum())

        # Contamos nulos y ceros para calcular el porcentaje de faltantes de esta columna
        null_count = series.isna().sum() + (series == 0).sum()
        # Limpiamos la serie quitando ceros y nulos antes de calcular estadísticas descriptivas
        clean = series.replace(0, pd.NA).dropna()
        data_ranges[col] = {
            "min": float(clean.min()) if len(clean) else 0.0,
            "max": float(clean.max()) if len(clean) else 0.0,
            "mean": float(clean.mean()) if len(clean) else 0.0,
            "std": float(clean.std()) if len(clean) else 0.0,
            "p25": float(clean.quantile(0.25)) if len(clean) else 0.0,
            "p50": float(clean.quantile(0.50)) if len(clean) else 0.0,
            "p75": float(clean.quantile(0.75)) if len(clean) else 0.0,
            "null_pct": float(null_count / len(df) * 100) if len(df) else 0.0,
        }

    # Calculamos el puntaje de calidad general en base al porcentaje de celdas faltantes y atípicas
    total_cells = len(df) * len(numeric_cols)
    missing_cells = sum(missing_values.values())
    outlier_cells = sum(outliers_detected.values())
    quality_score = (
        max(0, 100 - (missing_cells / total_cells * 50) - (outlier_cells / total_cells * 50))
        if total_cells > 0
        else 100.0
    )

    # Devolvemos el reporte de calidad completo
    return DataQualityReport(
        well_id=well_id,
        total_records=len(df),
        columns_analyzed=len(numeric_cols),
        missing_values=missing_values,
        outliers_detected=outliers_detected,
        data_ranges=data_ranges,
        quality_score=round(quality_score, 2),
    )


@router.get("/quality", response_class=HTMLResponse)
async def quality_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos para poblar el selector de la página
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Renderizamos la página principal de calidad de datos
    return templates.TemplateResponse(
        request,
        "pages/quality.html",
        {"request": request, "wells": wells, "current_user": current_user,
         "has_time_data": db_manager.has_time_data()},
    )


@router.get("/quality/well-options", response_class=HTMLResponse)
async def quality_well_options(
    request: Request,
    domain: str = "depth",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Filtramos los pozos según el dominio elegido (profundidad o tiempo)
    wells, time_ids = wells_for_domain(db, domain)
    # Devolvemos el fragmento HTML con las opciones de pozo ya filtradas
    return templates.TemplateResponse(
        request,
        "partials/well_options.html",
        {"request": request, "wells": wells, "time_well_ids": time_ids},
    )


@router.get("/quality/datasets", response_class=HTMLResponse)
async def quality_dataset_options(
    request: Request,
    well_id: int,
    domain: str = "depth",
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos las opciones de dataset disponibles para el pozo y dominio elegidos
    options = dataset_options(db, well_id, domain)
    # Devolvemos el fragmento HTML con el selector de dataset ya poblado
    return templates.TemplateResponse(
        request,
        "partials/dataset_select.html",
        {
            "request": request,
            "options": options,
            "select_id": "quality-dataset-select",
            "select_name": "dataset_id",
        },
    )


@router.post("/quality/report", response_class=HTMLResponse)
async def quality_report(
    request: Request,
    well_id: str = Form(""),
    dataset_id: str = Form("raw"),
    domain: str = Form("depth"),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # well_id is a string so an empty submission (e.g. clicking "Open Report" before
    # picking a well, which happens right after switching domain) renders the empty
    # state instead of a 422.
    # Intentamos convertir well_id a entero; si no hay pozo seleccionado, devolvemos un reporte vacío
    try:
        well_id = int(well_id)
    except (TypeError, ValueError):
        report = _build_report_from_records([], 0)
        return templates.TemplateResponse(
            request,
            "partials/quality_report.html",
            {"request": request, "report": report, "completeness": [], "ranges": []},
        )

    # Resolvemos el identificador de dataset (raw o el id de un dataset procesado)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Both raw and processed reports are built from fetched records so the report is
    # domain-aware (depth vs time) without depending on the depth-only API endpoint.
    # Obtenemos los registros del pozo respetando el dominio (profundidad o tiempo)
    records = fetch_records(
        db, well_id, processed_dataset_id,
        raw_sample_size=50000, processed_page_size=5000, domain=domain,
    )
    # Construimos el reporte de calidad a partir de los registros obtenidos
    report = _build_report_from_records(records, well_id)

    # Calculamos el porcentaje de completitud de cada parámetro seguido, para la tabla de completitud
    tracked = get_tracked_parameters()
    completeness = []
    for col in tracked:
        has_data = col in report.missing_values
        missing = report.missing_values.get(col, report.total_records)
        pct = ((report.total_records - missing) / report.total_records * 100) if has_data and report.total_records else 0.0
        completeness.append({"column": col, "label": _get_label(col), "completeness": pct})
    # Ordenamos de mayor a menor completitud para que lo más confiable aparezca primero
    completeness.sort(key=lambda c: c["completeness"], reverse=True)

    # Armamos la tabla de rangos estadísticos por parámetro
    ranges = []
    for col in tracked:
        r = report.data_ranges.get(col)
        ranges.append({"column": col, "label": _get_label(col), "range": r})

    # Renderizamos el fragmento con el reporte, la completitud y los rangos calculados
    return templates.TemplateResponse(
        request,
        "partials/quality_report.html",
        {
            "request": request,
            "report": report,
            "completeness": completeness,
            "ranges": ranges,
        },
    )
