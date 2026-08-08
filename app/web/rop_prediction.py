"""ROP Prediction wizard — multi-step ML pipeline to predict ROP across wells.

Steps: Select Wells → Features (controllable/response split) → Train/Test split
(+ blind well) → Processing → Models → Pre-selection → Hyperparameter optimisation
(Optuna TPE) → Validation (metrics + prediction intervals + SHAP/PDP + data-quality/
drift gates). Heavy steps run as background jobs (polled by the UI). Trained models
are persisted (registry + joblib) and can be reused for inference / what-if.
"""
# Importamos json para serializar/deserializar los mejores hiperparámetros (best_params)
import json
# Importamos re para parsear el progreso "(n/total)" que reportan los jobs de validación
import re

# Importamos numpy para las operaciones numéricas (arrays, log1p, muestreo aleatorio, etc.)
import numpy as np
# Importamos las piezas de FastAPI para declarar el router, las dependencias y el request
from fastapi import APIRouter, Depends, Request
# Importamos HTMLResponse para devolver fragmentos HTML crudos (partials htmx)
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de SQLAlchemy inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que exige un usuario autenticado en las rutas web
from app.core.deps import get_current_user_web
# Importamos el logger de la app
from app.core.logging import get_logger
# Importamos el modelo User (usuario autenticado)
from app.models.legacy import User
# Importamos el modelo legacy de pozo (con alias WellModel para no chocar con otros usos de "Well")
from app.models.legacy import Well as WellModel
# Importamos el repositorio de pozos para listarlos/consultarlos
from app.repositories.well_repository import WellRepository
# Importamos el gestor de sesiones y las dependencias de BD (por defecto y de la BD de profundidad)
from app.db.session import db_manager, get_db, get_depth_db
# Importamos los servicios que implementan la lógica de negocio del wizard (experimentos, jobs en
# background, el motor de ML, el servicio de features/estado y el guardado de runs)
from app.services import rop_experiments, rop_jobs, rop_ml, rop_prediction as svc, rop_run_store
# Importamos la lista de submódulos de Analytics para el menú lateral
from app.web.analytics import SUBMODULES
# Importamos el motor de templates Jinja de la app
from app.web.templating import templates

# Creamos el logger de este módulo
logger = get_logger(__name__)
# Creamos el router con el prefijo común de todas las rutas del wizard de ROP Prediction
router = APIRouter(prefix="/analytics/rop-prediction")

# Definimos los pasos del wizard, en el orden en que se muestran en el breadcrumb
WIZARD_STEPS = [
    {"key": "wells", "title": "Wells & Features"},
    {"key": "split", "title": "Train / Test"},
    # UI order deliberately matches build_dataset()'s ACTUAL processing order —
    # not the reverse — since a wizard's step order otherwise implies execution
    # order to the user. Outliers are removed (train-only, on raw values) BEFORE
    # Scaling is fit, so a bad outlier can't skew the scaler's statistics;
    # Scaling happens BEFORE PCA because PCA is variance-based and would
    # otherwise just be dominated by whichever raw feature has the largest
    # numeric range. See _split_well_options/build_dataset for the actual code.
    {"key": "outliers", "title": "Outliers"},
    {"key": "scaling", "title": "Scaling"},
    {"key": "pca", "title": "PCA"},
    {"key": "models", "title": "Models"},
    {"key": "preselect", "title": "Pre-selection"},
    {"key": "hpo", "title": "Hyperparameters"},
    {"key": "validation", "title": "Validation"},
]

# Definimos a dónde postea el click de "revisitar este paso" del breadcrumb — una
# entrada por cada key de WIZARD_STEPS. Los pasos de configuración simplemente vuelven
# a renderizarse desde el estado (barato); los 3 pasos pesados redisplayan el resultado
# cacheado del job (o una tarjeta "aún no corrido") vía los helpers _revisit_*, sin
# volver a correr el job subyacente.
STEP_ROUTES = {
    "wells": "/analytics/rop-prediction/step/wells",
    "split": "/analytics/rop-prediction/step/split",
    "outliers": "/analytics/rop-prediction/step/outliers",
    "scaling": "/analytics/rop-prediction/step/scaling",
    "pca": "/analytics/rop-prediction/step/pca",
    "models": "/analytics/rop-prediction/step/models",
    "preselect": "/analytics/rop-prediction/step/preselect",
    "hpo": "/analytics/rop-prediction/step/hpo",
    "validation": "/analytics/rop-prediction/step/validation",
}

# Guardamos aquí los stores en memoria de proceso (un solo proceso). _RUN_CTX guarda el
# contexto (estado+tipo) de cada job para el polling, y _PIPELINE_STORE guarda los
# pipelines ya entrenados de los jobs de validación, hasta que se guarden como experimento.
_RUN_CTX: dict = {}
_PIPELINE_STORE: dict = {}


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
# Reconstruimos el estado completo del wizard a partir de los campos del form (htmx
# reenvía TODO el estado en cada request, ya que no hay sesión de servidor por wizard).
def _state(form) -> dict:
    # Definimos un helper para leer una lista de valores no vacíos de un campo repetido
    def _list(k):
        return [x for x in form.getlist(k) if x not in ("", None)]

    # Definimos un helper para leer un entero con valor por defecto si falta o es inválido
    def _int(k, d):
        try:
            return int(form.get(k))
        except (TypeError, ValueError):
            return d

    # Definimos un helper para leer un float con valor por defecto si falta o es inválido
    def _float(k, d):
        try:
            return float(form.get(k))
        except (TypeError, ValueError):
            return d

    # Definimos un helper para leer un float OPCIONAL (None si no viene o es inválido)
    def _float_opt(k):
        v = form.get(k)
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # Definimos un helper para leer un entero OPCIONAL (None si no viene o es inválido)
    def _int_opt(k):
        v = form.get(k)
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    # Definimos un helper para leer una lista de floats, descartando los valores inválidos
    def _floats_list(k):
        out = []
        for x in form.getlist(k):
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                pass
        return out

    # Leemos el pozo "ciego" (blind) elegido, si lo hay
    blind = form.get("blind_well_id")
    # Leemos los filtros de profundidad y fecha (opcionales)
    depth_from, depth_to = _float_opt("depth_from"), _float_opt("depth_to")
    date_from, date_to = _int_opt("date_from"), _int_opt("date_to")
    # Leemos los umbrales mínimos de completitud de variables/target (opcionales)
    var_completeness_min = _float_opt("var_completeness_min")
    target_completeness_min = _float_opt("target_completeness_min")
    # Armamos y devolvemos el diccionario completo de estado del wizard
    return {
        "well_ids": [int(x) for x in _list("well_ids") if str(x).lstrip("-").isdigit()],
        "features": _list("features"),
        "test_pct": _int("test_pct", 20),
        "depth_from": depth_from, "depth_to": depth_to,
        "date_from": date_from, "date_to": date_to,
        # LISTS, deliberately not tuples: state gets persisted to JSONB (saved
        # experiments + rop_run_store) and JSON round-trips tuples back as
        # lists — a tuple here would make _is_stale's dict comparison fail
        # against any revived/loaded state ((a,b) != [a,b]), silently marking
        # every persisted run with a depth/date filter as stale.
        "depth_range": [depth_from, depth_to] if (depth_from is not None or depth_to is not None) else None,
        "date_range": [date_from, date_to] if (date_from is not None or date_to is not None) else None,
        "var_completeness_min": var_completeness_min,
        "target_completeness_min": target_completeness_min,
        "field": (form.get("field") or "").strip(),
        "bit_sizes": _floats_list("bit_sizes"),
        "blind_well_id": int(blind) if (blind or "").isdigit() else None,
        "log_target": form.get("log_target") == "true",
        "scaling": form.get("scaling") or "standard",
        "pca_enabled": form.get("pca_enabled") == "true",
        "pca_components": form.get("pca_components") or "",
        "pca_svd_solver": form.get("pca_svd_solver") or "auto",
        "pca_whiten": form.get("pca_whiten") == "true",
        # Preview-was-calculated flags — UI-only memory (NOT part of _cfg(), so
        # they never affect staleness/caching). False on first entry, flipped to
        # true by each "Calculate preview"/"Apply" click, carried through every
        # step so revisiting a step (breadcrumb/Back) auto-restores the preview
        # the user already asked for — while a never-touched section stays
        # completely idle until they act.
        "outlier_preview_done": form.get("outlier_preview_done") == "true",
        "scaling_preview_done": form.get("scaling_preview_done") == "true",
        "pca_preview_done": form.get("pca_preview_done") == "true",
        "dist_done": form.get("dist_done") == "true",
        "corr_done": form.get("corr_done") == "true",
        "outlier_method": form.get("outlier_method") or "none",
        # Per-method parameters — same field names as the Data-Cleaning wizard.
        "outlier_threshold": _float("outlier_threshold", 3.0),
        "outlier_multiplier": _float("outlier_multiplier", 1.5),
        "outlier_contamination": _float("outlier_contamination", 0.05),
        "outlier_n_estimators": _int("outlier_n_estimators", 100),
        "outlier_eps": _float("outlier_eps", 0.5),
        "outlier_min_samples": _int("outlier_min_samples", 5),
        "outlier_n_neighbors": _int("outlier_n_neighbors", 20),
        "models": _list("models"),
        "chosen_model": form.get("chosen_model") or "",
        "hpo_trials": _int("hpo_trials", 20),
        "best_params": form.get("best_params") or "{}",
        # Pointers to the last finished job of each kind, stamped in by poll()
        # when it renders a "done" result — let a step be revisited (breadcrumb,
        # Back) by redisplaying the cached result instead of re-running or
        # showing a blank form. See _revisit_preselect/_revisit_hpo/_revisit_validation.
        "preselect_job_id": form.get("preselect_job_id") or "",
        "hpo_job_id": form.get("hpo_job_id") or "",
        "validation_job_id": form.get("validation_job_id") or "",
    }


# Extraemos del estado los parámetros específicos de cada método de detección de outliers
def _outlier_params(state: dict) -> dict:
    return {
        "threshold": state["outlier_threshold"], "multiplier": state["outlier_multiplier"],
        "contamination": state["outlier_contamination"], "n_estimators": state["outlier_n_estimators"],
        "eps": state["outlier_eps"], "min_samples": state["outlier_min_samples"],
        "n_neighbors": state["outlier_n_neighbors"],
    }


# Proyectamos el estado completo del wizard a la configuración que realmente afecta el
# entrenamiento (_cfg) — se usa como clave de cache/staleness y como input a build_dataset()
def _cfg(state: dict) -> dict:
    comp = state["pca_components"]
    return {
        "well_ids": state["well_ids"], "features": state["features"], "test_pct": state["test_pct"],
        # list(...) normalization: state may come from a live form (lists) or
        # from JSONB persistence — and historically tuples; equality-compared
        # by _is_stale, so both sides must serialize identically.
        "depth_range": list(state["depth_range"]) if state.get("depth_range") else None,
        "date_range": list(state["date_range"]) if state.get("date_range") else None,
        "bit_sizes": sorted(state.get("bit_sizes") or []),
        "blind_well_id": state["blind_well_id"], "log_target": state["log_target"],
        "scaling": state["scaling"],
        "pca_enabled": state["pca_enabled"],
        "pca_components": int(comp) if str(comp).isdigit() else None,
        "pca_svd_solver": state["pca_svd_solver"], "pca_whiten": state["pca_whiten"],
        "outlier_method": state["outlier_method"], "outlier_params": _outlier_params(state),
        "seed": 42,
    }


# Armamos el contexto común y renderizamos el shell del wizard (o la página completa)
def _render(request, current_user, step, state=None, full=False, body_partial=None, **extra):
    ctx = {
        "request": request, "current_user": current_user, "submodules": SUBMODULES,
        "active": "rop-prediction", "wizard_steps": WIZARD_STEPS, "active_step": step,
        "step_routes": STEP_ROUTES, "body_partial": body_partial, "state": state or {},
        # Human-readable model names wherever a template shows a model key
        # (shell summary strip, etc.).
        "model_labels": {k: v["label"] for k, v in rop_ml.MODELS.items()},
    }
    # Mezclamos el contexto extra propio de cada paso (rankings, resultados, errores, etc.)
    ctx.update(extra)
    # Elegimos la página completa o solo el shell parcial (fragmento htmx), según corresponda
    tpl = "ops/pages/analytics/rop_prediction.html" if full else "ops/partials/analytics/rop_pred_shell.html"
    return templates.TemplateResponse(request, tpl, ctx)


# --------------------------------------------------------------------------- #
# Revisiting a step's result (breadcrumb / Back) without re-running or losing it
# --------------------------------------------------------------------------- #
def _is_stale(job_id: str, state: dict, extra_keys: tuple = ()) -> bool:
    """True if `state`'s training-relevant config no longer matches what the job
    at `job_id` was actually submitted with — e.g. the user changed wells/features
    (or, for hpo/validation, picked a different model) since that job ran, so its
    cached result would be misleading to redisplay. Compares the `_cfg()` projection
    (the actual training input) plus any `extra_keys`, not the whole wizard state —
    unrelated fields (which step you're on, UI-only toggles) shouldn't count."""
    # Buscamos el contexto del job; si no existe, lo tratamos como obsoleto (no hay nada que comparar)
    ctx = _RUN_CTX.get(job_id)
    if ctx is None:
        return True
    old_state = ctx["state"]
    # Comparamos la proyección de entrenamiento (_cfg) del estado actual contra la del job
    if _cfg(state) != _cfg(old_state):
        return True
    # Comparamos además las claves extra (p.ej. el modelo elegido) que también invalidan el resultado
    return any(state.get(k) != old_state.get(k) for k in extra_keys)


def _revive_job(db: Session, job_id: str, step: str) -> None:
    """If `job_id` isn't in the in-process store (server restarted since it
    finished), pull it back from the DB-backed rop_run_store and re-seed both
    rop_jobs and _RUN_CTX from it — the SAME redisplay path a live job or a
    loaded saved experiment already uses (see rop_jobs.seed_done), so nothing
    downstream needs to know the difference. A no-op if the job is already
    live in-process, or if no persisted row exists for it (e.g. it was never a
    preselect/hpo/validation job, or genuinely never finished)."""
    # Si no hay job_id, o el job ya está vivo y terminado en el store en memoria, no hacemos nada
    if not job_id or rop_jobs.get(job_id)["status"] == "done":
        return
    # Intentamos recuperar el resultado persistido en la BD
    persisted = rop_run_store.load(db, job_id)
    if persisted is None:
        # No hay nada guardado para este job_id — nada que revivir
        return
    # Re-sembramos el job como "terminado" en el store en memoria y reconstruimos su contexto
    rop_jobs.seed_done(job_id, persisted["result"])
    _RUN_CTX[job_id] = {"kind": persisted["kind"], "step": step, "state": persisted["state"], "msg": ""}


