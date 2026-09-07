import math  # Usamos funciones matemáticas para percentiles, histogramas y desviación estándar

from fastapi import APIRouter, Depends, Request  # Router y utilidades de FastAPI para las rutas web
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

SAMPLE_SIZE = 50000  # Límite de registros que muestreamos por pozo para no sobrecargar el gráfico
NUM_SLOTS = 5  # Cantidad máxima de pozos que se pueden comparar a la vez
WELL_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]  # Colores asignados a cada slot de comparación
DEFAULT_PARAM = "rate_of_penetration_ft_per_hr"  # Parámetro por defecto a comparar
BINS = 20  # Cantidad de barras del histograma


def _percentile(sorted_values: list[float], p: float) -> float:
    # Ubicamos el índice fraccionario correspondiente al percentil pedido
    index = (p / 100) * (len(sorted_values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    weight = index - lower
    # Si el índice cae exactamente en un valor entero, lo devolvemos directamente
    if lower == upper:
        return sorted_values[lower]
    # Interpolamos linealmente entre el valor inferior y el superior
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _parameter_options():
    # Armamos la lista de opciones (valor + etiqueta) para los selectores de parámetros
    return [{"value": p, "label": _get_label(p)} for p in get_tracked_parameters()]


@router.get("/comparison", response_class=HTMLResponse)
async def comparison_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos todos los pozos para poblar los selectores de la página
    wells = WellRepository(db).get_all(skip=0, limit=1000)
    # Renderizamos la página principal de comparación con los slots y colores disponibles
    return templates.TemplateResponse(
        request,
        "pages/comparison.html",
        {
            "request": request,
            "wells": wells,
            "current_user": current_user,
            "parameters": _parameter_options(),
            "default_param": DEFAULT_PARAM,
            "slots": range(NUM_SLOTS),
            "colors": WELL_COLORS,
        },
    )


@router.get("/comparison/datasets", response_class=HTMLResponse)
async def comparison_dataset_options(
    request: Request,
    well_id: int,
    slot: int,
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Obtenemos las opciones de dataset disponibles para el pozo elegido en este slot
    options = dataset_options(db, well_id)
    # Devolvemos el fragmento HTML con el selector de dataset del slot correspondiente
    return templates.TemplateResponse(
        request,
        "partials/dataset_select.html",
        {
            "request": request,
            "options": options,
            "select_id": f"comparison-dataset-select-{slot}",
            "select_name": f"dataset_id_{slot}",
        },
    )


@router.post("/comparison/plot", response_class=HTMLResponse)
async def comparison_plot(
    request: Request,
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Leemos el formulario completo porque el número de slots es variable
    form = await request.form()
    # Determinamos qué parámetro se está comparando entre los pozos
    comparison_parameter = str(form.get("comparison_parameter", DEFAULT_PARAM))

    # Armamos un diccionario id -> nombre para resolver el nombre de cada pozo rápidamente
    well_repo = WellRepository(db)
    all_wells = {w.id: w.well_name for w in well_repo.get_all(skip=0, limit=1000)}

    wells_payload = []
    all_values_for_bins: list[float] = []
    per_well_values: list[tuple[str, str, list[float]]] = []  # (well_key, well_name, values)

    # Recorremos cada slot de comparación disponible en el formulario
    for slot in range(NUM_SLOTS):
        raw_well_id = form.get(f"well_id_{slot}")
        # Si el slot no tiene pozo seleccionado, lo saltamos
        if not raw_well_id:
            continue
        try:
            well_id = int(raw_well_id)
        except ValueError:
            continue

        # Resolvemos el dataset elegido para este slot (raw o procesado)
        dataset_raw = str(form.get(f"dataset_id_{slot}", "raw"))
        processed_dataset_id = parse_dataset_id(dataset_raw)
        # Obtenemos los registros del pozo de este slot
        records = fetch_records(db, well_id, processed_dataset_id, raw_sample_size=SAMPLE_SIZE, processed_page_size=5000)
        # Si el pozo no tiene registros, lo saltamos
        if not records:
            continue

        points = []
        values = []
        for r in records:
            x = _num(r.get("bit_depth_feet"))
            y = _num(r.get(comparison_parameter))
            # Solo agregamos el punto al gráfico de profundidad si ambos valores existen
            if x is not None and y is not None:
                points.append({"x": x, "y": y})
            # Guardamos el valor del parámetro para las estadísticas y el histograma aunque falte la profundidad
            if y is not None:
                values.append(y)
        # Ordenamos los puntos por profundidad para que la línea se dibuje correctamente
        points.sort(key=lambda p: p["x"])

        well_name = all_wells.get(well_id, f"Well {well_id}")
        well_key = f"w{slot}"
        color = WELL_COLORS[slot % len(WELL_COLORS)]

        wells_payload.append(
            {"well_id": well_id, "well_name": well_name, "key": well_key, "color": color, "points": points}
        )
        per_well_values.append((well_key, well_name, values))
        all_values_for_bins.extend(values)

    # Histogram: 20 bins spanning the combined min/max across all selected wells
    # Calculamos el histograma combinado: 20 barras que cubren el rango de todos los pozos seleccionados
    histogram_bins = []
    histogram_ticks = []
    if all_values_for_bins:
        vmin, vmax = min(all_values_for_bins), max(all_values_for_bins)
        # Evitamos ancho de barra cero cuando todos los valores son iguales
        bin_width = (vmax - vmin) / BINS if vmax > vmin else 1.0
        for i in range(BINS):
            bin_start = vmin + i * bin_width
            bin_end = bin_start + bin_width
            bin_center = (bin_start + bin_end) / 2
            row = {"bin_center": bin_center, "bin_start": bin_start, "bin_end": bin_end, "counts": {}}
            for well_key, _name, values in per_well_values:
                # En la última barra incluimos el límite superior para no perder el valor máximo
                if i == BINS - 1:
                    count = sum(1 for v in values if bin_start <= v <= bin_end)
                else:
                    count = sum(1 for v in values if bin_start <= v < bin_end)
                row["counts"][well_key] = count
            histogram_bins.append(row)

        # Calculamos las marcas del eje X del histograma en base a los centros de las barras
        centers = [b["bin_center"] for b in histogram_bins]
        tmin, tmax = min(centers), max(centers)
        tstep = (tmax - tmin) / 9 if tmax > tmin else 1.0
        histogram_ticks = [tmin + tstep * i for i in range(10)]

    # Stats table
    # Calculamos las estadísticas descriptivas (percentiles, media, desviación) por pozo
    stats = []
    for well in wells_payload:
        well_key = well["key"]
        values = next(v for k, _n, v in per_well_values if k == well_key)
        values = sorted(v for v in values if v is not None)
        # Si el pozo no tiene valores válidos, marcamos la fila como vacía
        if not values:
            stats.append({"well_name": well["well_name"], "color": well["color"], "count": 0, "empty": True})
            continue
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        stats.append(
            {
                "well_name": well["well_name"],
                "color": well["color"],
                "count": len(values),
                "min": values[0],
                "p25": _percentile(values, 25),
                "p50": _percentile(values, 50),
                "p75": _percentile(values, 75),
                "max": values[-1],
                "mean": mean,
                "std": std,
                "empty": False,
            }
        )

    # Renderizamos el fragmento con los gráficos de dispersión, el histograma y la tabla de estadísticas
    return templates.TemplateResponse(
        request,
        "partials/comparison_charts.html",
        {
            "request": request,
            "has_data": len(wells_payload) > 0,
            "wells": wells_payload,
            "histogram_bins": histogram_bins,
            "histogram_ticks": histogram_ticks,
            "stats": stats,
            "comparison_label": _get_label(comparison_parameter),
        },
    )
