import math  # Usamos funciones matemáticas para escalas logarítmicas y muestreo

from fastapi import APIRouter, Depends, Form, Request  # Router y utilidades de FastAPI para las rutas web
from fastapi.responses import HTMLResponse  # Tipo de respuesta HTML para las rutas
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy inyectada

from app.services.exports import _get_label  # Traducimos el nombre técnico de cada parámetro a su etiqueta legible
from app.constants.parameters import get_tracked_parameters  # Obtenemos la lista de parámetros que seguimos en la app
from app.core.deps import get_current_user_web  # Dependencia que exige un usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario autenticado
from app.repositories.well_repository import WellRepository  # Repositorio para consultar los pozos
from app.db.session import get_db, get_depth_db  # Dependencias de sesión: BD principal y BD de dominio profundidad
from app.web.shared import dataset_options, fetch_records, num as _num, parse_dataset_id  # Helpers compartidos entre vistas web
from app.web.templating import templates  # Motor de plantillas Jinja compartido

router = APIRouter()

SAMPLE_SIZE = 50000  # Límite de registros que muestreamos para no sobrecargar el gráfico
DEFAULT_X = "bit_depth_feet"  # Parámetro por defecto para el eje X
DEFAULT_Y = "rate_of_penetration_ft_per_hr"  # Parámetro por defecto para el eje Y


def _log_ticks(values: list[float]) -> list[float]:
    # Si no hay valores, no podemos calcular marcas logarítmicas
    if not values:
        return []
    # Calculamos el exponente mínimo y máximo en base 10 que cubren los valores
    min_exp = math.floor(math.log10(min(values)))
    max_exp = math.ceil(math.log10(max(values)))
    # Devolvemos una marca por cada potencia de 10 dentro del rango
    return [10.0 ** e for e in range(min_exp, max_exp + 1)]


def _build_scatter_payload(
    records: list[dict],
    x_key: str,
    y_key: str,
    x_scale: str,
    y_scale: str,
    max_points: int,
    show_trend_line: bool,
    include_zeros: bool,
) -> dict:
    # Construimos la lista de puntos válidos filtrando valores nulos o incompatibles con la escala
    points = []
    for r in records:
        x = _num(r.get(x_key))
        y = _num(r.get(y_key))
        # Descartamos el registro si falta alguno de los dos valores
        if x is None or y is None:
            continue
        # En escala logarítmica no podemos graficar valores menores o iguales a cero
        if x_scale == "log" and x <= 0:
            continue
        if y_scale == "log" and y <= 0:
            continue
        # Si el usuario no quiere incluir ceros, los descartamos cuando la escala es lineal
        if not include_zeros:
            if (x_scale != "log" and x == 0) or (y_scale != "log" and y == 0):
                continue
        points.append({"x": x, "y": y})

    # Guardamos cuántos puntos válidos había antes de submuestrear
    total_valid = len(points)
    # Si excedemos el máximo de puntos a graficar, tomamos uno cada "step" para reducir la cantidad
    if total_valid > max_points:
        step = math.ceil(total_valid / max_points)
        points = points[::step]

    # Calculamos las marcas del eje logarítmico solo si corresponde a cada eje
    x_log_ticks = _log_ticks([p["x"] for p in points]) if x_scale == "log" else None
    y_log_ticks = _log_ticks([p["y"] for p in points]) if y_scale == "log" else None

    # Calculamos la línea de tendencia (regresión lineal simple) si el usuario la pidió y hay suficientes puntos
    trend_line = None
    if show_trend_line and len(points) >= 2:
        n = len(points)
        sum_x = sum(p["x"] for p in points)
        sum_y = sum(p["y"] for p in points)
        sum_xy = sum(p["x"] * p["y"] for p in points)
        sum_x2 = sum(p["x"] * p["x"] for p in points)
        denom = n * sum_x2 - sum_x * sum_x
        # Evitamos dividir entre cero cuando todos los puntos comparten la misma X
        if denom != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            min_x = min(p["x"] for p in points)
            max_x = max(p["x"] for p in points)
            # Representamos la recta con sus dos puntos extremos
            trend_line = [
                {"x": min_x, "y": slope * min_x + intercept},
                {"x": max_x, "y": slope * max_x + intercept},
            ]

    # Devolvemos el payload completo que consumirá la plantilla del gráfico
    return {
        "points": points,
        "total_valid": total_valid,
        "x_log_ticks": x_log_ticks,
        "y_log_ticks": y_log_ticks,
        "trend_line": trend_line,
    }