def _revisit_preselect(request, current_user, state: dict, db: Session):
    """Redisplay the last finished pre-selection job's result if it's still in
    the job store and not stale; otherwise a 'not run yet' card. Never re-runs —
    that's what the explicit Run/Re-run button is for."""
    # Obtenemos el id del último job de pre-selección guardado en el estado
    job_id = state.get("preselect_job_id")
    # Intentamos revivirlo desde la BD si el proceso se reinició
    _revive_job(db, job_id, "preselect")
    job = rop_jobs.get(job_id) if job_id else {"status": "missing"}
    # Si el job no terminó, o quedó obsoleto (config o modelos cambiaron), mostramos la tarjeta vacía
    if job["status"] != "done" or _is_stale(job_id, state, extra_keys=("models",)):
        return _render(request, current_user, "preselect", state=state, ranked=None)
    # Redisplayamos el ranking y la info del dataset del último job válido
    result = job["result"]
    return _render(request, current_user, "preselect", state=state,
                   ranked=result["ranked"], ds_info=result["ds_info"])


def _revisit_hpo(request, current_user, state: dict, db: Session):
    # Reachable with NO model chosen via the forward-jumpable breadcrumb —
    # supports_hpo("") is truthy, so without this guard the page rendered a
    # blank model name and a "Run optimization" button guaranteed to fail.
    if not state.get("chosen_model"):
        # Sin modelo elegido no hay nada que optimizar — mostramos el paso como "no listo"
        return _render(request, current_user, "hpo", state=state, not_ready=True,
                       can_hpo=False, model_label="")
    # Obtenemos el id del último job de HPO y lo revivimos si hace falta
    job_id = state.get("hpo_job_id")
    _revive_job(db, job_id, "hpo")
    job = rop_jobs.get(job_id) if job_id else {"status": "missing"}
    # Verificamos si el modelo elegido soporta optimización de hiperparámetros
    can_hpo = rop_ml.supports_hpo(state.get("chosen_model", ""))
    # Resolvemos la etiqueta legible del modelo elegido
    model_label = rop_ml.MODELS.get(state.get("chosen_model"), {}).get("label", state.get("chosen_model"))
    cfg = _cfg(state)
    # Estimamos cuánto tardarían el HPO y la validación con la config actual (para mostrar al usuario)
    hpo_estimate = rop_ml.estimate_seconds(cfg, "hpo", n_trials=int(state.get("hpo_trials") or 20))
    validation_estimate = rop_ml.estimate_seconds(cfg, "validation")
    # Si el job no terminó o quedó obsoleto, mostramos el formulario de "correr optimización"
    if job["status"] != "done" or _is_stale(job_id, state, extra_keys=("chosen_model",)):
        return _render(request, current_user, "hpo", state=state, can_hpo=can_hpo, model_label=model_label,
                       hpo_estimate=hpo_estimate, validation_estimate=validation_estimate)
    # Redisplayamos el resultado cacheado del último HPO válido
    return _render(request, current_user, "hpo", state=state, hpo_result=job["result"],
                   can_hpo=can_hpo, model_label=model_label,
                   hpo_estimate=hpo_estimate, validation_estimate=validation_estimate)


def _validation_result_defaults(result: dict) -> dict:
    """A live job's result always has every key (final_validation() sets them
    all); a LOADED experiment saved before metrics were expanded to include
    perm_importance/shap/plots/drift/n_invalid_blind may be missing some —
    default them so the (unguarded, since a live result never needed it)
    `result.perm_importance` loop in rop_pred_validation.html doesn't crash."""
    # Copiamos el resultado para no mutar el original
    result = dict(result)
    # Completamos con valores por defecto cada clave que pudiera faltar en un resultado antiguo
    result.setdefault("perm_importance", [])
    result.setdefault("shap", None)
    result.setdefault("plots", {})
    result.setdefault("drift", None)
    result.setdefault("n_invalid_blind", 0)
    result.setdefault("error_bands", None)
    result.setdefault("learning_curve", None)
    result.setdefault("validation_curve", None)
    return result


def _revisit_validation(request, current_user, state: dict, db: Session, full: bool = False):
    # Obtenemos el id del último job de validación y lo revivimos si hace falta
    job_id = state.get("validation_job_id")
    _revive_job(db, job_id, "validation")
    job = rop_jobs.get(job_id) if job_id else {"status": "missing"}
    model_label = rop_ml.MODELS.get(state.get("chosen_model"), {}).get("label", state.get("chosen_model"))
    # Si el job no terminó o quedó obsoleto, mostramos la validación sin resultado (tarjeta "no corrida")
    if job["status"] != "done" or _is_stale(job_id, state, extra_keys=("chosen_model", "best_params")):
        return _render(request, current_user, "validation", state=state, full=full, result=None, model_label=model_label)
    result = job["result"]
    # Save/logview leen el pipeline entrenado desde _PIPELINE_STORE, no del resultado
    # renderizado — un job revivido desde la BD (ver _revive_job) también necesita
    # poblarlo aquí, igual que la rama "kind == validation" de poll() para un job que
    # acaba de terminar en vivo.
    if job_id not in _PIPELINE_STORE and "pipeline" in result:
        _PIPELINE_STORE[job_id] = result["pipeline"]
    # Redisplayamos el resultado completo (con defaults aplicados) del último job válido
    return _render(request, current_user, "validation", state=state, full=full,
                   result=_validation_result_defaults(result["result"]),
                   ds_info=result["ds_info"], result_token=job_id, model_label=model_label)


# --------------------------------------------------------------------------- #
# Step 1 — wells
# --------------------------------------------------------------------------- #
# Armamos las filas de la tabla de pozos con sus estadísticas (rows, completitud, etc.),
# aplicando los filtros de rango/completitud/campo/diámetro de broca, y ordenando por
# completitud de variables descendente (los pozos más útiles primero)
def _well_rows(db: Session, depth_range=None, date_range=None,
               var_completeness_min=None, target_completeness_min=None, field=None,
               bit_sizes=None) -> list[dict]:
    # Traemos todos los pozos y sus resúmenes (n_rows, completitud) ya filtrados por rango
    wells = WellRepository(db).get_all(skip=0, limit=2000)
    summaries = svc.well_summaries(depth_range=depth_range, date_range=date_range, bit_sizes=bit_sizes)
    rows = []
    for w in wells:
        s = summaries.get(w.id)
        # Descartamos pozos sin resumen o sin filas dentro del rango elegido
        if not s or not s["n_rows"]:
            continue
        # Descartamos pozos por debajo del umbral mínimo de completitud de variables
        if var_completeness_min is not None and s["feature_completeness"] < var_completeness_min:
            continue
        # Descartamos pozos por debajo del umbral mínimo de completitud del target
        if target_completeness_min is not None and s["target_completeness"] < target_completeness_min:
            continue
        # Descartamos pozos que no pertenecen al campo filtrado
        if field and (w.field_name or "") != field:
            continue
        rows.append({"id": w.id, "name": w.well_name, "field": w.field_name, **s})
    # Ordenamos mostrando primero los pozos con mayor completitud de variables
    rows.sort(key=lambda r: r["feature_completeness"], reverse=True)
    return rows


# Devolvemos la lista de campos (field_name) distintos disponibles, para el filtro de campo
def _field_options(db: Session) -> list[str]:
    return [r[0] for r in db.query(WellModel.field_name).filter(WellModel.field_name.isnot(None))
                            .distinct().order_by(WellModel.field_name).all()]


# Armamos el contexto de la sección de features: la tabla de variables, las ya seleccionadas
# y los pozos seleccionados (para mostrarlos por nombre en la UI)
def _features_ctx(db: Session, state: dict) -> dict:
    names = {w.id: w.well_name for w in WellRepository(db).get_all(skip=0, limit=2000)}
    return {
        "feature_table": _feature_table(db, state["well_ids"], state["log_target"],
                                        depth_range=state.get("depth_range"), date_range=state.get("date_range"),
                                        bit_sizes=state.get("bit_sizes")),
        "selected_features": set(state["features"]),
        "sel_wells": sorted(
            [{"id": wid, "name": names.get(wid, f"Well {wid}")} for wid in state["well_ids"]],
            key=lambda w: w["name"].lower()),
    }


