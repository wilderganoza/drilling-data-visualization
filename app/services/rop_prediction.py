"""ROP Prediction — service layer.

Trains ML models (XGBoost, LightGBM, sklearn ensembles, …) to predict rate of
penetration (ROP) from drilling parameters, pooling rows across many wells. This
module owns the data-facing helpers; the wizard/routes live in
``app/ops/web/rop_prediction.py`` and reuse the Outlier-Detection preprocessing
(scaling / PCA / anomaly removal).

Step 1 of the wizard needs, per well: how complete the model's variables are, when
drilling started and the final depth — so the user can pick wells worth training on.
Computing that means a GROUP BY over well_data (~5M rows), so the result is cached
in-process with a short TTL (same pattern as db_manager.time_well_ids()).
"""
from __future__ import annotations

# Importamos time (con alias para no chocar con parámetros llamados "time") para medir el TTL de los cachés
import time as _time
# Importamos los tipos para anotar los cachés y los retornos
from typing import Any, Dict, List

# Importamos text para construir las consultas SQL crudas contra well_data
from sqlalchemy import text

# Importamos get_tracked_parameters, la lista de canales de sensor que seguimos
from app.constants.parameters import get_tracked_parameters
# Importamos get_logger para registrar errores de las consultas
from app.core.logging import get_logger
# Importamos db_manager para conectarnos directamente al engine de la base de datos de sensores
from app.db.session import db_manager
# Importamos _get_label de exports para reutilizar el mismo texto legible que usan las exportaciones
from app.services.exports import _get_label

# Nota: los imports de app.services.rop_features (en feature_role/feature_candidates/feature_label)
# quedan dentro de la función porque SÍ hay un ciclo real: rop_features.py importa de vuelta
# CONTEXT, PLAUSIBLE_RANGES y raw_candidates desde este mismo módulo (app/services/rop_prediction.py).
# Subirlos rompería la importación en un sentido o el otro.
logger = get_logger(__name__)

# Definimos la variable que el modelo predice.
# The variable the model predicts.
TARGET = "rate_of_penetration_ft_per_hr"

# Definimos las columnas que son el target disfrazado (filtrarían información hacia las features).
# Columns that ARE the target in disguise (would leak it into the features).
_LEAKAGE = {"on_bottom_rop_ft_per_hr", "time_of_penetration_min_per_ft"}

# Not literal same-row leakage (doesn't use THIS row's ROP), but close enough to
# ban outright: on_bottom_hours_hrs is a cumulative on-bottom-drilling-time
# counter, i.e. roughly cumsum(depth_increment / ROP) — a near-deterministic
# proxy for the well's entire ROP history up to that point. A model can partly
# "invert" it (or its lag/moving-avg/std variants) to recover local ROP and
# inflate R² without learning anything causal from WOB/RPM. Excluded from
# candidates entirely (like _LEAKAGE) rather than just left unchecked, so
# neither it nor its lag/ma/sd variants can be picked — including via "Select
# all". circulating_hours_hrs is a weaker version of the same pattern (doesn't
# require the bit to be advancing) and is left selectable, just not recommended.
_MONOTONIC_PROXY = {"on_bottom_hours_hrs"}

# Definimos los roles de las features — son solo etiquetas informativas; CUALQUIER variable se puede seleccionar.
# Feature roles — informational labels only; ANY variable can be selected.
# CONTROLLABLE = parameters the driller sets. RESPONSE = consequences of drilling
# (torque, pressures, hook load) — raise R² but aren't actionable. CONTEXT =
# where/what is being drilled. Unlisted raw channels default to "response".
# (The default-checked set is RECOMMENDED_DEFAULT below, independent of role.)
CONTROLLABLE = {
    "weight_on_bit_klbs", "rotary_rpm_rpm", "motor_rpm_rpm",
    "pump_1_strokes_min_spm", "pump_2_strokes_min_spm",
    "total_pump_output_gal_per_min", "totalpumpdisplacement_barrels",
}
CONTEXT = {"bit_depth_feet", "hole_depth_feet", "block_height_feet", "bit_size"}