def _parameter_options():
    # Armamos la lista de opciones (valor + etiqueta) para los selectores de parámetros
    return [{"value": p, "label": _get_label(p)} for p in get_tracked_parameters()]


@router.get("/crossplots", response_class=HTMLResponse)
async def crossplots_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos para poblar el selector de la página
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Renderizamos la página principal de crossplots con los valores por defecto
    return templates.TemplateResponse(
        request,
        "pages/crossplots.html",
        {
            "request": request,
            "wells": wells,
            "current_user": current_user,
            "parameters": _parameter_options(),
            "default_x": DEFAULT_X,
            "default_y": DEFAULT_Y,
        },
    )


@router.get("/crossplots/datasets", response_class=HTMLResponse)
async def crossplots_dataset_options(
    request: Request,
    well_id: int,
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos las opciones de dataset (raw / procesados) disponibles para el pozo elegido
    options = dataset_options(db, well_id)
    # Devolvemos el fragmento HTML con el selector de dataset ya poblado
    return templates.TemplateResponse(
        request,
        "partials/dataset_select.html",
        {
            "request": request,
            "options": options,
            "select_id": "crossplots-dataset-select",
            "select_name": "dataset_id",
        },
    )


@router.post("/crossplots/plot", response_class=HTMLResponse)
async def crossplots_plot(
    request: Request,
    well_id: str = Form(""),
    dataset_id: str = Form("raw"),
    x_param: str = Form(DEFAULT_X),
    y_param: str = Form(DEFAULT_Y),
    x_scale: str = Form("linear"),
    y_scale: str = Form("linear"),
    max_points: int = Form(1000),
    show_trend_line: bool = Form(False),
    include_zeros: bool = Form(True),
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # well_id arrives as a string so submitting with none selected renders an
    # empty state instead of a silent 422 (htmx doesn't swap on error
    # responses, so the button used to appear to do nothing — same fix
    # pattern already used by wells.py/quality.py).
    # Intentamos convertir well_id a entero; si no se pudo seleccionar un pozo, mostramos un mensaje vacío
    try:
        well_id = int(well_id)
    except (TypeError, ValueError):
        return HTMLResponse('<div class="card p-4"><p class="text-sm" style="color:var(--color-text-muted);">Select a well above to generate a crossplot.</p></div>')

    # Resolvemos el identificador de dataset (raw o el id de un dataset procesado)
    processed_dataset_id = parse_dataset_id(dataset_id)
    # Obtenemos los registros del pozo, ya sea crudos o procesados, con un límite de muestreo
    records = fetch_records(db, well_id, processed_dataset_id, raw_sample_size=SAMPLE_SIZE,
                            processed_page_size=SAMPLE_SIZE)

    # Construimos el payload del scatter plot con los parámetros elegidos por el usuario
    payload = _build_scatter_payload(
        records, x_param, y_param, x_scale, y_scale, max_points, show_trend_line, include_zeros
    )

    # Renderizamos el fragmento del gráfico con las etiquetas y escalas correspondientes
    return templates.TemplateResponse(
        request,
        "partials/crossplot_chart.html",
        {
            "request": request,
            "payload": payload,
            "x_label": _get_label(x_param),
            "y_label": _get_label(y_param),
            "x_scale": x_scale,
            "y_scale": y_scale,
        },
    )
