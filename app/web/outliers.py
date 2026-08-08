"""Outlier Detection wizard — a stateless, 6-step HTMX port of OutlierDetection.tsx.

All wizard state (well/variables/scaling/pca/outlier config) is carried
forward as hidden form fields on every request, mirroring the pattern used
elsewhere in this app (no server-side session). Each step is rendered by a
dedicated function reused by both the "Next" button of the preceding step
and the "Back" button of the following step.
"""
# Importamos math para calcular percentiles/histogramas a mano (cuantiles, bins)
import math
# Importamos Optional para tipar los valores que pueden venir vacíos
from typing import Optional

# Importamos pandas para construir DataFrames y calcular correlaciones/estadísticas
import pandas as pd
# Importamos las piezas de FastAPI que usamos para el router, la inyección de dependencias y la request
from fastapi import APIRouter, Depends, Request
# Importamos HTMLResponse para tipar las respuestas de los fragmentos HTMX
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session
# Importamos ValidationError para convertirla en la excepción de dominio del wizard
from pydantic import ValidationError

# Importamos el helper que traduce un nombre de columna a su etiqueta legible
from app.services.exports import _get_label
# Importamos la función que nos da la lista de parámetros rastreados (candidatos numéricos)
from app.constants.parameters import get_tracked_parameters
# Importamos la dependencia que exige un usuario autenticado por cookie
from app.core.deps import get_current_user_web
# Importamos los modelos de usuario y pozo
from app.models.legacy import User, Well
# Importamos el repositorio que sabe consultar los datos de sensores por pozo
from app.repositories.data_repository import DataRepository
# Importamos el manejador de sesiones/BD y las dependencias get_db / get_depth_db
from app.db.session import db_manager, get_db, get_depth_db
# Importamos los esquemas Pydantic que arman el request del pipeline de outliers
from app.schemas.outliers import (
    OutlierConfig,
    OutlierDetectionRequest,
    PCAConfig,
    ScalingConfig,
)
# Importamos el servicio que ejecuta el pipeline (escalado, PCA, detección) y su excepción de dominio
from app.services.outlier_detection import OutlierDetectionError, OutlierDetectionService
# Importamos el motor de templates Jinja compartido por toda la app
from app.web.templating import templates

# Creamos el router donde registramos todas las rutas del wizard
router = APIRouter()

# Definimos el orden de los pasos del wizard
STEP_ORDER = ["well", "variables", "outlier", "scaling", "pca", "review"]
# Definimos los títulos legibles de cada paso, para mostrarlos en la UI
STEP_TITLES = {
    "well": "Well & dataset",
    "variables": "Variables",
    "scaling": "Scaling",
    "pca": "PCA",
    "outlier": "Outlier detection",
    "review": "Review & run",
}
# Definimos cuántos registros muestreamos como máximo para las previsualizaciones
SAMPLE_SIZE = 100000

# Thresholds for the "recommended variables" pre-selection: complete enough,
# not near-constant, and de-duplicated when two variables move together.
# Definimos el umbral mínimo de completitud (%) para recomendar una variable
RECOMMEND_MIN_COMPLETENESS = 80.0
# Definimos el umbral mínimo de coeficiente de variación para descartar variables casi constantes
RECOMMEND_MIN_CV = 0.01
# Definimos el umbral de correlación a partir del cual consideramos dos variables redundantes
RECOMMEND_CORR_THRESHOLD = 0.9

# Definimos qué parámetros acepta cada método de detección de outliers
OUTLIER_PARAM_ALLOWLIST = {
    "isolation_forest": ["contamination", "n_estimators"],
    "dbscan": ["eps", "min_samples"],
    "local_outlier_factor": ["n_neighbors"],
    "zscore": ["threshold"],
    "iqr": ["multiplier"],
}


# Construimos el servicio de detección de outliers apuntando a la tabla de datos por profundidad
def _service(db: Session) -> OutlierDetectionService:
    # Obtenemos el nombre físico de la tabla well_data para el dominio "depth"
    table = db_manager.get_depth_table("well_data")
    # Devolvemos el servicio ya configurado con la sesión y la tabla
    return OutlierDetectionService(db, table)


# Convertimos un valor arbitrario a float, devolviendo None si no es numérico o es NaN
def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        # Devolvemos None si el valor no se puede convertir a float
        return None
    # Devolvemos el float solo si no es NaN (NaN nunca es igual a sí mismo)
    return f if f == f else None