ROLE_LABELS = {"controllable": "Controllable", "context": "Context",
               "response": "Response", "computed": "Computed"}


def feature_role(col: str) -> str:
    # Importamos aquí (no arriba) porque rop_features importa de vuelta CONTEXT/PLAUSIBLE_RANGES/
    # raw_candidates de este módulo — subir este import crearía un ciclo real entre ambos archivos.
    from app.services.rop_features import ENG_ROLE
    # Preferimos el rol declarado explícitamente para features de ingeniería
    if col in ENG_ROLE:
        return ENG_ROLE[col]
    if col in CONTROLLABLE:
        return "controllable"
    if col in CONTEXT:
        return "context"
    # Por defecto tratamos cualquier canal no listado como "response"
    return "response"


def raw_candidates() -> List[str]:
    """Raw sensor channels offered as predictors (target, leakage, and the
    on_bottom_hours ROP-history proxy removed — see _LEAKAGE/_MONOTONIC_PROXY)."""
    # Filtramos el target, las columnas de leakage y el proxy monotónico de la lista de canales seguidos
    return [p for p in get_tracked_parameters()
            if p != TARGET and p not in _LEAKAGE and p not in _MONOTONIC_PROXY]


def feature_candidates() -> List[str]:
    """Raw channels + the engineered features derivable from them."""
    # Importamos aquí por el mismo ciclo real explicado en feature_role() — rop_features
    # importa de vuelta símbolos de este módulo.
    from app.services.rop_features import available_engineered
    # Combinamos los canales crudos con las features de ingeniería derivables de ellos
    raw = raw_candidates()
    eng = available_engineered(get_tracked_parameters())
    return raw + eng


def feature_label(col: str) -> str:
    # Importamos aquí por el mismo ciclo real explicado en feature_role() — rop_features
    # importa de vuelta símbolos de este módulo.
    from app.services.rop_features import ENG_LABEL
    # Preferimos la etiqueta declarada explícitamente para features de ingeniería
    if col in ENG_LABEL:
        return ENG_LABEL[col]
    try:
        # Reutilizamos la misma etiqueta legible que usan las exportaciones para canales crudos
        return _get_label(col)
    except Exception:
        # Si no hay etiqueta conocida, generamos una a partir del nombre de la columna
        return col.replace("_", " ").title()


# Default-recommended = exactly the variables from the field team's requested list
# that we actually have (raw) or can compute (engineered), plus one lagged response
# variable (see below). Everything else is still selectable, just not pre-checked.
#
# RAW response variables are never recommended by default: they're consequences of
# drilling (torque, pressures, hook load), not driller-set controls, so predicting
# from them raw breaks the controllable->ROP counterfactual an optimizer needs (it
# can't supply a future response value as an input to search over). A LAGGED
# response variable is different — it's already-observed history at decision time,
# not a real-time reading, so it's safe for the optimization use case. That's the
# criterion: differential_pressure_psi_lag20 (the response to WOB/torque with a
# downhole motor) is recommended lagged; its raw/unlagged form is not, and is left
# selectable-but-unchecked along with every other lag/response combination — see
# rop_features.py's _LAG_CANDIDATES for the full generated set.
#
# bit_rpm_total is also deliberately left out here (still selectable, just not
# pre-checked): bit_rpm_total = rotary_rpm + gpm*rev/gal, i.e. perfect
# collinearity with two already-recommended variables (keep rotary/gpm free, let
# the model imply bit RPM). on_bottom_hours_hrs isn't in this set for a
# different reason — it isn't a candidate at all anymore, see _MONOTONIC_PROXY.
RECOMMENDED_DEFAULT = {
    # raw, available
    "weight_on_bit_klbs", "rotary_rpm_rpm", "total_pump_output_gal_per_min",
    "hole_depth_feet", "bit_size",
    # engineered, computable from what we have
    "cum_work", "wob_ma20", "rpm_ma20", "gpm_ma20",
    "wob_sd20", "rpm_sd20", "gpm_sd20", "sliding_frac",
    # lagged response — see comment above
    "differential_pressure_psi_lag20",
}