# Renderizamos la página completa del wizard, arrancando en el paso "wells" sin estado previo
@router.get("", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    return _render(request, current_user, "wells", state={}, full=True,
                   wells=_well_rows(db), n_features=len(svc.feature_candidates()),
                   selected_ids=set(), show_features=False, field_options=_field_options(db),
                   bit_size_options=svc.bit_size_options())


# Procesamos el paso "wells": reconstruimos el estado, recalculamos la tabla de pozos con los
# filtros vigentes y, si ya hay pozos elegidos, agregamos también la sección de features
@router.post("/step/wells", response_class=HTMLResponse)
async def step_wells(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    extra = dict(wells=_well_rows(db, depth_range=state.get("depth_range"), date_range=state.get("date_range"),
                                  var_completeness_min=state.get("var_completeness_min"),
                                  target_completeness_min=state.get("target_completeness_min"),
                                  field=state.get("field"), bit_sizes=state.get("bit_sizes")),
                 n_features=len(svc.feature_candidates()),
                 selected_ids=set(state["well_ids"]), show_features=False, field_options=_field_options(db),
                 bit_size_options=svc.bit_size_options())
    if state["well_ids"]:
        # Ya hay pozos elegidos: mostramos también la sección de selección de features
        extra["show_features"] = True
        extra.update(_features_ctx(db, state))
    return _render(request, current_user, "wells", state=state, **extra)


@router.post("/wells/refresh", response_class=HTMLResponse)
async def wells_refresh(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Re-render of the well stats table body, triggered by the "Apply filters"
    button — each well's Rows/completeness/start date/final depth reflect only the
    rows inside the chosen depth/date/bit-diameter window, and wells below the
    completeness thresholds (or with none in range) drop out."""
    # Reconstruimos el estado y recalculamos las filas de pozos con los filtros vigentes
    state = _state(await request.form())
    rows = _well_rows(db, depth_range=state.get("depth_range"), date_range=state.get("date_range"),
                      var_completeness_min=state.get("var_completeness_min"),
                      target_completeness_min=state.get("target_completeness_min"),
                      field=state.get("field"), bit_sizes=state.get("bit_sizes"))
    # Devolvemos solo el cuerpo de la tabla (fragmento htmx)
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_wells_tbody.html",
        {"request": request, "wells": rows, "selected_ids": set(state["well_ids"])})


# --------------------------------------------------------------------------- #
# Step 2 — features
# --------------------------------------------------------------------------- #
# Calculamos, para cada variable candidata, sus estadísticas de completitud, correlación con
# el target, y plausibilidad física — la tabla que el usuario usa para decidir qué features usar
def _feature_table(db: Session, well_ids: list[int], log_target: bool = False,
                   depth_range=None, date_range=None, bit_sizes=None) -> dict:
    import pandas as pd

    target = svc.TARGET
    candidates = svc.feature_candidates()
    # Traemos y concatenamos los datos (raw + engineered) de cada pozo seleccionado
    frames = []
    for wid in well_ids:
        dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=depth_range, date_range=date_range, bit_sizes=bit_sizes)
        if dfw is None:
            continue
        keep = [c for c in candidates if c in dfw.columns]
        cols = keep + ([target] if target in dfw.columns and target not in keep else [])
        frames.append(dfw[cols].apply(pd.to_numeric, errors="coerce"))
    if not frames:
        # Sin datos de ningún pozo, devolvemos una tabla vacía
        return {"rows": [], "n_records": 0, "n_wells": 0}
    df = pd.concat(frames, ignore_index=True)
    n = len(df)
    has_target = target in df.columns
    if has_target and log_target:
        # Aplicamos log1p al target si el usuario activó "predecir log(ROP)"
        df[target] = np.log1p(df[target])

    from app.services.rop_features import ENG_KEYS
    role_order = {"controllable": 0, "context": 1, "computed": 2, "response": 3}
    rows = []
    for col in candidates:
        role = svc.feature_role(col)
        if col in df.columns:
            s = df[col]
            if col in ENG_KEYS:
                # Engineered values are derived, so 0 is a legitimate reading (e.g.
                # sliding_frac = 0 means "all rotating") — count only NaN as missing.
                comp = float(s.notna().sum()) / n * 100 if n else 0.0
                clean = s.dropna()
            else:
                # Para sensores crudos, tratamos también el 0 como "sin lectura"
                comp = float(((s.notna()) & (s != 0)).sum()) / n * 100 if n else 0.0
                clean = s.replace(0, np.nan).dropna()
            # Calculamos las estadísticas descriptivas (media, desvío, mín, máx) sobre los valores limpios
            st = {"mean": float(clean.mean()) if len(clean) else None,
                  "std": float(clean.std()) if len(clean) else None,
                  "min": float(clean.min()) if len(clean) else None,
                  "max": float(clean.max()) if len(clean) else None}
            r = None
            if has_target:
                # Calculamos la correlación de Pearson de la variable con el target (ROP)
                pair = df[[col, target]].dropna()
                pair = pair[pair[target] > 0]  # log1p(0) == 0 too, so this still excludes ROP<=0 either way
                if col not in ENG_KEYS:
                    pair = pair[pair[col] != 0]
                if len(pair) >= 10:
                    r = float(pair[col].corr(pair[target]))
            # Coherence: share of non-null readings inside the physically plausible
            # range (same PLAUSIBLE_RANGES used to gate build_dataset) — None for
            # columns with no defined range (most engineered/computed features).
            plaus = None
            if col in svc.PLAUSIBLE_RANGES and len(clean):
                lo, hi = svc.PLAUSIBLE_RANGES[col]
                plaus = float(((clean >= lo) & (clean <= hi)).sum()) / len(clean) * 100
        else:
            # La columna no está presente en ningún pozo — la mostramos vacía
            comp, st, r, plaus = 0.0, {"mean": None, "std": None, "min": None, "max": None}, None, None
        rows.append({
            "column": col, "label": svc.feature_label(col), "role": role,
            "role_label": svc.ROLE_LABELS[role], "completeness": comp, "r": r, "plausible": plaus,
            "recommended": svc.is_recommended(col), **st,
        })
    # Ordenamos por rol (controlables primero) y luego alfabéticamente por etiqueta
    rows.sort(key=lambda r: (role_order[r["role"]], r["label"].lower()))
    return {"rows": rows, "n_records": n, "n_wells": len(well_ids)}


@router.post("/step/features", response_class=HTMLResponse)
async def step_features(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """The features SECTION fragment — swapped into #rop-feat-section by the wells
    Apply button (the wells+features step is a single combined page)."""
    state = _state(await request.form())
    if not state["well_ids"]:
        # Sin pozos elegidos aún, mostramos un mensaje en vez de la tabla de features
        return HTMLResponse('<div class="card p-4"><p class="text-sm" style="color:var(--color-text-muted);">Select at least one well above, then click Apply.</p></div>')
    ctx = {"request": request, "state": state}
    ctx.update(_features_ctx(db, state))
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_features.html", ctx)


@router.post("/feature/distribution", response_class=HTMLResponse)
async def feature_distribution(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Histogram / density / box-and-whiskers for one variable of one well —
    renders the SAME partial as the Data-Cleaning wizard's Visualize view."""
    import pandas as pd
    from app.services.rop_features import ENG_KEYS
    from app.web.outliers import _box_stats, _histogram
    form = await request.form()
    state = _state(form)
    # Leemos la variable y el pozo elegidos para graficar la distribución
    variable = form.get("visualize_variable") or ""
    wid = int(form.get("dist_well_id")) if (form.get("dist_well_id") or "").isdigit() else None
    values = []
    if variable and wid:
        # Traemos los datos del pozo y extraemos los valores válidos de la variable elegida
        dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
        if dfw is not None and variable in dfw.columns:
            s = pd.to_numeric(dfw[variable], errors="coerce").dropna()
            if variable not in ENG_KEYS:
                s = s[s != 0]  # raw sensors: 0 = no reading
            values = [float(v) for v in s.tolist()]
    # Devolvemos el histograma/boxplot con las mismas funciones que usa Data Cleaning
    return templates.TemplateResponse(
        request, "partials/outlier_variable_chart.html",
        {"request": request, "variable": variable,
         "label": svc.feature_label(variable) if variable else "",
         "box": _box_stats(values), "histogram": _histogram(values),
         "sample_count": len(values)})


@router.post("/feature/wellfilter", response_class=HTMLResponse)
async def feature_wellfilter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Smart well filtering: scores each selected well's data suitability for the
    chosen features and recommends which to keep. Explainable criteria:
    valid rows (completeness + physical ranges + ROP>0), completeness %, signal
    (variation of the controllable parameters) and centroid deviation vs the cohort
    (σ). Keeps at least 4 wells (the grouped-split minimum)."""
    import pandas as pd
    from app.services.rop_prediction import CONTROLLABLE, PLAUSIBLE_RANGES, TARGET
    form = await request.form()
    state = _state(form)
    feats, wids = state["features"], state["well_ids"]
    if not feats or not wids:
        # Sin features o sin pozos no hay nada que analizar
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">Select wells and features first, then click Analyze.</p>')

    names = {w.id: w.well_name for w in WellRepository(db).get_all(skip=0, limit=2000)}
    cols = feats + [TARGET]
    ranges = {c: PLAUSIBLE_RANGES[c] for c in cols if c in PLAUSIBLE_RANGES}
    # Usamos solo las variables controlables (si las hay) para medir la "señal" (variación)
    ctrl = [f for f in feats if f in CONTROLLABLE] or feats

    rows, well_means = [], {}
    for wid in wids:
        dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
        fetched = len(dfw) if dfw is not None else 0
        entry = {"id": wid, "name": names.get(wid, f"Well {wid}"), "n_valid": 0,
                 "completeness": 0.0, "signal": 0.0, "dev": None}
        if dfw is not None and all(c in dfw.columns for c in cols):
            # Filtramos filas válidas (sin NaN, target>0, dentro de rangos físicos plausibles)
            sub = dfw[cols].apply(pd.to_numeric, errors="coerce").dropna()
            sub = sub[sub[TARGET] > 0]
            for c, (lo, hi) in ranges.items():
                sub = sub[(sub[c] >= lo) & (sub[c] <= hi)]
            entry["n_valid"] = len(sub)
            entry["completeness"] = len(sub) / fetched * 100 if fetched else 0.0
            if len(sub) >= 30:
                # Calculamos el coeficiente de variación de cada variable controlable (señal)
                cvs = []
                for f in ctrl:
                    m, s = float(sub[f].mean()), float(sub[f].std() or 0.0)
                    cvs.append(min(1.0, s / (abs(m) + 1e-9)))
                entry["signal"] = sum(cvs) / len(cvs)
                # Guardamos la media de cada feature del pozo para calcular la desviación vs el cohorte
                well_means[wid] = sub[feats].mean()
        rows.append(entry)

    # Centroid deviation vs the cohort (needs ≥3 wells with stats).
    if len(well_means) >= 3:
        # Calculamos cuánto se aleja cada pozo (en desvíos estándar) de la mediana del cohorte
        M = pd.DataFrame(well_means).T
        med, std = M.median(), M.std().replace(0, 1.0)
        for r in rows:
            if r["id"] in M.index:
                r["dev"] = float(((M.loc[r["id"]] - med).abs() / std).mean())

    for r in rows:
        # Calculamos un puntaje ponderado (rows, completitud, señal, cercanía al cohorte)
        dev_pen = 0.0 if r["dev"] is None else min(r["dev"] / 3.0, 1.0)
        r["score"] = round(100 * (0.45 * min(r["n_valid"] / 2000.0, 1.0)
                                  + 0.30 * (r["completeness"] / 100.0)
                                  + 0.15 * r["signal"]
                                  + 0.10 * (1.0 - dev_pen)), 1)
        # Armamos las razones por las que un pozo podría descartarse
        reasons = []
        if r["n_valid"] < 200:
            reasons.append("few valid rows")
        if r["completeness"] < 40:
            reasons.append("low completeness")
        if r["dev"] is not None and r["dev"] > 2.5:
            reasons.append("outlier vs cohort (%.1fσ)" % r["dev"])
        r["keep"] = not reasons
        reason = ", ".join(reasons) if reasons else "good data"
        r["reason"] = reason[0].upper() + reason[1:]

    # Ordenamos de mayor a menor puntaje
    rows.sort(key=lambda r: -r["score"])
    min_keep = min(4, len(rows))
    n_keep = sum(1 for r in rows if r["keep"])
    if n_keep < min_keep:  # top-up by score to preserve a trainable cohort
        # Recuperamos pozos descartados (por puntaje) hasta alcanzar el mínimo entrenable
        for r in rows:
            if n_keep >= min_keep:
                break
            if not r["keep"]:
                r["keep"] = True
                r["reason"] += " · kept to preserve ≥%d wells" % min_keep
                n_keep += 1

    keep_ids = [r["id"] for r in rows if r["keep"]]
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_wellfilter.html",
        {"request": request, "rows": rows, "keep_ids": keep_ids,
         "n_keep": len(keep_ids), "n_drop": len(rows) - len(keep_ids)})


@router.post("/feature/featurefilter", response_class=HTMLResponse)
async def feature_featurefilter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Smart FEATURE filtering — the variable analogue of well filtering. Drops
    variables that are: low completeness, near-constant (no signal), or redundant/
    collinear (|r|>=0.92 with another kept feature — keeps the one more correlated
    with ROP). Keeps at least 2 features."""
    import pandas as pd
    from app.services.rop_features import ENG_KEYS
    from app.services.rop_prediction import TARGET
    form = await request.form()
    state = _state(form)
    feats, wids = state["features"], state["well_ids"]
    if len(feats) < 2 or not wids:
        # Necesitamos al menos 2 features para poder evaluar redundancia entre ellas
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">Select wells and at least 2 features, then click Analyze.</p>')

    cols = feats + [TARGET]
    # Flat per-well row budget, no well-count cap — matches Smart Well Filtering
    # (analyzing only the first N wells would silently disagree with what full
    # training actually pools, and with what wellfilter itself reports).
    # Traemos y concatenamos las filas válidas (target no nulo y positivo) de cada pozo
    frames = []
    for wid in wids:
        dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
        if dfw is None or TARGET not in dfw.columns:
            continue
        have = [c for c in cols if c in dfw.columns]
        sub = dfw[have].apply(pd.to_numeric, errors="coerce")
        sub = sub[sub[TARGET].notna() & (sub[TARGET] > 0)]
        frames.append(sub)
    if not frames:
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">No data available for the selection.</p>')
    df = pd.concat(frames, ignore_index=True)

    # Calculamos, por cada feature, completitud, coeficiente de variación y correlación con el target
    info = {}
    for f in feats:
        if f not in df.columns:
            info[f] = {"completeness": 0.0, "cv": 0.0, "rt": None}
            continue
        s = df[f]
        if f in ENG_KEYS:
            comp = float(s.notna().mean() * 100)
            clean = s.dropna()
        else:
            comp = float(((s.notna()) & (s != 0)).mean() * 100)
            clean = s.where(s != 0).dropna()
        mean, sd = float(clean.mean()) if len(clean) else 0.0, float(clean.std() or 0.0) if len(clean) else 0.0
        pair = df[[f, TARGET]].dropna()
        if f not in ENG_KEYS:
            pair = pair[pair[f] != 0]
        rt = float(pair[f].corr(pair[TARGET])) if len(pair) >= 10 else None
        info[f] = {"completeness": comp, "cv": sd / (abs(mean) + 1e-9), "rt": rt}

    # Calculamos la matriz de correlación absoluta entre las features presentes
    present = [f for f in feats if f in df.columns]
    corr = df[present].apply(pd.to_numeric, errors="coerce").corr().abs() if len(present) > 1 else None

    # Greedy redundancy pass: process features best-correlated-with-target first;
    # a later feature is redundant if it correlates >=0.92 with one already kept.
    drop_redundant = {}
    kept = []
    for f in sorted(present, key=lambda f: -(abs(info[f]["rt"]) if info[f]["rt"] is not None else 0.0)):
        partner = next((g for g in kept if corr is not None and corr.loc[f, g] >= 0.92), None)
        if partner is None:
            kept.append(f)
        else:
            drop_redundant[f] = partner

    # Armamos las filas de resultado con las razones de descarte de cada feature
    rows = []
    for f in feats:
        d = info[f]
        reasons = []
        if d["completeness"] < 40:
            reasons.append("low completeness")
        if d["cv"] < 0.01:
            reasons.append("near-constant")
        if f in drop_redundant:
            reasons.append("redundant with %s" % svc.feature_label(drop_redundant[f]))
        maxr = None
        if corr is not None and f in corr.columns and len(corr.columns) > 1:
            others = [g for g in corr.columns if g != f]
            maxr = float(corr.loc[f, others].max())
        reason = ", ".join(reasons) if reasons else "good"
        rows.append({"feature": f, "label": svc.feature_label(f), "completeness": d["completeness"],
                     "cv": d["cv"], "rt": d["rt"], "maxr": maxr,
                     "keep": not reasons, "reason": reason[0].upper() + reason[1:]})

    # Ordenamos mostrando primero las que se mantienen, luego por mayor correlación con el target
    rows.sort(key=lambda r: (not r["keep"], -(abs(r["rt"]) if r["rt"] is not None else 0.0)))
    n_keep = sum(1 for r in rows if r["keep"])
    for r in rows:  # keep at least 2 (a model needs features)
        # Recuperamos features descartadas hasta alcanzar el mínimo de 2
        if n_keep >= min(2, len(rows)):
            break
        if not r["keep"]:
            r["keep"] = True
            r["reason"] += " · kept to preserve ≥2 features"
            n_keep += 1

    keep_cols = [r["feature"] for r in rows if r["keep"]]
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_featfilter.html",
        {"request": request, "rows": rows, "keep_cols": keep_cols,
         "n_keep": len(keep_cols), "n_drop": len(rows) - len(keep_cols)})


@router.post("/feature/correlation", response_class=HTMLResponse)
async def feature_correlation(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Correlation of each selected feature vs the ROP target (Pearson r), with an
    interactive scatter of a chosen variable against ROP."""
    import pandas as pd
    from app.services.rop_features import ENG_KEYS
    from app.services.rop_prediction import TARGET
    form = await request.form()
    state = _state(form)
    # Leemos el pozo (o "all") y la variable elegida para el scatter
    wid_raw = form.get("corr_well_id") or "all"
    corr_variable = form.get("corr_variable") or ""

    wids = state["well_ids"] if wid_raw == "all" else ([int(wid_raw)] if wid_raw.isdigit() else state["well_ids"])
    feats = state["features"]
    error = None
    rows, points, scatter_var = [], [], ""
    if not feats:
        error = "Select at least one feature (checkboxes above) first."
    elif not wids:
        error = "No wells selected."
    else:
        cols = feats + [TARGET]
        # Flat per-well row budget, no well-count cap — see feature_featurefilter.
        # Traemos y concatenamos las filas válidas de los pozos elegidos
        frames = []
        for wid in wids:
            dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
            if dfw is None or TARGET not in dfw.columns:
                continue
            have = [c for c in cols if c in dfw.columns]
            sub = dfw[have].apply(pd.to_numeric, errors="coerce")
            sub = sub[sub[TARGET].notna() & (sub[TARGET] > 0)]
            frames.append(sub)
        if not frames:
            error = "No data available for the selection."
        else:
            df = pd.concat(frames, ignore_index=True)
            if state["log_target"]:
                # Aplicamos log1p al target si el usuario activó "predecir log(ROP)"
                df[TARGET] = np.log1p(df[TARGET])
            # Calculamos la correlación de cada feature con el target
            for f in feats:
                if f not in df.columns:
                    continue
                pair = df[[f, TARGET]].dropna()
                if f not in ENG_KEYS:
                    pair = pair[pair[f] != 0]
                n = len(pair)
                r = float(pair[f].corr(pair[TARGET])) if n >= 10 else None
                rows.append({"feature": f, "label": svc.feature_label(f), "r": r, "n": n})
            # Ordenamos por magnitud de correlación descendente
            rows.sort(key=lambda x: -(abs(x["r"]) if x["r"] is not None else -1.0))
            # Elegimos la variable a graficar en el scatter (la pedida por el usuario, o la más correlacionada)
            scatter_var = corr_variable if corr_variable in feats else (rows[0]["feature"] if rows else "")
            if scatter_var and scatter_var in df.columns:
                pair = df[[scatter_var, TARGET]].dropna()
                if scatter_var not in ENG_KEYS:
                    pair = pair[pair[scatter_var] != 0]
                if len(pair) > 1200:
                    # Muestreamos para no saturar el gráfico con demasiados puntos
                    pair = pair.sample(1200, random_state=1)
                points = [{"x": float(a), "y": float(b)} for a, b in zip(pair[scatter_var], pair[TARGET])]
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_corr.html",
        {"request": request, "rows": rows, "points": points, "scatter_var": scatter_var,
         "scatter_label": svc.feature_label(scatter_var) if scatter_var else "",
         "target_label": "log(ROP+1)" if state["log_target"] else "ROP (ft/hr)",
         "features": sorted(feats, key=lambda f: svc.feature_label(f).lower()), "error": error,
         "feature_labels": {f: svc.feature_label(f) for f in feats}})


# --------------------------------------------------------------------------- #
# Step 3 — split
# --------------------------------------------------------------------------- #
@router.post("/step/split", response_class=HTMLResponse)
async def step_split(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    # Fail HERE, next to the cause — a degenerate selection used to sail
    # through five more screens and only blow up at Pre-selection with a
    # message far from the step that caused it.
    if not state["well_ids"] or not state["features"]:
        # Volvemos al paso "wells" con un error inline en vez de dejar avanzar una
        # selección incompleta
        missing = "well" if not state["well_ids"] else "feature"
        extra = dict(wells=_well_rows(db, depth_range=state.get("depth_range"), date_range=state.get("date_range"),
                                      var_completeness_min=state.get("var_completeness_min"),
                                      target_completeness_min=state.get("target_completeness_min"),
                                      field=state.get("field"), bit_sizes=state.get("bit_sizes")),
                     n_features=len(svc.feature_candidates()),
                     selected_ids=set(state["well_ids"]), show_features=bool(state["well_ids"]),
                     field_options=_field_options(db), bit_size_options=svc.bit_size_options(),
                     error=f"Select at least one {missing} before continuing to Train / Test.")
        if state["well_ids"]:
            extra.update(_features_ctx(db, state))
        return _render(request, current_user, "wells", state=state, **extra)
    # Selección válida: resolvemos los nombres de los pozos elegidos y avanzamos al paso "split"
    names = {w.id: w.well_name for w in WellRepository(db).get_all(skip=0, limit=2000)}
    wells = [{"id": wid, "name": names.get(wid, f"Well {wid}")} for wid in state["well_ids"]]
    return _render(request, current_user, "split", state=state, wells=wells)


# --------------------------------------------------------------------------- #
# Steps 4-6 — processing, split like the Data-Cleaning wizard (Scaling / PCA /
# Outliers) each with a live preview computed on a pooled sample.
# --------------------------------------------------------------------------- #
# Renderizamos el paso de Scaling (solo re-mostramos el formulario con el estado actual)
@router.post("/step/scaling", response_class=HTMLResponse)
async def step_scaling(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    return _render(request, current_user, "scaling", state=state)


# Renderizamos el paso de PCA
@router.post("/step/pca", response_class=HTMLResponse)
async def step_pca(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    return _render(request, current_user, "pca", state=state)


# Renderizamos el paso de Outliers
@router.post("/step/outliers", response_class=HTMLResponse)
async def step_outliers(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    return _render(request, current_user, "outliers", state=state)


@router.post("/outliers/param-fields", response_class=HTMLResponse)
async def outlier_param_fields(request: Request, current_user: User = Depends(get_current_user_web)):
    """Re-renders the per-method outlier param field(s) when the method dropdown
    changes. ROP-Prediction-owned (not the shared /outliers/param-fields route)
    because it also emits hidden fallbacks for the other six params — see
    rop_pred_outlier_fields.html for why.

    POST, not GET: the dropdown's hx-include carries the ENTIRE wizard state
    (potentially hundreds of well_ids + dozens of features) — as a GET that all
    went into the query string, which can blow past request-line limits on big
    selections. Every other state-carrying call in the module is a POST."""
    q = await request.form()

    # Definimos un helper local para leer un float opcional del form
    def _f(k, default=None):
        v = q.get(k)
        try:
            return float(v) if v not in (None, "") else default
        except (TypeError, ValueError):
            return default

    # Resolvemos el método elegido y armamos los parámetros de cada método (con sus defaults)
    method = q.get("outlier_method") or q.get("method") or "none"
    outlier_params = {
        "threshold": _f("outlier_threshold", 3.0), "multiplier": _f("outlier_multiplier", 1.5),
        "contamination": _f("outlier_contamination", 0.05), "n_estimators": _f("outlier_n_estimators"),
        "eps": _f("outlier_eps", 0.5), "min_samples": _f("outlier_min_samples", 5),
        "n_neighbors": _f("outlier_n_neighbors", 20),
    }
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_outlier_fields.html",
        {"request": request, "method": method, "outlier_params": outlier_params})


def _preview_matrix(db, well_ids, features, depth_range=None, date_range=None, bit_sizes=None, include_target=False):
    """Pooled feature matrix (raw + engineered) for the processing previews.

    Pulls every row of every selected well — no cap — same pool build_dataset()
    itself uses for real training, so the Scaling/PCA/Outliers preview is never
    computed on a truncated sample that could disagree with what training sees.

    With ``include_target=True`` the target (ROP) is appended as the LAST column
    (so callers who need feature-vs-target, e.g. the no-PCA outlier scatter, don't
    need a second pooling pass)."""
    import pandas as pd
    from app.services.rop_prediction import PLAUSIBLE_RANGES, TARGET
    cols = features + [TARGET]
    ranges = {c: PLAUSIBLE_RANGES[c] for c in cols if c in PLAUSIBLE_RANGES}
    out_cols = features + ([TARGET] if include_target else [])
    # Recorremos cada pozo, filtramos filas válidas (sin NaN, target>0, dentro de rango físico)
    # y las vamos acumulando
    frames = []
    for wid in well_ids:
        dfw = rop_ml.well_frame(db, wid, 2_000_000, depth_range=depth_range, date_range=date_range, bit_sizes=bit_sizes)
        if dfw is None or not all(c in dfw.columns for c in cols):
            continue
        sub = dfw[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=cols)
        sub = sub[sub[TARGET] > 0]
        for c, (lo, hi) in ranges.items():
            sub = sub[(sub[c] >= lo) & (sub[c] <= hi)]
        frames.append(sub[out_cols])
    if not frames:
        # Sin datos, devolvemos una matriz vacía con la forma correcta
        return np.zeros((0, len(out_cols)))
    df = pd.concat(frames, ignore_index=True)
    return df.to_numpy(dtype=float)


def _pca_fit(state, X):
    """Fit PCA on the (scaled) preview matrix; returns (pca, X_scaled, labels)."""
    from sklearn.decomposition import PCA
    # Escalamos la matriz con el método elegido (o la dejamos sin escalar si no hay escalador)
    sc = rop_ml._scaler(state["scaling"])
    Xs = sc.fit_transform(X) if sc is not None else X
    # Resolvemos el número de componentes (None = automático) y ajustamos PCA
    nc = int(state["pca_components"]) if str(state["pca_components"]).isdigit() else None
    p = PCA(n_components=nc, svd_solver=state["pca_svd_solver"],
            whiten=state["pca_whiten"], random_state=42).fit(Xs)
    labels = ["PC%d" % (i + 1) for i in range(p.n_components_)]
    return p, Xs, labels


def _diagnostic_pca(X):
    """2-component PCA fit fresh (always standardized, independent of the
    wizard's own Scaling/PCA config) purely to VISUALIZE outlier detection —
    used when PCA is disabled for training. A raw single-variable-vs-target
    scatter is a 2D shadow of a decision made in full multivariate space (a
    point can look 'normal' on that one axis and still be flagged because of
    a different variable) — this instead shows the actual multivariate
    structure the detector saw, the standard way to visualize multivariate
    anomaly detection. Not tied to training in any way; diagnostic only."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    # Estandarizamos siempre (independiente del scaler elegido por el usuario para entrenar)
    Xs = StandardScaler().fit_transform(X)
    # Ajustamos PCA a (como máximo) 2 componentes, solo para visualizar
    p = PCA(n_components=min(2, X.shape[1]), random_state=42).fit(Xs)
    Z = p.transform(Xs)
    evr = p.explained_variance_ratio_
    labels = ["PC%d (%.1f%%)" % (i + 1, evr[i] * 100) for i in range(Z.shape[1])]
    return Z, labels


# These render the SAME partials as the Data-Cleaning (Outliers) wizard, so the
# Scaling / PCA / Outliers previews look identical (DrillingCharts variance &
# scatter charts, raw-vs-scaled table, pipeline metrics).
@router.post("/preview/scaling", response_class=HTMLResponse)
async def preview_scaling(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    # Armamos la matriz pooled (sin cap) de features de los pozos seleccionados
    X = _preview_matrix(db, state["well_ids"], state["features"],
                        depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
    rows = []
    if len(X):
        # Escalamos y comparamos min/max/mean crudo vs escalado, columna por columna
        sc = rop_ml._scaler(state["scaling"])
        Xs = sc.fit_transform(X) if sc is not None else X
        for i, f in enumerate(state["features"]):
            rows.append({"feature": svc.feature_label(f),
                         "raw_min": float(X[:, i].min()), "raw_max": float(X[:, i].max()), "raw_mean": float(X[:, i].mean()),
                         "sc_min": float(Xs[:, i].min()), "sc_max": float(Xs[:, i].max()), "sc_mean": float(Xs[:, i].mean())})
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_preview_scaling.html",
                                      {"request": request, "rows": rows, "n": len(X), "method": state["scaling"]})


@router.post("/preview/pca", response_class=HTMLResponse)
async def preview_pca(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    X = _preview_matrix(db, state["well_ids"], state["features"],
                        depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
    result, cumulative, error = None, [], None
    if len(X) > 2:
        try:
            # Ajustamos PCA y calculamos la varianza explicada acumulada por componente
            p, _Xs, labels = _pca_fit(state, X)
            evr = [float(v) for v in p.explained_variance_ratio_]
            c = 0.0
            for v in evr:
                c += v
                cumulative.append(c * 100)  # percent, matching the Data-Cleaning PCA preview
            result = {"component_labels": labels, "explained_variance_ratio": evr}
        except Exception as exc:
            error = f"PCA failed: {str(exc)[:200]}"
    else:
        error = "Not enough data to run PCA."
    return templates.TemplateResponse(request, "partials/outlier_preview_pca.html",
                                      {"request": request, "result": result, "cumulative": cumulative, "error": error})


@router.post("/preview/pca-scatter", response_class=HTMLResponse)
async def preview_pca_scatter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await request.form()
    state = _state(form)
    # Leemos qué par de componentes graficar (por defecto PC1 vs PC2)
    try:
        x_idx = int(form.get("pca_scatter_x") or 0)
        y_idx = int(form.get("pca_scatter_y") or 1)
    except ValueError:
        x_idx, y_idx = 0, 1
    X = _preview_matrix(db, state["well_ids"], state["features"],
                        depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"))
    points, labels, error = [], [], None
    if len(X) > 2:
        try:
            # Ajustamos PCA, proyectamos y muestreamos hasta 1500 puntos para graficar
            p, Xs, labels = _pca_fit(state, X)
            proj = p.transform(Xs)
            if proj.shape[1] > max(x_idx, y_idx):
                rng = np.random.RandomState(1)
                idx = rng.permutation(len(proj))[:1500]
                points = [{"x": float(proj[i, x_idx]), "y": float(proj[i, y_idx])} for i in idx]
        except Exception as exc:
            error = f"PCA failed: {str(exc)[:200]}"
    else:
        error = "Not enough data."
    return templates.TemplateResponse(request, "partials/outlier_pca_scatter.html",
                                      {"request": request, "points": points, "labels": labels,
                                       "x_idx": x_idx, "y_idx": y_idx, "error": error})


@router.post("/preview/outlier-scatter", response_class=HTMLResponse)
async def preview_outlier_scatter(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Inliers (blue) vs outliers (red) scatter for the Outliers step. ALWAYS a
    diagnostic-only 2-component PCA projection (see _diagnostic_pca()), fully
    decoupled from the wizard's own Scaling/PCA config for training — Outliers
    comes before those steps anyway, and this chart's only job is to visualize
    the outlier split faithfully (a raw feature vs the ROP target is just a 2D
    shadow of a decision made in full multivariate space), not to preview the
    training pipeline."""
    form = await request.form()
    state = _state(form)
    # Leemos qué par de componentes diagnósticos graficar
    try:
        x_idx = int(form.get("outlier_scatter_x") or 0)
        y_idx = int(form.get("outlier_scatter_y") or 1)
    except ValueError:
        x_idx, y_idx = 0, 1
    # Armamos la matriz con el target incluido como última columna (para calcular el mismo
    # mask de inliers/outliers que usaría el entrenamiento real)
    XY = _preview_matrix(db, state["well_ids"], state["features"],
                         depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"),
                         include_target=True)
    inliers, outliers, labels, error, x_label, y_label = [], [], [], None, "", ""
    if len(XY) > 2:
        try:
            X, y = XY[:, :-1], XY[:, -1]
            # REAL target column, matching training: _inlier_mask stacks y into
            # the data, so zscore/iqr/model-based methods all see one extra
            # dimension at train time — a zeros(y) preview flagged different
            # points than the actual run would remove.
            # Calculamos qué filas son inliers/outliers con el método y parámetros elegidos
            mask = (rop_ml._inlier_mask(X, y, state["outlier_method"], _outlier_params(state))
                    if state["outlier_method"] != "none" else np.ones(len(X), bool))
            # Muestreamos hasta 2000 puntos y los proyectamos a 2D con PCA diagnóstico
            rng = np.random.RandomState(1)
            idx = rng.permutation(len(X))[:2000]
            Z, labels = _diagnostic_pca(X)
            if Z.shape[1] > max(x_idx, y_idx):
                # Repartimos cada punto muestreado en inliers u outliers según el mask
                for i in idx:
                    point = {"x": float(Z[i, x_idx]), "y": float(Z[i, y_idx])}
                    (outliers if not mask[i] else inliers).append(point)
                x_label, y_label = labels[x_idx], labels[y_idx]
            else:
                labels = []
        except Exception as exc:
            error = f"Scatter failed: {str(exc)[:200]}"
    else:
        error = "Not enough data."
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_outlier_scatter.html",
        {"request": request, "inliers": inliers, "outliers": outliers,
         "labels": labels, "x_idx": x_idx, "y_idx": y_idx, "error": error,
         "x_label": x_label, "y_label": y_label})


@router.post("/preview/outliers", response_class=HTMLResponse)
async def preview_outliers(request: Request, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    XY = _preview_matrix(db, state["well_ids"], state["features"],
                         depth_range=state.get("depth_range"), date_range=state.get("date_range"), bit_sizes=state.get("bit_sizes"),
                         include_target=True)
    result, error, labels = None, None, []
    if len(XY):
        X, y = XY[:, :-1], XY[:, -1]
        try:
            # Real y, matching what training's _inlier_mask actually sees —
            # see preview_outlier_scatter for the full rationale.
            mask = (rop_ml._inlier_mask(X, y, state["outlier_method"], _outlier_params(state))
                    if state["outlier_method"] != "none" else np.ones(len(X), bool))
        except Exception as exc:
            return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_outlier_preview.html",
                                              {"request": request, "result": None,
                                               "error": f"Outlier preview failed: {str(exc)[:200]}"})
        # Calculamos las métricas del preview: total, procesados, outliers detectados y su porcentaje
        n = len(X)
        out = int((~mask).sum())
        result = {"metrics": {"total_records": n, "processed_records": n, "outlier_records": out,
                              "outlier_percentage": (out / n * 100 if n else 0.0), "dropped_records": 0,
                              "explained_variance_ratio": None}, "component_labels": []}
        # Also refresh the Component scatter's X/Y selectors below with real
        # component names — same OOB-swap pattern the PCA step's own Calculate
        # preview already uses — so the user isn't stuck with a "1"/"PC1" static
        # placeholder until they blindly click Plot once. ALWAYS the diagnostic-
        # only projection (see _diagnostic_pca()) — independent of the wizard's
        # own Scaling/PCA config for training, which is a separate concern.
        try:
            _Z, labels = _diagnostic_pca(X)
        except Exception:
            labels = []
    else:
        error = "Not enough data to preview."
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_outlier_preview.html",
                                      {"request": request, "result": result, "error": error, "labels": labels})


# --------------------------------------------------------------------------- #
# Step 7 — models
# --------------------------------------------------------------------------- #
@router.post("/step/models", response_class=HTMLResponse)
async def step_models(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    # Usamos los modelos ya elegidos por el usuario, o los modelos por defecto si no eligió ninguno
    selected = set(state["models"]) or set(rop_ml.DEFAULT_MODELS)
    models = [{"key": k, **v, "selected": k in selected} for k, v in rop_ml.MODELS.items()]
    # Estimamos cuánto tardaría correr la pre-selección con la config actual
    estimate = rop_ml.estimate_seconds(_cfg(state), "preselect")
    return _render(request, current_user, "models", state=state, models=models, estimate=estimate)


@router.post("/step/preselect", response_class=HTMLResponse)
async def step_preselect(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Revisit (breadcrumb / Back from Hyperparameters): redisplay the last
    finished pre-selection result for this exact config, or a 'not run yet'
    card — never re-runs (that's the dedicated Run/Re-run button's job)."""
    state = _state(await request.form())
    return _revisit_preselect(request, current_user, state, db)


# --------------------------------------------------------------------------- #
# Background jobs (pre-selection / HPO / validation)
# --------------------------------------------------------------------------- #
# Job de background: construye el dataset y corre la pre-selección (entrenamiento rápido
# de todos los modelos candidatos) para rankearlos. Corre en un hilo aparte, por eso abre
# su PROPIA sesión de BD en vez de reutilizar la inyectada por FastAPI.
def _job_preselect(cfg, model_keys, progress_cb=None, cancel_event=None):
    s = db_manager._session_factory()
    try:
        ds = rop_ml.build_dataset(s, cfg, progress_cb=progress_cb, cancel_event=cancel_event)
        if len(ds.X_train) < 30:
            # Muy pocas filas válidas tras el filtrado: no vale la pena entrenar nada
            return {"error": "Not enough valid rows after the quality gate & filtering. Pick more wells or different features."}
        return {"ranked": rop_ml.preselect(ds, model_keys, progress_cb=progress_cb, cancel_event=cancel_event),
                "ds_info": {"n_train": len(ds.X_train), "n_test": len(ds.X_test),
                            "n_blind": len(ds.y_blind) if ds.y_blind is not None else 0,
                            "n_features": len(ds.feature_names), "n_removed": ds.n_removed_outliers,
                            "n_invalid": ds.n_invalid, "split_grouped": ds.split_grouped}}
    finally:
        # Cerramos siempre la sesión propia del hilo, corra bien o falle
        s.close()


# Job de background: construye el dataset y corre la optimización de hiperparámetros (Optuna)
# para el modelo elegido
def _job_hpo(cfg, model_key, n_trials, progress_cb=None, cancel_event=None):
    s = db_manager._session_factory()
    try:
        ds = rop_ml.build_dataset(s, cfg, progress_cb=progress_cb, cancel_event=cancel_event)
        res = rop_ml.optimize(ds, model_key, n_trials=n_trials, progress_cb=progress_cb, cancel_event=cancel_event)

        # Metrics of the optimised model vs defaults, on BOTH train and test, so
        # the HPO step shows what the tuning actually bought — and whether it's
        # overfitting (train up, test flat/down) rather than genuinely improving.
        # Definimos un helper que entrena con unos parámetros dados y devuelve las métricas
        # en train y test
        def _eval(params):
            m = rop_ml.make_model(model_key, params, log_target=ds.log_target)
            m.fit(ds.X_train, ds.y_train)
            return {"train": rop_ml.metrics(ds.y_train, m.predict(ds.X_train)),
                    "test": rop_ml.metrics(ds.y_test, m.predict(ds.X_test))}

        # Comparamos el modelo optimizado (best_params) contra el modelo con parámetros por defecto
        tuned, default = _eval(res["best_params"]), _eval({})
        res["tuned_metrics"] = tuned["test"]
        res["default_metrics"] = default["test"]
        res["tuned_train_metrics"] = tuned["train"]
        res["default_train_metrics"] = default["train"]
        return res
    finally:
        s.close()


# Job de background: construye el dataset, entrena el modelo final, calibra el intervalo de
# predicción, calcula las métricas de validación completas y empaqueta el pipeline para inferencia
def _job_validation(cfg, model_key, params, progress_cb=None, cancel_event=None):
    s = db_manager._session_factory()
    try:
        ds = rop_ml.build_dataset(s, cfg, progress_cb=progress_cb, cancel_event=cancel_event)
        # Fit the final model ONCE (previously final_validation() and fit_pipeline()
        # each independently fit an identical model + recomputed the same conformal
        # quantile — doubling the heaviest step in the whole wizard for no benefit).
        # Entrenamos el modelo final y calibramos el cuantil conformal UNA sola vez
        model, q = rop_ml.fit_model_and_q(ds, model_key, params, progress_cb=progress_cb, cancel_event=cancel_event)
        # Calculamos las métricas de validación completas (train/test/blind, SHAP, drift, etc.)
        result = rop_ml.final_validation(ds, model_key, params, model=model, q=q,
                                         progress_cb=progress_cb, cancel_event=cancel_event)
        if progress_cb is not None:
            progress_cb({"stage": "Packaging model for inference…"})
        # Empaquetamos el pipeline (modelo + scaler + PCA + metadatos) reutilizando el mismo
        # modelo y cuantil ya calculados, para poder usarlo luego en inferencia/what-if
        pipe = rop_ml.fit_pipeline(ds, model_key, params, model=model, q=q)
        ds_info = {"n_train": len(ds.X_train), "n_test": len(ds.X_test),
                   "n_blind": len(ds.y_blind) if ds.y_blind is not None else 0,
                   "blind_well_id": ds.blind_well_id, "n_features": len(ds.feature_names),
                   "used_params": params}
        return {"result": result, "ds_info": ds_info, "pipeline": pipe}
    finally:
        s.close()


# Lanzamos un job en background (preselect/hpo/validation) y registramos su contexto para
# poder pollearlo, revisitarlo o persistirlo
def _start(kind, step, state, msg, fn, *args):
    def _persist(job_id, result):
        """Runs in the worker thread the moment the job completes — durable even
        if no browser ever polls the finished job (tab closed, laptop asleep).
        Error-shaped results ({"error": ...}) aren't worth reviving later."""
        if isinstance(result, dict) and result.get("error"):
            # No persistimos resultados de error — no vale la pena revivirlos después
            return
        s = db_manager._session_factory()
        try:
            rop_run_store.save(s, job_id, kind, state, result)
        finally:
            s.close()

    # Enviamos el job al pool de background, con _persist como callback al terminar
    job_id = rop_jobs.submit(fn, *args, on_done=_persist)
    if len(_RUN_CTX) > 40:
        # Evict oldest entries first, but skip any job still actually running —
        # a full .clear() here would strand an in-flight run's polling (it'd
        # start reporting "server restarted" even though the job is still fine).
        # Desalojamos entradas viejas del store en memoria, saltando los jobs aún corriendo
        for jid in list(_RUN_CTX):
            if len(_RUN_CTX) <= 40:
                break
            if rop_jobs.get(jid)["status"] != "running":
                _RUN_CTX.pop(jid, None)
    # Registramos el contexto de este job nuevo
    _RUN_CTX[job_id] = {"kind": kind, "step": step, "state": state, "msg": msg}
    return job_id


@router.post("/run/preselect", response_class=HTMLResponse)
async def run_preselect(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    if not state["models"]:
        # No silent fallback to DEFAULT_MODELS: the user just cleared every
        # checkbox — training 6 models they explicitly deselected would be
        # invisible magic. Re-render the step with an inline error instead.
        selected = set()
        models = [{"key": k, **v, "selected": k in selected} for k, v in rop_ml.MODELS.items()]
        return _render(request, current_user, "models", state=state, models=models,
                       estimate=rop_ml.estimate_seconds(_cfg(state), "preselect"),
                       error="Select at least one model to run pre-selection.")
    # Lanzamos el job de pre-selección en background y mostramos la pantalla de "corriendo"
    job_id = _start("preselect", "preselect", state, "Training models…",
                    _job_preselect, _cfg(state), state["models"])
    return _render(request, current_user, "preselect", state=state, body_partial="running",
                   job_id=job_id, running_msg="Training models…",
                   cancel_url=f"/analytics/rop-prediction/job/{job_id}/cancel")


@router.post("/step/hpo", response_class=HTMLResponse)
async def step_hpo(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Revisit (breadcrumb / Back from Validation): redisplay the last finished
    HPO result for this exact model+config, or the bare 'run optimisation' form."""
    state = _state(await request.form())
    return _revisit_hpo(request, current_user, state, db)


@router.post("/run/hpo", response_class=HTMLResponse)
async def run_hpo(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    # Lanzamos el job de optimización de hiperparámetros en background
    job_id = _start("hpo", "hpo", state, "Optimizing hyperparameters…",
                    _job_hpo, _cfg(state), state["chosen_model"], state["hpo_trials"])
    return _render(request, current_user, "hpo", state=state, body_partial="running",
                   job_id=job_id, running_msg="Optimizing hyperparameters…",
                   cancel_url=f"/analytics/rop-prediction/job/{job_id}/cancel")


@router.post("/run/validation", response_class=HTMLResponse)
async def run_validation(request: Request, current_user: User = Depends(get_current_user_web)):
    state = _state(await request.form())
    try:
        # Parseamos los mejores hiperparámetros (del HPO, o vacío si se saltó ese paso)
        params = json.loads(state["best_params"] or "{}")
    except json.JSONDecodeError:
        params = {}
    # Lanzamos el job de validación final en background
    job_id = _start("validation", "validation", state, "Validating & fitting final model…",
                    _job_validation, _cfg(state), state["chosen_model"], params)
    return _render(request, current_user, "validation", state=state, body_partial="running",
                   job_id=job_id, running_msg="Validating & fitting final model…",
                   cancel_url=f"/analytics/rop-prediction/job/{job_id}/cancel")


@router.post("/step/validation", response_class=HTMLResponse)
async def step_validation(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Revisit (breadcrumb): redisplay the last finished validation result for
    this exact model+params+config, or a 'not run yet' card. Validation has no
    independent config screen of its own, so this is only reachable via the
    breadcrumb — the normal forward path is the HPO step's Run/Skip buttons."""
    state = _state(await request.form())
    return _revisit_validation(request, current_user, state, db)


# Where "Back" (which cancels the running job) lands, per job kind — matches
# the target the equivalent Back button already uses once that step finishes.
# Definimos a qué paso vuelve el botón "Back" (que cancela el job en curso), según el tipo de job
_CANCEL_BACK_STEP = {"preselect": "models", "hpo": "preselect", "validation": "hpo"}

# Heuristic (start%, end%) budget per validation stage — used only to turn the
# stage-message string into a rough overall progress bar / ETA, not anything
# exact. "Loading well data" dominates real runtime by far (per-well DB round
# trips), hence the outsized share; see rop_ml.estimate_seconds for the same
# calibration basis.
_VALIDATION_STAGE_RANGES = [
    # EVERY stage string final_validation()/build_dataset() can emit must have
    # an entry — a missing prefix makes _validation_progress_pct return None,
    # which silently hides the progress bar and ETA mid-run (it used to vanish
    # during "Splitting & scaling" and both curve stages, two of the slowest).
    ("Loading well data", 0.00, 0.55),
    ("Splitting & scaling", 0.55, 0.58),
    ("Fitting final model", 0.58, 0.68),
    ("Calibrating prediction interval", 0.68, 0.72),
    ("Computing permutation importance", 0.72, 0.79),
    ("Computing SHAP values", 0.79, 0.86),
    ("Computing learning curve", 0.86, 0.93),
    ("Computing validation curve", 0.93, 0.99),
    ("Packaging model for inference", 0.99, 1.00),
]
# Compilamos el patrón que extrae "(hecho/total)" de un mensaje de progreso tipo well-by-well
_WELL_PROGRESS_RE = re.compile(r"\((\d+)/(\d+)\)")


# Traducimos el string de "stage" actual del job de validación a un porcentaje aproximado de
# progreso global, usando los rangos calibrados en _VALIDATION_STAGE_RANGES
def _validation_progress_pct(stage):
    if not stage:
        return None
    for prefix, lo, hi in _VALIDATION_STAGE_RANGES:
        if stage.startswith(prefix):
            # Si el stage trae "(n/total)" (p.ej. cargando pozo a pozo), interpolamos dentro del rango
            m = _WELL_PROGRESS_RE.search(stage)
            if m and int(m.group(2)):
                return lo + (int(m.group(1)) / int(m.group(2))) * (hi - lo)
            return lo
    return None


@router.get("/job/{job_id}", response_class=HTMLResponse)
async def poll(request: Request, job_id: str, current_user: User = Depends(get_current_user_web), since: int = 0):
    # Buscamos el contexto y el estado actual del job en los stores en memoria
    ctx = _RUN_CTX.get(job_id)
    job = rop_jobs.get(job_id)
    if ctx is None:
        # The in-process job store was lost (e.g. server restart mid-run, or this
        # run was cancelled from another poll of the same job).
        return HTMLResponse(
            '<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">'
            'This run is no longer available (the server restarted). Please start again.</p>'
            '<div style="margin-top:10px;"><a href="/analytics/rop-prediction" class="btn btn-primary btn-sm">Restart wizard</a></div></div>')
    kind, step, state = ctx["kind"], ctx["step"], ctx["state"]

    if job["status"] == "running":
        progress = job.get("progress")
        extra = {}
        # preselect/hpo both start with a build_dataset() pass that reports plain
        # {"stage": "..."} progress (loading each well, then splitting/scaling) —
        # same shape validation already used — before switching to their own
        # {"done"/"current"} or {"history"} shape once training/trials start.
        in_loading_stage = bool(progress and "stage" in progress)
        if kind == "preselect" and progress is not None and not in_loading_stage:
            # Armamos una fila de progreso por cada modelo (terminado / en curso / pendiente)
            model_keys = state.get("models") or rop_ml.DEFAULT_MODELS
            done_by_key = {r["key"]: r for r in progress.get("done", [])}
            extra["progress_rows"] = [
                {"key": k, "label": rop_ml.MODELS.get(k, {}).get("label", k), "result": done_by_key.get(k),
                 "current": k == progress.get("current")}
                for k in model_keys
            ]
            extra["progress_done"] = len(progress.get("done", []))
            extra["progress_total"] = progress.get("total", len(model_keys))
        elif kind == "hpo" and progress is not None and not in_loading_stage:
            # Exponemos el historial de trials de Optuna corridos hasta ahora
            extra["hpo_progress_history"] = progress.get("history", [])
            extra["progress_done"] = len(extra["hpo_progress_history"])
            extra["progress_total"] = progress.get("total")

        # Nothing new since the caller's last render (`since`) — tell htmx to
        # skip the swap entirely (204 = no-op) instead of re-rendering identical
        # content, which is what was causing the visible flicker every 2s even
        # when no model/trial had actually finished yet. Doesn't apply during the
        # loading-stage text phase (no trial/model counter to dedupe against yet,
        # and skipping it there is exactly what left the screen blank).
        if kind in ("preselect", "hpo") and not in_loading_stage and extra.get("progress_done", 0) <= since:
            return HTMLResponse(status_code=204)

        extra["cancel_url"] = f"/analytics/rop-prediction/job/{job_id}/cancel" if kind in _CANCEL_BACK_STEP else None
        extra["stop_requested"] = job.get("stop_requested", False)
        # The running message itself is swapped for the job's current stage
        # (loading wells / fitting / permutation importance / SHAP / …) whenever
        # one is reported, so a run that takes minutes on a large well selection
        # never sits on a silent, unchanging spinner — applies to all 3 kinds,
        # since preselect/hpo/validation all go through build_dataset() first.
        running_msg = (progress.get("stage") if progress else None) or ctx["msg"]
        if kind == "validation" and progress:
            # Calculamos el porcentaje de avance y proyectamos el ETA restante
            pct = _validation_progress_pct(progress.get("stage"))
            elapsed = job.get("elapsed")
            extra["progress_pct"] = pct
            # Linear projection from elapsed/pct — only meaningful once we're
            # past the very first sliver of progress (avoids a wild early spike).
            extra["eta_seconds"] = (elapsed / pct * (1 - pct)) if (pct and pct > 0.03 and elapsed is not None) else None
        # Re-renderizamos el fragmento "running" con el progreso actualizado
        return _render(request, current_user, step, state=state, body_partial="running",
                       job_id=job_id, running_msg=running_msg, **extra)

    # El job ya terminó (o falló): recuperamos su resultado y revisamos si hubo error
    result = job.get("result") or {}
    err = job.get("error") or result.get("error")
    if err:
        if kind == "hpo":
            # Without can_hpo/model_label the HPO template's else-branch renders
            # a misleading "<blank> has no hyperparameters to tune" AND hides
            # the Run button — leaving no way to retry after a transient error.
            return _render(request, current_user, "hpo", state=state, error=err,
                           can_hpo=rop_ml.supports_hpo(state.get("chosen_model", "")),
                           model_label=rop_ml.MODELS.get(state.get("chosen_model"), {}).get("label", state.get("chosen_model")),
                           hpo_estimate=rop_ml.estimate_seconds(_cfg(state), "hpo", n_trials=int(state.get("hpo_trials") or 20)),
                           validation_estimate=rop_ml.estimate_seconds(_cfg(state), "validation"))
        return _render(request, current_user, step, state=state, error=err)

    # NOTE: durable persistence happens in _start()'s on_done hook the moment
    # the worker finishes — NOT here — so closing the tab mid-run doesn't lose
    # the result. This branch only renders.

    if kind == "preselect":
        # Guardamos el job_id en el estado y, si aún no hay modelo elegido, preseleccionamos
        # automáticamente el mejor ranqueado que haya funcionado
        state2 = dict(state)
        state2["preselect_job_id"] = job_id
        if not state2.get("chosen_model"):
            best = next((r for r in result["ranked"] if r["ok"]), None)
            if best:
                state2["chosen_model"] = best["key"]
        return _render(request, current_user, "preselect", state=state2,
                       ranked=result["ranked"], ds_info=result["ds_info"])
    if kind == "hpo":
        # Guardamos el job_id y los mejores hiperparámetros encontrados en el estado
        state2 = dict(state)
        state2["hpo_job_id"] = job_id
        state2["best_params"] = json.dumps(result["best_params"])
        return _render(request, current_user, "hpo", state=state2, hpo_result=result,
                       can_hpo=rop_ml.supports_hpo(state["chosen_model"]),
                       model_label=rop_ml.MODELS.get(state["chosen_model"], {}).get("label", state["chosen_model"]),
                       hpo_estimate=rop_ml.estimate_seconds(_cfg(state), "hpo", n_trials=int(state.get("hpo_trials") or 20)),
                       validation_estimate=rop_ml.estimate_seconds(_cfg(state), "validation"))
    # validation
    # Guardamos el pipeline entrenado en el store en memoria, para poder guardarlo o usarlo en logview
    _PIPELINE_STORE[job_id] = result["pipeline"]
    if len(_PIPELINE_STORE) > 20:
        # Desalojamos los pipelines más antiguos si superamos el límite del store
        for k in list(_PIPELINE_STORE)[:-20]:
            _PIPELINE_STORE.pop(k, None)
    state2 = dict(state)
    state2["validation_job_id"] = job_id
    return _render(request, current_user, "validation", state=state2,
                   result=_validation_result_defaults(result["result"]),
                   ds_info=result["ds_info"], result_token=job_id,
                   model_label=rop_ml.MODELS.get(state["chosen_model"], {}).get("label", state["chosen_model"]))


@router.post("/job/{job_id}/cancel", response_class=HTMLResponse)
async def cancel_run(request: Request, job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """'Back' while a preselect/HPO/validation job is running: stops it
    (cooperatively — build_dataset/fit_model_and_q/final_validation check
    cancel_event between stages same as preselect/optimize do between
    models/trials, so this actually frees the worker soon rather than letting
    it run to completion in the background) and redisplays whatever result the
    PREVIOUS step already has cached (never re-runs it — see _revisit_*)."""
    # Sacamos el contexto del job (dejamos de rastrearlo) y le pedimos al worker que se detenga
    ctx = _RUN_CTX.pop(job_id, None)
    rop_jobs.cancel(job_id)
    if ctx is None:
        return HTMLResponse(
            '<div class="card p-4"><p style="color:var(--color-text-muted);">Nothing to go back to.</p>'
            '<div style="margin-top:10px;"><a href="/analytics/rop-prediction" class="btn btn-primary btn-sm">Restart wizard</a></div></div>')
    kind, state = ctx["kind"], ctx["state"]

    if kind == "preselect":
        # Volvemos al paso "models" (antes de la pre-selección)
        selected = set(state["models"]) or set(rop_ml.DEFAULT_MODELS)
        models = [{"key": k, **v, "selected": k in selected} for k, v in rop_ml.MODELS.items()]
        return _render(request, current_user, "models", state=state, models=models,
                       estimate=rop_ml.estimate_seconds(_cfg(state), "preselect"))
    if kind == "hpo":
        # Volvemos al paso "preselect", redisplayando su resultado cacheado
        return _revisit_preselect(request, current_user, state, db)
    # Volvemos al paso "hpo", redisplayando su resultado cacheado
    return _revisit_hpo(request, current_user, state, db)


@router.post("/job/{job_id}/stop-early", response_class=HTMLResponse)
async def stop_early(job_id: str, current_user: User = Depends(get_current_user_web)):
    """HPO 'stop early, keep the best trial found so far' — unlike Back/cancel,
    this does NOT discard the job: it just asks optimize() to stop after the
    trial in flight, and the existing polling picks up the normal 'done' result
    (built from whichever trials actually completed) a couple of seconds later."""
    # Pedimos al job que se detenga tras el trial en curso (sin descartar lo ya hecho)
    rop_jobs.request_stop(job_id)
    return HTMLResponse(
        '<span class="text-sm" style="color:var(--color-text-muted); display:inline-flex; align-items:center; gap:6px;">'
        '<span class="spinner-el" style="width:12px; height:12px; border-width:2px;"></span>'
        'Stopping after this trial…</span>')


# Actual-vs-predicted log view, scoped to a live/revisited/loaded Validation
# job rather than a saved experiment — same _split_well_options/_logview_records
# helpers, just sourced from _RUN_CTX[job_id]["state"]/_PIPELINE_STORE[job_id]
# instead of a DB row, so it works before the user has clicked Save.
@router.get("/job/{job_id}/logview/init", response_class=HTMLResponse)
async def job_logview_init(request: Request, job_id: str, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    """Auto-loaded (hx-trigger=load) by the Validation page's 'Actual vs
    Predicted' card — computing the train/test/blind well split needs a DB
    session, which the render path that puts this card on screen
    (_revisit_validation/poll/cancel_run/step_validation) doesn't carry, so
    this is fetched separately instead of threading `db` through all of them
    (same auto-load convention as Variable distribution / Correlation)."""
    # Buscamos el contexto del job para saber con qué config se entrenó
    ctx = _RUN_CTX.get(job_id)
    if ctx is None:
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">Not available — re-run validation.</p>')
    # Calculamos qué pozos cayeron en train/test/blind con esa config, y elegimos el dataset
    # por defecto a mostrar (el primero no vacío)
    split = _split_well_options(db, _cfg(ctx["state"]))
    default_dataset = "train" if split["train"] else ("test" if split["test"] else "blind")
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_logview_card_body.html",
                                      {"request": request, "job_id": job_id, "split": split, "default_dataset": default_dataset})


@router.get("/job/{job_id}/logview/wells", response_class=HTMLResponse)
async def job_logview_wells(request: Request, job_id: str, dataset: str = "train",
                            db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    ctx = _RUN_CTX.get(job_id)
    if ctx is None:
        return HTMLResponse('<div></div>')
    # Devolvemos la lista de pozos del dataset elegido (train/test/blind) para el selector
    split = _split_well_options(db, _cfg(ctx["state"]))
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_logview_wells.html",
                                      {"request": request, "wells": split.get(dataset, [])})


@router.post("/job/{job_id}/logview/open", response_class=HTMLResponse)
async def job_logview_open(request: Request, job_id: str, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await request.form()
    well_id = int(form.get("well_id")) if (form.get("well_id") or "").isdigit() else None
    pipe = _PIPELINE_STORE.get(job_id)
    if pipe is None or well_id is None:
        # Sin pipeline (job expirado) o sin pozo elegido, no hay nada que mostrar
        return HTMLResponse('<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">Pick a well (or the model isn\'t available anymore — re-run validation).</p></div>')
    ctx = _RUN_CTX.get(job_id) or {}
    st = ctx.get("state") or {}
    # Calculamos las filas actual-vs-predicho para ese pozo, respetando el rango de entrenamiento
    view = _logview_records(db, well_id, pipe, bit_sizes=st.get("bit_sizes"),
                            depth_range=st.get("depth_range"), date_range=st.get("date_range"))
    return templates.TemplateResponse(request, "partials/welllog_view.html",
                                      {"request": request, "has_data": view is not None, **(view or {})})


# --------------------------------------------------------------------------- #
# Save experiment
# --------------------------------------------------------------------------- #
@router.post("/save", response_class=HTMLResponse)
async def save_experiment(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    form = await request.form()
    # Leemos el token del job de validación a guardar, el nombre y la descripción del experimento
    token = form.get("result_token") or ""
    name = (form.get("name") or "").strip() or "ROP experiment"
    desc = (form.get("description") or "").strip() or None
    # The browser may still show a perfectly valid Save form for a run whose
    # in-process stores were wiped by a server restart — the persisted copy
    # (rop_run_store) is the source of truth, so revive before giving up.
    _revive_job(db, token, "validation")
    job = rop_jobs.get(token)
    ctx = _RUN_CTX.get(token, {})
    state = ctx.get("state", {})
    pipe = _PIPELINE_STORE.get(token)
    if pipe is None and job.get("status") == "done":
        # Recuperamos el pipeline directamente del resultado del job si no estaba en el store
        pipe = ((job.get("result") or {}).get("pipeline"))
    if pipe is None or job.get("status") != "done":
        return HTMLResponse('<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">Result expired — re-run validation, then save.</p></div>')
    if not state.get("well_ids"):
        # ctx evicted (very long session) or revive returned a stateless stub —
        # refusing beats silently writing a corrupt experiment row with an
        # empty config/model_key.
        return HTMLResponse('<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">'
                            'Session context for this run is gone — revisit the Validation step (breadcrumb), then save again.</p></div>')
    vres = (job.get("result") or {}).get("result", {})
    # Everything final_validation() actually returns, not a hand-picked subset —
    # perm_importance/shap/plots/drift are needed to fully redisplay Validation
    # from a saved row later with no live job behind it (see /experiments/{id}/load).
    stored_metrics = {k: vres.get(k) for k in
                      ("train", "test", "blind", "pi_level", "pi_halfwidth", "split_grouped",
                       "n_invalid", "n_invalid_blind", "drift", "plots", "scatter", "residuals",
                       "perm_importance", "shap", "error_bands", "learning_curve", "validation_curve")}
    # The FULL wizard state, not a hand-picked subset — a prior version of this
    # dropped `field`, completeness filters, and (worst) `log_target`, so a saved
    # experiment couldn't even tell you whether it predicted log(ROP) or raw ROP.
    config = dict(state)
    config["params"] = (job.get("result") or {}).get("ds_info", {}).get("used_params")

    # Best-effort pre-selection/HPO detail, if those jobs are still in the store
    # (revived from the DB when possible) — lets a later /load show more than
    # just the final numbers. None per-key when that step was skipped (e.g.
    # "Skip → Validation") or genuinely lost.
    # Definimos un helper para recuperar (reviviendo si hace falta) el resultado de un job
    # anterior (pre-selección u HPO) referenciado en el estado
    def _job_result(job_id_key, kind):
        jid = state.get(job_id_key)
        if not jid:
            return None
        _revive_job(db, jid, kind)
        j = rop_jobs.get(jid)
        return j["result"] if j.get("status") == "done" else None

    pre_res = _job_result("preselect_job_id", "preselect")
    hpo_res = _job_result("hpo_job_id", "hpo")
    # Armamos el detalle de entrenamiento (ranking de pre-selección + historial de HPO), si existen
    training_detail = {
        "ranked": pre_res.get("ranked") if pre_res else None,
        "preselect_ds_info": pre_res.get("ds_info") if pre_res else None,
        "hpo_history": hpo_res.get("history") if hpo_res else None,
        # .get(), not [..]: an experiment loaded from an older row can seed an
        # HPO job with history but without the tuned-vs-default keys — re-saving
        # it under a new name used to KeyError here.
        "hpo_tuned_vs_default": {k: hpo_res.get(k) for k in
                                 ("tuned_metrics", "default_metrics", "tuned_train_metrics", "default_train_metrics")}
                                if hpo_res else None,
    }

    # Persistimos el experimento (config, métricas, pipeline entrenado y detalle) en la BD
    exp = rop_experiments.save(db, name=name, description=desc, model_key=state.get("chosen_model", ""),
                               config=config, metrics=stored_metrics, pipeline=pipe,
                               training_detail=training_detail, created_by=getattr(current_user, "id", None))
    return HTMLResponse(
        f'<div class="card p-4"><p style="color:#22c55e;">Saved as model #{exp.id} — “{exp.name}”.</p>'
        f'<div style="margin-top:10px; display:flex; gap:8px;">'
        f'<a href="/analytics/rop-prediction/experiments" class="btn btn-secondary btn-sm">View saved models</a>'
        f'<a href="/analytics/rop-prediction/experiments/{exp.id}/whatif" class="btn btn-primary btn-sm">What-if &rarr;</a>'
        f'</div></div>')


# --------------------------------------------------------------------------- #
# Saved models + inference + what-if
# --------------------------------------------------------------------------- #
# Armamos el contexto común de las páginas fuera del wizard (listado de experimentos, predicción,
# what-if) que también necesitan el menú lateral de Analytics
def _analytics_ctx(request, current_user, **extra):
    ctx = {"request": request, "current_user": current_user, "submodules": SUBMODULES,
           "active": "rop-prediction"}
    ctx.update(extra)
    return ctx


@router.get("/experiments", response_class=HTMLResponse)
async def experiments(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Listamos todos los experimentos (modelos) guardados
    exps = rop_experiments.list_experiments(db)
    return templates.TemplateResponse(request, "ops/pages/analytics/rop_pred_experiments.html",
                                      _analytics_ctx(request, current_user, experiments=exps,
                                                     model_labels={k: v["label"] for k, v in rop_ml.MODELS.items()}))


@router.get("/experiments/{exp_id}/load", response_class=HTMLResponse)
async def load_experiment(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Reopen a saved experiment as an editable wizard, landing on Validation
    with its persisted results. Adopts the saved result into the SAME job-store
    redisplay path a live run uses (rop_jobs.seed_done + a synthetic _RUN_CTX
    entry) — see _revisit_validation/_revisit_preselect/_revisit_hpo — so no
    separate rendering code is needed here, and breadcrumb navigation back to
    Pre-selection/Hyperparameters works for free (showing exp.training_detail
    when it was captured, an honest 'not available' card when it wasn't)."""
    from starlette.datastructures import FormData
    exp = rop_experiments.get(db, exp_id)
    if exp is None:
        return HTMLResponse('<div class="card p-4">Experiment not found.</div>')

    # Old experiments (saved before this feature) only have the hand-picked
    # config subset — start from full defaults so nothing's missing, then
    # overlay whatever the saved config actually has.
    # Reconstruimos el estado partiendo de los defaults y superponiendo la config guardada
    state = _state(FormData([]))
    state.update(exp.config or {})
    state["chosen_model"] = exp.model_key or state.get("chosen_model", "")
    # A saved case by definition ran the whole pipeline, so every step's
    # preview should redisplay when its step is revisited — force the
    # preview-was-calculated flags on, covering cases saved before the flags
    # existed too (their stored config simply lacks the keys).
    for k in ("outlier_preview_done", "scaling_preview_done", "pca_preview_done", "dist_done", "corr_done"):
        state[k] = True

    pipe = rop_experiments.load_pipeline(exp)
    detail = exp.training_detail or {}
    metrics = exp.metrics or {}

    # Definimos un helper para estimar cuántas filas tenía un split (train/test), a partir
    # del tamaño de la muestra de puntos guardada para el scatter
    def _n_plot_rows(split):
        # Best-effort row counts for older experiments whose ds_info was never
        # stored — the plots payload carries a (capped) sample per split; showing
        # its length beats the literal blank "Train · Test rows" the
        # validation header used to render for loaded cases.
        pts = ((metrics.get("plots") or {}).get(split) or {}).get("scatter")
        return len(pts) if pts else None

    # Re-sembramos un job "de validación" sintético con el resultado guardado, para poder
    # reusar el mismo camino de redisplay (_revisit_validation) que un job en vivo
    vjob = f"exp{exp.id}-validation"
    vresult = {"result": metrics, "pipeline": pipe, "ds_info": {
        "n_features": len(state.get("features") or []),
        "blind_well_id": state.get("blind_well_id"),
        "used_params": (exp.config or {}).get("params"),
        "n_train": _n_plot_rows("train"), "n_test": _n_plot_rows("test"),
    }}
    rop_jobs.seed_done(vjob, vresult)
    state["validation_job_id"] = vjob
    if pipe is not None:
        _PIPELINE_STORE[vjob] = pipe
    seeded = [(vjob, "validation", vresult)]

    if detail.get("ranked") is not None:
        # Si se guardó el ranking de pre-selección, también lo re-sembramos como job sintético
        pjob = f"exp{exp.id}-preselect"
        presult = {"ranked": detail["ranked"], "ds_info": detail.get("preselect_ds_info") or {}}
        rop_jobs.seed_done(pjob, presult)
        state["preselect_job_id"] = pjob
        _RUN_CTX[pjob] = {"kind": "preselect", "step": "preselect", "state": state, "msg": ""}
        seeded.append((pjob, "preselect", presult))

    if detail.get("hpo_history") is not None:
        # Si se guardó el historial de HPO, también lo re-sembramos como job sintético
        hjob = f"exp{exp.id}-hpo"
        try:
            best_params = json.loads(state.get("best_params") or "{}")
        except (TypeError, json.JSONDecodeError):
            best_params = {}
        hpo_result = {"history": detail["hpo_history"], "best_params": best_params, "best_r2": None}
        hpo_result.update(detail.get("hpo_tuned_vs_default") or {})
        rop_jobs.seed_done(hjob, hpo_result)
        state["hpo_job_id"] = hjob
        _RUN_CTX[hjob] = {"kind": "hpo", "step": "hpo", "state": state, "msg": ""}
        seeded.append((hjob, "hpo", hpo_result))

    _RUN_CTX[vjob] = {"kind": "validation", "step": "validation", "state": state, "msg": ""}

    # Persist the seeded jobs too: without this, a server restart while the
    # loaded case is open leaves the browser holding exp{N}-* job ids that
    # _revive_job can't find anywhere, and every step shows "not run yet"
    # until the user re-loads from /experiments.
    # Persistimos también los jobs sembrados, para que sobrevivan a un reinicio del servidor
    for jid, kind, res in seeded:
        try:
            rop_run_store.save(db, jid, kind, state, res)
        except Exception:
            logger.exception("Failed to persist seeded job %s for experiment %s", jid, exp.id)

    # Aterrizamos en el paso de Validación, mostrando el resultado ya sembrado
    return _revisit_validation(request, current_user, state, db, full=True)


@router.post("/experiments/{exp_id}/delete", response_class=HTMLResponse)
async def delete_experiment(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Eliminamos el experimento y devolvemos el listado actualizado
    rop_experiments.delete(db, exp_id)
    exps = rop_experiments.list_experiments(db)
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_experiments_list.html",
                                      _analytics_ctx(request, current_user, experiments=exps,
                                                     model_labels={k: v["label"] for k, v in rop_ml.MODELS.items()}))


# Devolvemos los pozos que sí tienen datos (n_rows > 0), para los selectores de predicción/logview
def _well_options(db: Session) -> list[dict]:
    summaries = svc.well_summaries()
    out = []
    for w in WellRepository(db).get_all(skip=0, limit=2000):
        if summaries.get(w.id, {}).get("n_rows"):
            out.append({"id": w.id, "name": w.well_name})
    return out


# --------------------------------------------------------------------------- #
# Actual-vs-predicted log view — reuses the Well Logs module's multi-track
# viewer (partials/welllog_view.html + static/js/welllog.js) as-is, fed with
# {depth, actual_rop, predicted_rop} rows instead of raw sensor channels.
# --------------------------------------------------------------------------- #
def _saved_cfg(config: dict) -> dict:
    """The `_cfg()` training projection of a SAVED experiment's stored state.
    Passing `exp.config` (the full wizard state) straight into build_dataset()
    had two real consequences: the cache key never matched the training-time
    key (forcing a slow full rebuild), and — worse — the full state has no
    `outlier_params` dict (only the individual outlier_* fields), so the
    rebuild silently ran with DEFAULT outlier parameters, which can change the
    reconstructed train/test membership vs. what was actually trained."""
    from starlette.datastructures import FormData
    # Partimos de los defaults y superponemos la config guardada, para reconstruir la MISMA
    # clave de entrenamiento (_cfg) que se usó al entrenar
    base = _state(FormData([]))
    base.update(config or {})
    return _cfg(base)


def _split_well_options(db: Session, cfg: dict) -> dict:
    """{'train': [{id,name}...], 'test': [...], 'blind': [...], 'grouped': bool}
    — which wells ended up in each split for this exact config. Deterministic
    (fixed seed), so this reproduces build_dataset's own split rather than
    tracking it separately; cached the same way any other build_dataset(cfg)
    call is. `grouped` is False when there were too few wells for a by-well
    split — train/test then share wells (row-level split) and the UI should
    say so instead of implying disjoint well lists."""
    # Reconstruimos el dataset (determinístico, misma semilla) para recuperar exactamente
    # qué pozos cayeron en cada split
    ds = rop_ml.build_dataset(db, cfg)
    names = {w.id: w.well_name for w in WellRepository(db).get_all(skip=0, limit=2000)}

    # Definimos un helper que convierte una lista de ids de pozo en opciones {id, name} ordenadas
    def _opts(ids):
        return sorted(({"id": int(i), "name": names.get(int(i), f"Well {int(i)}")} for i in set(ids)),
                      key=lambda w: w["name"].lower())

    return {
        "train": _opts(ds.groups_train.tolist()) if ds.groups_train is not None else [],
        "test": _opts(ds.groups_test.tolist()) if ds.groups_test is not None else [],
        "blind": _opts([ds.blind_well_id]) if ds.blind_well_id is not None else [],
        "grouped": ds.split_grouped,
    }


def _logview_records(db: Session, well_id: int, pipe: dict, bit_sizes=None,
                     depth_range=None, date_range=None):
    """Depth-sorted actual-vs-predicted ROP rows for one well, scored with a
    fitted pipeline — same well-fetch/filter logic as predict_score(), just
    keeping the depth column and sorting by it instead of random-sampling for
    a scatter. Returns None if the well can't be scored (missing features /
    too few valid rows), same failure signal predict_score() already uses.

    `bit_sizes`/`depth_range`/`date_range` restrict to the regime the model
    was actually trained on — it has no validity outside it, so intervals
    outside the training window are excluded rather than (mis)scored."""
    import pandas as pd
    from app.services.rop_prediction import PLAUSIBLE_RANGES, TARGET

    feats = pipe["raw_features"]
    # Traemos los datos del pozo con las mismas restricciones (bit/profundidad/fecha) que el entrenamiento
    dfw = rop_ml.well_frame(db, well_id, 2_000_000, bit_sizes=bit_sizes,
                            depth_range=depth_range, date_range=date_range)
    if dfw is None or not all(c in dfw.columns for c in feats + [TARGET]):
        # Al pozo le faltan columnas necesarias — no se puede scorear
        return None
    depth_key = next((c for c in ("bit_depth_feet", "hole_depth_feet") if c in dfw.columns), None)
    if depth_key is None:
        return None
    # Dedupe: a depth channel can itself be a selected model feature
    # (bit_depth_feet is a Context candidate) — repeating it made
    # dfw[cols] carry a duplicated column label and sort_values() raise
    # "column label is not unique" (a reproducible 500).
    cols = feats + [TARGET] + ([depth_key] if depth_key not in feats else [])
    ranges = {c: PLAUSIBLE_RANGES[c] for c in feats + [TARGET] if c in PLAUSIBLE_RANGES}
    # Filtramos filas válidas (sin NaN, target>0, dentro del rango físico plausible)
    sub = dfw[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=cols)
    sub = sub[sub[TARGET] > 0]
    for c, (lo, hi) in ranges.items():
        sub = sub[(sub[c] >= lo) & (sub[c] <= hi)]
    if len(sub) < 5:
        return None
    # Ordenamos por profundidad para que el log view se vea como una curva continua
    sub = sub.sort_values(depth_key)
    X = sub[feats].to_numpy(dtype=float)
    # Scoreamos con el pipeline entrenado y armamos las filas actual/predicho/residual
    yp, _half = rop_ml.predict_pipeline(pipe, X)
    y = sub[TARGET].to_numpy()
    records = [{depth_key: float(d), "actual_rop": float(a), "predicted_rop": float(p), "residual_rop": float(a - p)}
              for d, a, p in zip(sub[depth_key].to_numpy(), y, yp)]
    return {
        "records": records, "depth_key": depth_key,
        "available_parameters": ["actual_rop", "predicted_rop", "residual_rop"],
        "param_labels": {"actual_rop": "Actual ROP (ft/hr)", "predicted_rop": "Predicted ROP (ft/hr)",
                         "residual_rop": "Residual — actual minus predicted (ft/hr)"},
        # Pre-populate the two tracks the user actually wants to see — actual
        # (continuous line) overlaid with predicted (scatter points, so a dense
        # curve underneath is still readable) in Track 1, residual in Track 2 —
        # instead of the blank Well-Logs-style "+ Add Track" starting point.
        # Still a full WellLogView underneath, so add-track/add-parameter/zoom/
        # log-scale/export all keep working exactly as in /logs if the user
        # wants to customize further.
        "initial_tracks": [
            # same_scale: actual and predicted are both ft/hr — one shared axis so
            # the two curves are visually comparable instead of each being
            # independently stretched to fill the track width.
            {"name": "ROP", "parameters": ["actual_rop", "predicted_rop"], "same_scale": True},
            {"name": "Residual", "parameters": ["residual_rop"]},
        ],
        "param_colors": {"actual_rop": "#3B82F6", "predicted_rop": "#EF4444", "residual_rop": "#F59E0B"},
        "param_styles": {"predicted_rop": "scatter"},
    }


@router.get("/experiments/{exp_id}/predict", response_class=HTMLResponse)
async def predict_page(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    exp = rop_experiments.get(db, exp_id)
    if exp is None:
        return HTMLResponse('<div class="card p-4">Experiment not found.</div>')
    return templates.TemplateResponse(request, "ops/pages/analytics/rop_pred_predict.html",
                                      _analytics_ctx(request, current_user, exp=exp, wells=_well_options(db),
                                                     model_label=rop_ml.MODELS.get(exp.model_key, {}).get("label", exp.model_key)))


@router.post("/experiments/{exp_id}/score", response_class=HTMLResponse)
async def predict_score(request: Request, exp_id: int, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    import pandas as pd
    from app.services.rop_prediction import PLAUSIBLE_RANGES, TARGET
    form = await request.form()
    well_id = int(form.get("well_id")) if (form.get("well_id") or "").isdigit() else None
    exp = rop_experiments.get(db, exp_id)
    pipe = rop_experiments.load_pipeline(exp) if exp else None
    if pipe is None or well_id is None:
        return HTMLResponse('<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">Pick a well (or the model artifact is missing).</p></div>')

    feats = pipe["raw_features"]
    # Filtramos las mismas columnas y rangos físicos plausibles que se usaron al entrenar
    cols = feats + [TARGET]
    ranges = {c: PLAUSIBLE_RANGES[c] for c in cols if c in PLAUSIBLE_RANGES}
    # No row cap — a well can run past 60k rows (see build_dataset's own
    # per_well=2_000_000 sentinel); an 8000-row cap here silently scored only the
    # shallowest fraction of any bigger well, same class of bug as the sample_cap
    # / 60-well / 20-well caps already removed elsewhere in this module.
    # bit_sizes/depth_range/date_range restrict to the regime the model was
    # trained on — scoring rows outside that window would be extrapolating
    # outside its validity.
    cfgd = exp.config or {}
    dfw = rop_ml.well_frame(db, well_id, 2_000_000, bit_sizes=cfgd.get("bit_sizes"),
                            depth_range=cfgd.get("depth_range"), date_range=cfgd.get("date_range"))  # raw + engineered
    if dfw is None or not all(c in dfw.columns for c in cols):
        return HTMLResponse('<div class="card p-4">This well is missing some of the model’s features.</div>')
    sub = dfw[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=cols)
    sub = sub[sub[TARGET] > 0]
    for c, (lo, hi) in ranges.items():
        sub = sub[(sub[c] >= lo) & (sub[c] <= hi)]
    if len(sub) < 5:
        return HTMLResponse('<div class="card p-4">Not enough valid rows for this well.</div>')
    X = sub[feats].to_numpy(dtype=float)
    y = sub[TARGET].to_numpy(dtype=float)
    # Scoreamos con el pipeline entrenado y calculamos métricas + cobertura del intervalo de predicción
    yp, half = rop_ml.predict_pipeline(pipe, X)
    m = rop_ml.metrics(y, yp)
    coverage = float(np.mean(np.abs(y - yp) <= half) * 100)
    # Muestreamos hasta 1200 puntos para el scatter actual-vs-predicho
    rng = np.random.RandomState(1)
    idx = rng.permutation(len(yp))[:1200]
    # {x, y} to match the SAME shape/convention DrillingCharts.renderScatterChart
    # already uses for every other predicted-vs-actual plot in this module
    # (rop_pred_validation.html's train/test/blind scatters).
    scatter = [{"x": float(y[i]), "y": float(yp[i])} for i in idx]
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_score.html",
                                      _analytics_ctx(request, current_user, exp=exp, metrics=m,
                                                     coverage=coverage, half=float(half[0]) if len(half) else 0.0,
                                                     pi_level=pipe.get("pi_level", 0.9),
                                                     n_rows=len(y), scatter=scatter))


@router.get("/experiments/{exp_id}/logview", response_class=HTMLResponse)
async def logview_page(request: Request, exp_id: int, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    exp = rop_experiments.get(db, exp_id)
    if exp is None:
        return HTMLResponse('<div class="card p-4">Experiment not found.</div>')
    # Recalculamos el split train/test/blind del experimento guardado y elegimos el dataset por defecto
    split = _split_well_options(db, _saved_cfg(exp.config))
    default_dataset = "train" if split["train"] else ("test" if split["test"] else "blind")
    return templates.TemplateResponse(request, "ops/pages/analytics/rop_pred_logview.html",
                                      _analytics_ctx(request, current_user, exp=exp, split=split,
                                                     default_dataset=default_dataset,
                                                     wells=split.get(default_dataset, []),
                                                     model_label=rop_ml.MODELS.get(exp.model_key, {}).get("label", exp.model_key)))


@router.get("/experiments/{exp_id}/logview/wells", response_class=HTMLResponse)
async def logview_wells(request: Request, exp_id: int, dataset: str = "train",
                        db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    exp = rop_experiments.get(db, exp_id)
    if exp is None:
        return HTMLResponse('<div></div>')
    split = _split_well_options(db, _saved_cfg(exp.config))
    return templates.TemplateResponse(request, "ops/partials/analytics/rop_pred_logview_wells.html",
                                      {"request": request, "wells": split.get(dataset, [])})


@router.post("/experiments/{exp_id}/logview/open", response_class=HTMLResponse)
async def logview_open(request: Request, exp_id: int, db: Session = Depends(get_depth_db), current_user: User = Depends(get_current_user_web)):
    form = await request.form()
    well_id = int(form.get("well_id")) if (form.get("well_id") or "").isdigit() else None
    exp = rop_experiments.get(db, exp_id)
    pipe = rop_experiments.load_pipeline(exp) if exp else None
    if pipe is None or well_id is None:
        return HTMLResponse('<div class="card p-4"><p style="color:var(--color-danger,#ef4444);">Pick a well (or the model artifact is missing).</p></div>')
    cfgd = exp.config or {}
    # Calculamos las filas actual-vs-predicho para el pozo elegido, con el mismo rango de entrenamiento
    view = _logview_records(db, well_id, pipe, bit_sizes=cfgd.get("bit_sizes"),
                            depth_range=cfgd.get("depth_range"), date_range=cfgd.get("date_range"))
    return templates.TemplateResponse(request, "partials/welllog_view.html",
                                      {"request": request, "has_data": view is not None, **(view or {})})


@router.get("/experiments/{exp_id}/whatif", response_class=HTMLResponse)
async def whatif_page(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    exp = rop_experiments.get(db, exp_id)
    pipe = rop_experiments.load_pipeline(exp) if exp else None
    if pipe is None:
        return HTMLResponse('<div class="card p-4">Experiment/model artifact not found.</div>')
    stats, roles = pipe.get("raw_stats", {}), pipe.get("roles", {})
    controls, fixed = [], []
    # Separamos las features en "controlables" (el usuario las mueve) y "fijas" (contexto/derivadas)
    for f in pipe["raw_features"]:
        st = stats.get(f, {"median": 0.0, "min": 0.0, "max": 1.0})
        row = {"feature": f, "label": svc.feature_label(f), **st, "role": roles.get(f, "response")}
        (controls if roles.get(f) == "controllable" else fixed).append(row)
    controls_by_feature = {c["feature"]: {"min": c["min"], "max": c["max"]} for c in controls}
    return templates.TemplateResponse(request, "ops/pages/analytics/rop_pred_whatif.html",
                                      _analytics_ctx(request, current_user, exp=exp, controls=controls, fixed=fixed,
                                                     controls_by_feature=controls_by_feature))


@router.post("/experiments/{exp_id}/whatif", response_class=HTMLResponse)
async def whatif_compute(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    exp = rop_experiments.get(db, exp_id)
    pipe = rop_experiments.load_pipeline(exp) if exp else None
    if pipe is None:
        return HTMLResponse('<div class="card p-4">Model artifact not found.</div>')
    form = await request.form()
    stats = pipe.get("raw_stats", {})
    row = []
    # Armamos la fila de entrada con los valores del form (o la mediana histórica si falta alguno)
    for f in pipe["raw_features"]:
        try:
            row.append(float(form.get(f)))
        except (TypeError, ValueError):
            row.append(stats.get(f, {}).get("median", 0.0))
    # Predecimos con el pipeline entrenado y calculamos el intervalo de predicción
    yp, half = rop_ml.predict_pipeline(pipe, np.array([row], dtype=float))
    pred, h = float(yp[0]), float(half[0])
    lvl = int(pipe.get("pi_level", 0.9) * 100)
    return HTMLResponse(
        f'<div class="card p-4" style="text-align:center;">'
        f'<div class="text-sm" style="color:var(--color-text-muted);">Predicted ROP</div>'
        f'<div style="font-size:34px; font-weight:700; color:var(--color-primary);">{pred:.1f} <span style="font-size:16px; color:var(--color-text-muted);">ft/hr</span></div>'
        f'<div class="text-sm" style="color:var(--color-text-muted);">{lvl}% interval: {max(0.0, pred - h):.1f} – {pred + h:.1f} ft/hr (±{h:.1f})</div>'
        f'</div>')


@router.post("/experiments/{exp_id}/whatif/sweep", response_class=HTMLResponse)
async def whatif_sweep(request: Request, exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Parameter sweep ("founder point") — freezes every OTHER feature at
    whatever the What-if form currently has them set to, and sweeps one
    controllable feature across a range, plotting the predicted ROP curve.
    No refit: repeated predict_pipeline() calls over a grid, reusing the exact
    same fitted pipeline and raw_stats the single-prediction card already uses."""
    exp = rop_experiments.get(db, exp_id)
    pipe = rop_experiments.load_pipeline(exp) if exp else None
    if pipe is None:
        return HTMLResponse('<div class="card p-4">Model artifact not found.</div>')
    form = await request.form()
    stats = pipe.get("raw_stats", {})
    feats = pipe["raw_features"]

    # Congelamos cada feature en el valor actual del form (o su mediana histórica si falta)
    base_values = {}
    for f in feats:
        try:
            base_values[f] = float(form.get(f))
        except (TypeError, ValueError):
            base_values[f] = stats.get(f, {}).get("median", 0.0)

    # Leemos qué variable barrer (sweep)
    sweep_feature = form.get("sweep_feature") or ""
    if sweep_feature not in feats:
        return HTMLResponse('<p class="text-sm" style="color:var(--color-text-muted);">Pick a variable to sweep.</p>')

    # Definimos un helper local para leer un float del form
    def _num(key, default):
        try:
            return float(form.get(key))
        except (TypeError, ValueError):
            return default

    # Resolvemos el rango del barrido (del form, o los límites históricos de la variable)
    st = stats.get(sweep_feature, {})
    lo = _num("sweep_min", st.get("min", base_values[sweep_feature] - 1.0))
    hi = _num("sweep_max", st.get("max", base_values[sweep_feature] + 1.0))
    if hi <= lo:
        return HTMLResponse('<p class="text-sm" style="color:var(--color-danger,#ef4444);">Sweep max must be greater than min.</p>')

    # Si se pidió una variable de comparación, armamos sus valores representativos (min/mediana/max)
    compare_feature = form.get("compare_feature") or ""
    compare_values, compare_label = None, None
    if compare_feature and compare_feature in feats and compare_feature != sweep_feature:
        cst = stats.get(compare_feature, {})
        compare_values = sorted({v for v in (cst.get("min"), cst.get("median"), cst.get("max")) if v is not None})
        compare_label = svc.feature_label(compare_feature)

    # Corremos el barrido (predicciones repetidas sobre la grilla) y devolvemos el gráfico
    result = rop_ml.param_sweep(pipe, base_values, sweep_feature, lo, hi,
                                compare_feature=compare_feature or None, compare_values=compare_values)
    return templates.TemplateResponse(
        request, "ops/partials/analytics/rop_pred_sweep_chart.html",
        {"request": request, "result": result, "feature_label": svc.feature_label(sweep_feature),
         "compare_label": compare_label})