# Leemos el form de la request y lo convertimos a un dict plano (colapsando listas de un solo valor)
async def _form_dict(request: Request) -> dict:
    # Parseamos el cuerpo de la request como form-data
    form = await request.form()
    result = {}
    for key in form.keys():
        # Obtenemos todos los valores repetidos para esta clave (ej. checkboxes múltiples)
        values = form.getlist(key)
        # Si hay más de un valor lo dejamos como lista, si hay uno solo lo desempaquetamos
        result[key] = values if len(values) > 1 else values[0]
    return result


# Normalizamos un valor de formulario a lista (para campos que pueden venir como string único o lista)
def _as_list(value) -> list:
    if value is None:
        # Devolvemos lista vacía cuando no hay valor
        return []
    if isinstance(value, list):
        # Devolvemos el valor tal cual si ya es una lista
        return value
    # Envolvemos el valor único en una lista de un elemento
    return [value]


# Convertimos un valor de formulario a float, tratando vacío/None como ausencia de valor
def _as_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # Devolvemos None si el valor no es un float válido
        return None


# Convertimos un valor de formulario a int (pasando por float primero, por si viene "3.0")
def _as_int(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        # Devolvemos None si el valor no es un entero válido
        return None


# Definimos el estado del wizard, reconstruido en cada request a partir de los campos ocultos
class WizardState:
    """Parses the accumulated hidden-field form data into typed config."""

    def __init__(self, form: dict):
        # Guardamos el form crudo por si necesitamos leer claves dinámicas (ej. outlier_<param>)
        self.form = form
        # Leemos el id del pozo seleccionado
        self.well_id = _as_int(form.get("well_id"))
        # Leemos el nombre que se le dará al dataset resultante
        self.dataset_name = (form.get("dataset_name") or "").strip()
        # Leemos la descripción opcional del dataset
        self.description = (form.get("description") or "").strip()
        # Leemos las variables seleccionadas, descartando valores vacíos
        self.variables = [v for v in _as_list(form.get("variables")) if v]
        # Leemos el método de escalado, con "standard" como valor por defecto
        self.scaling_method = form.get("scaling_method") or "standard"
        # Leemos si PCA está habilitado (por defecto sí)
        self.pca_enabled = form.get("pca_enabled", "true") == "true"
        # Leemos el número de componentes de PCA a conservar
        self.pca_n_components = _as_int(form.get("pca_n_components"))
        # Leemos si se debe aplicar whitening en PCA
        self.pca_whiten = form.get("pca_whiten") == "true"
        # Leemos el solver de PCA a usar, con "auto" como valor por defecto
        self.pca_svd_solver = form.get("pca_svd_solver") or "auto"
        # Leemos el método de detección de outliers, con isolation_forest por defecto
        self.outlier_method = form.get("outlier_method") or "isolation_forest"
        # Leemos si se deben marcar los outliers detectados en el dataset resultante
        self.outlier_mark_outliers = form.get("outlier_mark_outliers", "true") == "true"
        # Leemos el id del dataset guardado seleccionado (para cargar o reemplazar un caso)
        self.selected_dataset_id = _as_int(form.get("selected_dataset_id"))

    # Extraemos del form los parámetros específicos del método de outliers elegido
    def outlier_params(self) -> dict:
        # Obtenemos la lista de parámetros permitidos para este método
        allowed = OUTLIER_PARAM_ALLOWLIST.get(self.outlier_method, [])
        params = {}
        for key in allowed:
            # Leemos el valor crudo con el prefijo "outlier_" (ej. outlier_contamination)
            raw = self.form.get(f"outlier_{key}")
            if raw in (None, ""):
                # Saltamos los parámetros que no vinieron en el form
                continue
            if key in ("n_estimators", "min_samples", "n_neighbors"):
                # Convertimos a entero los parámetros que representan conteos
                params[key] = _as_int(raw)
            else:
                # Convertimos a float el resto de parámetros numéricos
                params[key] = _as_float(raw)
        # Filtramos los parámetros que terminaron en None por una conversión fallida
        return {k: v for k, v in params.items() if v is not None}

    # Armamos el request tipado que espera el servicio de detección de outliers
    def to_request(self, *, include_columns: Optional[list] = None, max_records: Optional[int] = None) -> OutlierDetectionRequest:
        # Construir el request Pydantic puede lanzar ValidationError (ej. variables vacío,
        # ya que OutlierDetectionRequest exige min_items=1) si el wizard se invoca sin haber
        # pasado por el paso de selección de variables (form obsoleto, request manual, etc.).
        # La convertimos en la excepción de dominio que todas las rutas del wizard ya saben
        # mostrar como error amigable, en vez de dejarla escapar como un 500 crudo.
        try:
            return OutlierDetectionRequest(
                well_id=self.well_id,
                dataset_name=self.dataset_name or None,
                description=self.description or None,
                variables=self.variables,
                scaling=ScalingConfig(method=self.scaling_method),
                pca=PCAConfig(
                    enabled=self.pca_enabled,
                    n_components=self.pca_n_components,
                    whiten=self.pca_whiten,
                    svd_solver=self.pca_svd_solver,
                ),
                outlier=OutlierConfig(
                    method=self.outlier_method,
                    params=self.outlier_params(),
                    mark_outliers=self.outlier_mark_outliers,
                ),
                include_columns=include_columns,
                max_records=max_records,
            )
        except ValidationError:
            raise OutlierDetectionError("Selecciona al menos una variable antes de continuar.")

    # Armamos el diccionario base de contexto que reutilizan todos los pasos del wizard
    def base_ctx(self) -> dict:
        d = {
            "well_id": self.well_id,
            "dataset_name": self.dataset_name,
            "description": self.description,
            "variables": self.variables,
            "scaling_method": self.scaling_method,
            "pca_enabled": self.pca_enabled,
            "pca_n_components": self.pca_n_components,
            "pca_whiten": self.pca_whiten,
            "pca_svd_solver": self.pca_svd_solver,
            "outlier_method": self.outlier_method,
            "outlier_params": self.outlier_params(),
            "outlier_mark_outliers": self.outlier_mark_outliers,
            "selected_dataset_id": self.selected_dataset_id,
            "steps": STEP_ORDER,
            "step_titles": STEP_TITLES,
        }
        d["ctx"] = d  # self-reference so templates can pass `ctx` to the wizard_hidden() macro
        # Devolvemos el contexto ya armado, listo para que cada paso le agregue lo suyo
        return d


# Calculamos el cuantil p (0-100) de una lista ya ordenada, interpolando entre los dos valores más cercanos
def _quantile(sorted_values: list, p: float) -> float:
    if not sorted_values:
        # Devolvemos 0 si no hay datos
        return 0.0
    # Calculamos la posición fraccionaria dentro de la lista ordenada
    idx = (p / 100) * (len(sorted_values) - 1)
    lower = math.floor(idx)
    upper = math.ceil(idx)
    weight = idx - lower
    if lower == upper:
        # Devolvemos el valor exacto cuando el índice cae en una posición entera
        return sorted_values[lower]
    # Interpolamos linealmente entre el valor inferior y el superior
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


# Calculamos las estadísticas de caja (boxplot) de una lista de valores
def _box_stats(values: list) -> Optional[dict]:
    if not values:
        # Devolvemos None si no hay valores para calcular
        return None
    s = sorted(values)
    # Calculamos cuartiles y mediana
    q1, median, q3 = _quantile(s, 25), _quantile(s, 50), _quantile(s, 75)
    iqr = q3 - q1
    # Calculamos las cercas (fences) de Tukey a 1.5 IQR
    lower_fence, upper_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    # Nos quedamos con los valores dentro de las cercas para calcular los bigotes
    inside = [v for v in s if lower_fence <= v <= upper_fence]
    lower_whisker = min(inside) if inside else s[0]
    upper_whisker = max(inside) if inside else s[-1]
    # Contamos cuántos valores caen fuera de las cercas (candidatos a outlier)
    outliers = [v for v in s if v < lower_fence or v > upper_fence]
    return {
        "min": s[0], "max": s[-1], "q1": q1, "median": median, "q3": q3,
        "lower_whisker": lower_whisker, "upper_whisker": upper_whisker,
        "outlier_count": len(outliers),
    }


# Construimos un histograma simple (bins uniformes) de una lista de valores
def _histogram(values: list) -> list:
    if not values:
        # Devolvemos lista vacía si no hay valores
        return []
    n = len(values)
    # Elegimos la cantidad de bins entre 6 y 12, escalando con el tamaño de la muestra
    bins = max(6, min(12, n // 2)) or 1
    vmin, vmax = min(values), max(values)
    # Calculamos el ancho de cada bin (1.0 si todos los valores son iguales, para evitar división por cero)
    width = (vmax - vmin) / bins if vmax > vmin else 1.0
    counts = [0] * bins
    for v in values:
        idx = int((v - vmin) / width) if width else 0
        # Metemos en el último bin cualquier valor que se pase del rango por redondeo
        counts[bins - 1 if idx >= bins else idx] += 1
    out = []
    for i in range(bins):
        start = vmin + i * width
        end = start + width
        center = (start + end) / 2
        # Armamos cada bin con su rango, centro, conteo y porcentaje de densidad
        out.append({"bin_start": start, "bin_end": end, "bin_center": center, "count": counts[i], "density_pct": counts[i] / n * 100})
    return out


# Precalculamos el histograma de cada columna candidata, para previews instantáneos en el cliente
def _variable_histograms(records: list, columns: list) -> dict:
    """Precompute every candidate's histogram once, from the already-fetched
    sample, so the client can render hover previews instantly with no
    per-hover round trip."""
    out = {}
    for col in columns:
        # Filtramos valores no numéricos y ceros (0 significa "sin lectura" para estos sensores)
        values = [v for v in (_num(r.get(col)) for r in records) if v is not None and v != 0]
        out[col] = _histogram(values)
    return out


# Construimos un DataFrame numérico de las columnas candidatas, enmascarando los ceros como NaN
def _numeric_df(records: list, columns: list):
    """DataFrame of candidate columns, coerced to numeric with 0 masked to NaN
    (0 means "no reading" for these sensors — same convention as completeness/histograms)."""
    # Convertimos cada columna a numérico, forzando a NaN lo que no se pueda parsear
    df = pd.DataFrame(records)[columns].apply(pd.to_numeric, errors="coerce")
    # Enmascaramos los ceros como NaN, siguiendo la misma convención del resto del módulo
    return df.mask(df == 0)


# Calculamos media, desviación estándar y coeficiente de variación por columna
def _variable_stats(df, columns: list) -> dict:
    """Mean / std / coefficient of variation per column, for display and for
    the near-constant check in _recommend_variables."""
    out = {}
    for c in columns:
        # Descartamos los NaN antes de calcular las estadísticas
        s = df[c].dropna()
        if len(s) < 2:
            # No calculamos estadísticas si hay menos de 2 valores válidos
            out[c] = {"mean": None, "std": None, "cv": None}
            continue
        mean, std = float(s.mean()), float(s.std())
        # Calculamos el coeficiente de variación (evitando dividir por una media 0)
        out[c] = {"mean": mean, "std": std, "cv": abs(std / mean) if mean else None}
    return out


# Sugerimos una selección inicial de variables aplicando los criterios de completitud, varianza y correlación
def _recommend_variables(df, columns: list, completeness_by_col: dict, stats: dict) -> set:
    """Suggest a starting variable selection:
    1) completeness >= RECOMMEND_MIN_COMPLETENESS,
    2) not near-constant (coefficient of variation > RECOMMEND_MIN_CV), and
    3) when two variables are highly correlated (|r| >= RECOMMEND_CORR_THRESHOLD),
       keep only the more complete one.
    """
    # Filtramos las columnas que cumplen el umbral mínimo de completitud
    eligible = [c for c in columns if completeness_by_col.get(c, 0) >= RECOMMEND_MIN_COMPLETENESS]
    # Filtramos las que además no son casi constantes (CV por encima del umbral)
    eligible = [c for c in eligible if (stats.get(c, {}).get("cv") or 0) > RECOMMEND_MIN_CV]
    if len(eligible) <= 1:
        # Devolvemos directamente si hay 0 o 1 elegibles (no hay nada que des-duplicar)
        return set(eligible)

    # Calculamos la matriz de correlación entre las columnas elegibles
    corr = df[eligible].corr()
    dropped = set()
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            if a in dropped or b in dropped:
                # Saltamos pares donde alguna de las dos ya fue descartada
                continue
            r = corr.loc[a, b]
            if pd.notna(r) and abs(r) >= RECOMMEND_CORR_THRESHOLD:
                # Cuando dos variables están muy correlacionadas, descartamos la menos completa
                loser = a if completeness_by_col.get(a, 0) < completeness_by_col.get(b, 0) else b
                dropped.add(loser)
    # Devolvemos las elegibles que no fueron descartadas por redundancia
    return {c for c in eligible if c not in dropped}


# Traemos una muestra de registros de sensores para el pozo indicado
def _fetch_well_records(db: Session, well_id: int, sample_size: int = SAMPLE_SIZE) -> list:
    # Obtenemos el nombre físico de la tabla well_data para el dominio "depth"
    table = db_manager.get_depth_table("well_data")
    # Construimos el repositorio de datos apuntando a esa tabla
    repo = DataRepository(db, table)
    # Devolvemos la muestra de registros solicitada
    return repo.query_sample(well_id, sample_size=sample_size)


# Extraemos los nombres de columnas disponibles a partir del primer registro
def _available_columns(records: list) -> list:
    if not records:
        # Devolvemos lista vacía si no hay registros
        return []
    return list(records[0].keys())


# Filtramos los parámetros rastreados que efectivamente existen como columnas en estos datos
def _numeric_candidates(records: list) -> list:
    """Tracked parameters that exist as columns in this well's data."""
    if not records:
        # Devolvemos lista vacía si no hay registros de donde sacar columnas
        return []
    cols = set(records[0].keys())
    # Devolvemos solo los parámetros rastreados que están presentes en esta tabla
    return [p for p in get_tracked_parameters() if p in cols]


# Calculamos el porcentaje de completitud (valores presentes y distintos de 0) de cada columna
def _completeness(records: list, columns: list) -> list:
    # Evitamos dividir por cero cuando no hay registros
    total = len(records) or 1
    out = []
    for col in columns:
        present = 0
        for r in records:
            v = _num(r.get(col))
            if v is not None and v != 0:
                present += 1
        # Guardamos la columna, su etiqueta legible y su porcentaje de completitud
        out.append({"column": col, "label": _get_label(col), "completeness": present / total * 100})
    # Ordenamos de mayor a menor completitud para facilitar la revisión visual
    out.sort(key=lambda c: c["completeness"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Step renderers
# ---------------------------------------------------------------------------

# Renderizamos el paso 1: selección de pozo y datos del dataset
def _render_step_well(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    # Traemos todos los pozos ordenados alfabéticamente para el selector
    wells = db.query(Well).order_by(Well.well_name).all()
    ctx = state.base_ctx()
    # Pre-render the saved-case list when a well is already selected (Back from
    # a later step, or a validation error) — otherwise the "Load an existing
    # case" card sits empty until the well <select>'s change event fires, and
    # "Load case" is clickable in that state with nothing to load.
    # Precargamos los datasets guardados de ese pozo, si ya hay uno seleccionado
    datasets = _service(db).list_datasets(state.well_id) if state.well_id else []
    ctx.update({"request": request, "current_user": current_user, "wells": wells, "current_step": "well",
               "errors": errors or [], "datasets": datasets})
    return templates.TemplateResponse(request, "partials/outlier_step_well.html", ctx)


# Renderizamos el paso 2: selección de variables candidatas
def _render_step_variables(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    # Traemos una muestra de registros del pozo seleccionado
    records = _fetch_well_records(db, state.well_id)
    # Determinamos qué parámetros rastreados existen realmente en estos datos
    candidates = _numeric_candidates(records)
    # Calculamos la completitud de cada candidato
    completeness = _completeness(records, candidates)
    completeness_by_col = {c["column"]: c["completeness"] for c in completeness}

    if records:
        # Construimos el DataFrame numérico y calculamos estadísticas y recomendaciones
        df = _numeric_df(records, candidates)
        stats = _variable_stats(df, candidates)
        recommended = _recommend_variables(df, candidates, completeness_by_col, stats)
    else:
        # Si no hay registros, no hay estadísticas ni recomendaciones que calcular
        stats = {}
        recommended = set()

    ctx = state.base_ctx()
    # Armamos las opciones de variable que consume el template (con su completitud y estadísticas)
    variable_options = [
        {
            "value": c["column"],
            "label": c["label"],
            "completeness": c["completeness"],
            "recommended": c["column"] in recommended,
            "mean": stats.get(c["column"], {}).get("mean"),
            "std": stats.get(c["column"], {}).get("std"),
            "cv": stats.get(c["column"], {}).get("cv"),
        }
        for c in completeness
    ]
    ctx.update({
        "request": request, "current_user": current_user, "current_step": "variables", "errors": errors or [],
        "candidates": variable_options,
        # Ofrecemos también una vista ordenada alfabéticamente por etiqueta
        "candidates_alpha": sorted(variable_options, key=lambda c: c["label"]),
        "sample_size": len(records),
        "histograms": _variable_histograms(records, candidates),
        "recommend_criteria": {
            "min_completeness": RECOMMEND_MIN_COMPLETENESS,
            "min_cv": RECOMMEND_MIN_CV,
            "corr_threshold": RECOMMEND_CORR_THRESHOLD,
        },
    })
    if not state.variables:
        # Si el usuario todavía no eligió variables, precargamos las recomendadas
        ctx["variables"] = sorted(recommended)
    return templates.TemplateResponse(request, "partials/outlier_step_variables.html", ctx)


# Renderizamos el paso 3: configuración de escalado
def _render_step_scaling(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    ctx = state.base_ctx()
    ctx.update({"request": request, "current_user": current_user, "current_step": "scaling", "errors": errors or []})
    return templates.TemplateResponse(request, "partials/outlier_step_scaling.html", ctx)


# Renderizamos el paso 4: configuración de PCA
def _render_step_pca(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    ctx = state.base_ctx()
    ctx.update({"request": request, "current_user": current_user, "current_step": "pca", "errors": errors or []})
    return templates.TemplateResponse(request, "partials/outlier_step_pca.html", ctx)


# Renderizamos el paso 5: configuración del método de detección de outliers
def _render_step_outlier(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    ctx = state.base_ctx()
    ctx.update({"request": request, "current_user": current_user, "current_step": "outlier", "errors": errors or []})
    return templates.TemplateResponse(request, "partials/outlier_step_outlier.html", ctx)


# Renderizamos el paso 6: revisión final antes de ejecutar el pipeline
def _render_step_review(request: Request, db: Session, current_user: User, state: WizardState, errors=None):
    # Buscamos el pozo para mostrar su nombre en el resumen
    well = db.query(Well).filter(Well.id == state.well_id).first() if state.well_id else None
    ctx = state.base_ctx()
    ctx.update({
        "request": request, "current_user": current_user, "current_step": "review", "errors": errors or [],
        # Usamos el nombre del pozo si lo encontramos, o el id como respaldo
        "well_name": well.well_name if well else f"Well {state.well_id}",
        # Traducimos cada variable seleccionada a su etiqueta legible
        "variable_labels": [_get_label(v) for v in state.variables],
    })
    return templates.TemplateResponse(request, "partials/outlier_step_review.html", ctx)


# ---------------------------------------------------------------------------
# Entry + step transitions
# ---------------------------------------------------------------------------

# Definimos la ruta de entrada al wizard (mantenida solo por compatibilidad)
@router.get("/outliers")
async def outliers_page(current_user: User = Depends(get_current_user_web)):
    """Relocated into the Analytics workspace (Data Cleaning). Kept as a redirect
    so old links/bookmarks still land on the wizard; the step endpoints below are
    unchanged and are driven from /analytics/cleaning."""
    # Importamos RedirectResponse aquí mismo porque solo se usa en esta ruta
    from fastapi.responses import RedirectResponse
    # Redirigimos a la nueva ubicación del wizard dentro de Analytics
    return RedirectResponse(url="/analytics/cleaning", status_code=307)


# Manejamos el envío del paso 1 (pozo) y renderizamos ese mismo paso con el estado actualizado
@router.post("/outliers/steps/well", response_class=HTMLResponse)
async def step_well(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Reconstruimos el estado del wizard a partir del form enviado
    state = WizardState(await _form_dict(request))
    return _render_step_well(request, db, current_user, state)


# Manejamos el avance del paso "well" hacia el paso "variables", validando antes de avanzar
@router.post("/outliers/steps/variables", response_class=HTMLResponse)
async def step_variables(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    errors = []
    if not state.well_id:
        # Exigimos que haya un pozo seleccionado
        errors.append("Select a well.")
    if not state.dataset_name:
        # Exigimos que el dataset tenga un nombre
        errors.append("Enter a dataset name.")
    if errors:
        # Si hay errores, nos quedamos en el paso "well" mostrando los mensajes
        return _render_step_well(request, db, current_user, state, errors)
    return _render_step_variables(request, db, current_user, state)


# Manejamos el avance del paso "variables" hacia el paso "outlier", validando que haya variables elegidas
@router.post("/outliers/steps/outlier", response_class=HTMLResponse)
async def step_outlier(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    if not state.variables:
        # Si no seleccionó ninguna variable, lo devolvemos al paso "variables" con el error
        return _render_step_variables(request, db, current_user, state, ["Select at least one variable."])
    return _render_step_outlier(request, db, current_user, state)


# Manejamos el avance del paso "outlier" hacia el paso "scaling"
@router.post("/outliers/steps/scaling", response_class=HTMLResponse)
async def step_scaling(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    return _render_step_scaling(request, db, current_user, state)


# Manejamos el avance del paso "scaling" hacia el paso "pca"
@router.post("/outliers/steps/pca", response_class=HTMLResponse)
async def step_pca(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    return _render_step_pca(request, db, current_user, state)


# Manejamos el avance del paso "pca" hacia el paso final "review", validando el número de componentes
@router.post("/outliers/steps/review", response_class=HTMLResponse)
async def step_review(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    if state.pca_n_components is not None and state.pca_n_components <= 0:
        # Rechazamos un número de componentes de PCA menor o igual a 0
        return _render_step_pca(request, db, current_user, state, ["Number of components must be greater than 0."])
    return _render_step_review(request, db, current_user, state)


# Devolvemos el fragmento con la lista de casos guardados de un pozo (usado al cambiar de pozo)
@router.get("/outliers/case-options", response_class=HTMLResponse)
async def case_options(request: Request, well_id: int, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    service = _service(db)
    # Consultamos los datasets guardados para este pozo
    datasets = service.list_datasets(well_id)
    return templates.TemplateResponse(
        request, "partials/outlier_case_select.html", {"request": request, "datasets": datasets}
    )


# Cargamos un caso guardado previamente y reconstruimos el estado del wizard hasta el paso de revisión
@router.post("/outliers/load-case", response_class=HTMLResponse)
async def load_case(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await _form_dict(request)
    # Leemos el id del dataset guardado que el usuario quiere cargar
    case_id = _as_int(form.get("case_dataset_id"))
    if not case_id:
        # Si no seleccionó ningún caso, mostramos el error en el paso "well"
        state = WizardState(form)
        return _render_step_well(request, db, current_user, state, ["Select a saved case to load."])

    service = _service(db)
    # Buscamos el detalle del dataset guardado
    detail = service.get_dataset(case_id)
    if detail is None:
        # Si el caso ya no existe, avisamos en el paso "well"
        state = WizardState(form)
        return _render_step_well(request, db, current_user, state, ["That case could not be found."])

    # Leemos la configuración del pipeline guardada junto con el dataset
    cfg = detail.pipeline_config or {}
    scaling = cfg.get("scaling", {})
    pca = cfg.get("pca", {})
    outlier = cfg.get("outlier", {})
    # Reconstruimos el form como si el usuario hubiera llenado cada paso a mano
    rebuilt = {
        "well_id": str(detail.well_id),
        "dataset_name": detail.name,
        "description": detail.description or "",
        "variables": cfg.get("variables", []),
        "scaling_method": scaling.get("method", "standard"),
        "pca_enabled": "true" if pca.get("enabled") else "false",
        "pca_n_components": str(pca.get("n_components")) if pca.get("n_components") else "",
        "pca_whiten": "true" if pca.get("whiten") else "false",
        "pca_svd_solver": pca.get("svd_solver", "auto"),
        "outlier_method": outlier.get("method", "isolation_forest"),
        "outlier_mark_outliers": "true" if outlier.get("mark_outliers", True) else "false",
        "selected_dataset_id": str(detail.id),
    }
    for key, value in (outlier.get("params") or {}).items():
        # Reinyectamos cada parámetro del método de outliers con su prefijo esperado
        rebuilt[f"outlier_{key}"] = str(value)

    state = WizardState(rebuilt)
    return _render_step_review(request, db, current_user, state)


# ---------------------------------------------------------------------------
# Step-local actions
# ---------------------------------------------------------------------------

# Generamos el gráfico (boxplot + histograma) de una variable puntual, a pedido del usuario
@router.post("/outliers/visualize", response_class=HTMLResponse)
async def visualize_variable(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await _form_dict(request)
    state = WizardState(form)
    # Leemos qué variable se quiere visualizar
    variable = form.get("visualize_variable")
    # Traemos la muestra de registros del pozo
    records = _fetch_well_records(db, state.well_id)
    # Extraemos los valores numéricos válidos de esa variable, descartando ceros ("sin lectura")
    values = [v for v in (_num(r.get(variable)) for r in records) if v is not None and v != 0]

    return templates.TemplateResponse(
        request,
        "partials/outlier_variable_chart.html",
        {
            "request": request,
            "variable": variable,
            "label": _get_label(variable) if variable else "",
            "box": _box_stats(values),
            "histogram": _histogram(values),
            "sample_count": len(values),
        },
    )


# Ejecutamos una previsualización del escalado de las variables seleccionadas, sin guardar nada
@router.post("/outliers/preview/scaling", response_class=HTMLResponse)
async def preview_scaling(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    service = _service(db)
    try:
        # Pedimos al servicio el preview de escalado con la configuración actual
        result = service.preview_scaling(state.to_request())
        error = None
    except OutlierDetectionError as exc:
        # Capturamos cualquier error de dominio y lo mostramos en el template
        result, error = None, str(exc)
    return templates.TemplateResponse(
        request, "partials/outlier_preview_scaling.html", {"request": request, "result": result, "error": error}
    )


# Ejecutamos una previsualización de PCA (varianza explicada por componente) sin guardar nada
@router.post("/outliers/preview/pca", response_class=HTMLResponse)
async def preview_pca(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    service = _service(db)
    try:
        # Pedimos al servicio el preview de PCA con la configuración actual
        result = service.preview_pca(state.to_request())
        error = None
    except OutlierDetectionError as exc:
        result, error = None, str(exc)
    cumulative = []
    if result:
        # Acumulamos la varianza explicada componente a componente, en porcentaje
        total = 0.0
        for ratio in result.explained_variance_ratio:
            total += ratio
            cumulative.append(total * 100)
    return templates.TemplateResponse(
        request,
        "partials/outlier_preview_pca.html",
        {"request": request, "result": result, "error": error, "cumulative": cumulative},
    )


# Ejecutamos una previsualización del scatter de dos componentes principales elegidos por el usuario
@router.post("/outliers/preview/pca-scatter", response_class=HTMLResponse)
async def preview_pca_scatter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await _form_dict(request)
    state = WizardState(form)
    # Leemos qué componentes van en el eje X e Y del scatter (por defecto el 1º y el 2º)
    x_idx = _as_int(form.get("pca_scatter_x")) or 0
    y_idx = _as_int(form.get("pca_scatter_y")) or 1
    service = _service(db)
    try:
        result = service.preview_pca(state.to_request())
        error = None
    except OutlierDetectionError as exc:
        result, error = None, str(exc)

    points = []
    labels = []
    if result and len(result.component_labels) > max(x_idx, y_idx):
        # Solo armamos los puntos si el resultado tiene suficientes componentes para los ejes pedidos
        labels = result.component_labels
        for score in result.scores:
            points.append({"x": score.components[x_idx], "y": score.components[y_idx]})

    return templates.TemplateResponse(
        request,
        "partials/outlier_pca_scatter.html",
        {"request": request, "points": points, "labels": labels, "x_idx": x_idx, "y_idx": y_idx, "error": error},
    )


# Ejecutamos una previsualización completa del pipeline de detección de outliers, sin guardar nada
@router.post("/outliers/preview/outlier", response_class=HTMLResponse)
async def preview_outlier(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    service = _service(db)
    try:
        # Corremos el pipeline completo (escalado + PCA + detección) en modo preview
        result = service.preview_pipeline(state.to_request())
        error = None
    except OutlierDetectionError as exc:
        result, error = None, str(exc)
    return templates.TemplateResponse(
        request, "partials/outlier_preview_outlier.html", {"request": request, "result": result, "error": error}
    )


# Ejecutamos una previsualización del scatter de outliers vs inliers en dos componentes elegidos
@router.post("/outliers/preview/outlier-scatter", response_class=HTMLResponse)
async def preview_outlier_scatter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await _form_dict(request)
    state = WizardState(form)
    # Leemos qué componentes van en el eje X e Y del scatter (por defecto el 1º y el 2º)
    x_idx = _as_int(form.get("outlier_scatter_x")) or 0
    y_idx = _as_int(form.get("outlier_scatter_y")) or 1
    service = _service(db)
    try:
        result = service.preview_pipeline(state.to_request())
        error = None
    except OutlierDetectionError as exc:
        result, error = None, str(exc)

    inliers, outliers = [], []
    labels = []
    if result and result.component_labels and len(result.component_labels) > max(x_idx, y_idx):
        labels = result.component_labels
        for row, is_out in zip(result.components, result.is_outlier):
            point = {"x": row[x_idx], "y": row[y_idx]}
            # Repartimos cada punto en la lista de outliers o de inliers según corresponda
            (outliers if is_out else inliers).append(point)

    return templates.TemplateResponse(
        request,
        "partials/outlier_scatter.html",
        {"request": request, "inliers": inliers, "outliers": outliers, "labels": labels, "x_idx": x_idx, "y_idx": y_idx, "error": error},
    )


# Ejecutamos el pipeline definitivo y guardamos (o reemplazamos) el dataset resultante
@router.post("/outliers/run", response_class=HTMLResponse)
async def run_pipeline(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = WizardState(await _form_dict(request))
    # Traemos un solo registro solo para conocer qué columnas existen en la tabla
    records = _fetch_well_records(db, state.well_id, sample_size=1)
    available = _available_columns(records)
    # Incluimos en el dataset final todas las columnas que no fueron usadas como variables de entrada
    include_columns = [c for c in available if c not in state.variables]

    service = _service(db)
    try:
        # Ejecutamos el pipeline completo, guardando el dataset y registrando quién lo creó
        response = service.run_pipeline(
            state.to_request(include_columns=include_columns),
            created_by=current_user.id,
            replace_dataset_id=state.selected_dataset_id,
        )
        error = None
        detail = response.dataset
    except OutlierDetectionError as exc:
        # Capturamos el error de dominio para mostrarlo en el paso de revisión
        error, detail = str(exc), None

    if error:
        # Si algo falló, nos quedamos en el paso de revisión mostrando el error
        return _render_step_review(request, db, current_user, state, [error])

    # Buscamos el pozo para mostrar su nombre en la pantalla de resultado
    well = db.query(Well).filter(Well.id == state.well_id).first()
    return templates.TemplateResponse(
        request,
        "partials/outlier_run_result.html",
        {"request": request, "detail": detail, "well_name": well.well_name if well else state.well_id},
    )