def is_recommended(col: str) -> bool:
    # Verificamos si esta columna está en el set de features recomendadas por defecto
    return col in RECOMMENDED_DEFAULT


# Definimos los rangos físicamente plausibles por canal.
# Physically plausible ranges per channel — the data-quality gate drops rows with
# any selected feature (or the target) outside these. Channels without an entry are
# left unbounded.
PLAUSIBLE_RANGES = {
    "rate_of_penetration_ft_per_hr": (0.0, 1000.0),
    "weight_on_bit_klbs": (0.0, 120.0),
    "rotary_rpm_rpm": (0.0, 350.0),
    "motor_rpm_rpm": (0.0, 500.0),
    "total_pump_output_gal_per_min": (0.0, 1500.0),
    "totalpumpdisplacement_barrels": (0.0, 1e6),
    "standpipe_pressure_psi": (0.0, 8000.0),
    "differential_pressure_psi": (0.0, 3000.0),
    "hook_load_klbs": (0.0, 700.0),
    "over_pull_klbs": (0.0, 300.0),
    "bit_depth_feet": (0.0, 40000.0),
    "hole_depth_feet": (0.0, 40000.0),
    "block_height_feet": (0.0, 200.0),
    "trip_speed_ft_per_min": (0.0, 600.0),
    "pump_1_strokes_min_spm": (0.0, 250.0),
    "pump_2_strokes_min_spm": (0.0, 250.0),
    "bit_size": (3.0, 40.0),
}


# 0 significa "sin lectura" para estos sensores, así que la completitud cuenta no-nulo Y no-cero
# (misma convención que el módulo de Outliers).
def _present_sql(col: str) -> str:
    # Armamos la expresión SQL que cuenta cuántas filas tienen este canal presente (no nulo, no cero)
    return f'count(*) FILTER (WHERE "{col}" IS NOT NULL AND "{col}" <> 0)'


# Definimos los cachés en proceso (well_summaries y bit_size_options) con su TTL corto
_CACHE: Dict[str, Any] = {"data": None, "at": 0.0}
_BIT_SIZE_CACHE: Dict[str, Any] = {"data": None, "at": 0.0}


def bit_size_options(ttl: float = 300.0) -> List[float]:
    """Distinct bit diameters present across all well data, for the wizard's
    bit-diameter filter (Step 1). Cached — the set of drilled bit sizes changes
    rarely, and this is a DISTINCT scan over a multi-million-row table."""
    # Revisamos si el caché sigue vigente antes de golpear la base de datos
    now = _time.monotonic()
    if _BIT_SIZE_CACHE["data"] is not None and (now - _BIT_SIZE_CACHE["at"]) < ttl:
        return _BIT_SIZE_CACHE["data"]
    # Consultamos los diámetros de bit distintos presentes en toda la tabla well_data
    sql = text('SELECT DISTINCT "bit_size" FROM well_data WHERE "bit_size" IS NOT NULL AND "bit_size" > 0 ORDER BY "bit_size"')
    try:
        with db_manager._engine.connect() as cx:
            out = [float(r[0]) for r in cx.execute(sql)]
    except Exception:
        # Si la consulta falla, registramos el error y devolvemos el último caché conocido (o vacío)
        logger.exception("bit_size_options() query failed")
        return _BIT_SIZE_CACHE["data"] or []
    # Actualizamos el caché con el resultado fresco
    _BIT_SIZE_CACHE["data"] = out
    _BIT_SIZE_CACHE["at"] = now
    return out


def well_summaries(ttl: float = 300.0, depth_range=None, date_range=None, bit_sizes=None) -> Dict[int, Dict[str, Any]]:
    """Per-well {n_rows, start_date, final_depth, target_completeness,
    feature_completeness} keyed by well_id. Cached for ``ttl`` seconds — but only
    the unfiltered result is cacheable; a depth/date/bit-size filter bypasses the
    cache (single grouped-aggregate query, cheap enough to run live per keystroke)."""
    # Determinamos si hay algún filtro en vivo — de ser así, no usamos ni actualizamos el caché
    live_filter = depth_range is not None or date_range is not None or bool(bit_sizes)
    if not live_filter:
        now = _time.monotonic()
        if _CACHE["data"] is not None and (now - _CACHE["at"]) < ttl:
            return _CACHE["data"]

    # Only RAW sensor columns exist in well_data — engineered features are derived
    # later in pandas, so the completeness SQL must use raw_candidates(), not
    # feature_candidates() (which also lists engineered names that aren't columns).
    # Solo existen columnas de sensor CRUDAS en well_data — las features de ingeniería se derivan
    # después en pandas, así que el SQL de completitud debe usar raw_candidates(), no feature_candidates().
    feats = raw_candidates()
    feat_present = " + ".join(_present_sql(c) for c in feats) or "0"

    # Armamos las cláusulas WHERE dinámicamente según los filtros recibidos
    where, params = [], {}
    if depth_range is not None:
        # Filtramos por rango de profundidad (bit depth si existe, si no hole depth)
        lo, hi = depth_range
        if lo is not None:
            where.append('COALESCE("bit_depth_feet", "hole_depth_feet") >= :depth_lo')
            params["depth_lo"] = lo
        if hi is not None:
            where.append('COALESCE("bit_depth_feet", "hole_depth_feet") <= :depth_hi')
            params["depth_hi"] = hi
    if date_range is not None:
        # Filtramos por rango de años (convertidos al formato de fecha de la columna)
        yr_lo, yr_hi = date_range
        if yr_lo is not None:
            where.append('"yyyy_mm_dd" >= :date_lo')
            params["date_lo"] = "%04d/01/01" % yr_lo
        if yr_hi is not None:
            where.append('"yyyy_mm_dd" <= :date_hi')
            params["date_hi"] = "%04d/12/31" % yr_hi
    if bit_sizes:
        # Filtramos por los diámetros de bit seleccionados
        where.append('"bit_size" = ANY(:bit_sizes)')
        params["bit_sizes"] = list(bit_sizes)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # Armamos la consulta agregada por pozo: conteo, fechas, profundidades y completitud de target/features
    sql = text(
        f"""
        SELECT well_id,
               count(*)                                           AS n,
               min(yyyy_mm_dd)                                    AS start_date,
               min(COALESCE(hole_depth_feet, bit_depth_feet))     AS start_depth,
               max(COALESCE(hole_depth_feet, bit_depth_feet))     AS final_depth,
               {_present_sql(TARGET)}                             AS target_present,
               ({feat_present})                                   AS feat_present_sum
        FROM well_data
        {where_sql}
        GROUP BY well_id
        """
    )
    # Evitamos dividir entre cero cuando no hay features seguidas
    n_feats = max(1, len(feats))
    out: Dict[int, Dict[str, Any]] = {}
    try:
        with db_manager._engine.connect() as cx:
            for row in cx.execute(sql, params):
                n = row.n or 0
                # Calculamos los porcentajes de completitud del target y de las features por pozo
                out[row.well_id] = {
                    "n_rows": n,
                    "start_date": row.start_date,
                    "start_depth": float(row.start_depth) if row.start_depth is not None else None,
                    "final_depth": float(row.final_depth) if row.final_depth is not None else None,
                    "target_completeness": (row.target_present / n * 100.0) if n else 0.0,
                    "feature_completeness": (row.feat_present_sum / (n * n_feats) * 100.0) if n else 0.0,
                }
    except Exception:
        # Si la consulta falla, registramos el error y caemos al último caché conocido
        logger.exception("well_summaries() query failed (depth_range=%s date_range=%s); falling back to cache",
                         depth_range, date_range)
        return _CACHE["data"] or {}

    # Solo actualizamos el caché cuando la consulta no tenía filtros en vivo
    if not live_filter:
        _CACHE["data"] = out
        _CACHE["at"] = now
    # Devolvemos el resumen por pozo
    return out
