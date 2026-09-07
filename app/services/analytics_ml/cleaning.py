"""Data Cleaning submodule — self-contained statistical outlier detection over
the OPERATIONAL drilling-parameter record (the ops_drill_params grid rows that
live under each daily report).

This is deliberately independent of the legacy high-frequency sensor pipeline
(/wells, LAS/CSV, the `well_data` table): it runs immediately on whatever
operational drilling parameters have been captured, using plain-Python
statistics (no numpy/pandas). Two complementary flag methods are combined:

  * Z-score:  |(x - mean) / std| > 3
  * IQR:      x < Q1 - 1.5·IQR  or  x > Q3 + 1.5·IQR

A point is an outlier if EITHER method flags it; the method(s) that fired are
recorded per point.
"""
# Importamos las funciones estadísticas de la librería estándar (sin numpy/pandas, como aclara el docstring)
from statistics import mean as _mean, median as _median, pstdev as _pstdev

# Importamos select para armar la consulta de eventos
from sqlalchemy import select

# Importamos CONFIG_BY_KEY para resolver el modelo de la grilla drill-params
from app.models.capture import CONFIG_BY_KEY
# Importamos los modelos de la jerarquía para recorrer evento -> wellbore -> pozo
from app.models.hierarchy import Event, Well, Wellbore
# Importamos GridRepository para leer las filas de la grilla capturada
from app.repositories.capture_repository import GridRepository
# Importamos DailyReportRepository para listar los reportes diarios de cada evento
from app.repositories.daily_report_repository import DailyReportRepository

# Definimos los parámetros que analizamos, en el orden en que se muestran
PARAMS = ["rop", "mse_ksi", "wob", "spp_psi", "torque_ftlb"]

# Definimos el orden de preferencia para elegir qué parámetro dibuja el gráfico (gana el más poblado,
# y los empates se resuelven a favor del que está más adelante en esta lista)
_CHART_PREF = ["rop", "mse_ksi", "wob", "spp_psi", "torque_ftlb"]

# Definimos el umbral de z-score para marcar un outlier
Z_THRESH = 3.0
# Definimos el multiplicador k del rango intercuartílico (IQR) para las cercas de Tukey
IQR_K = 1.5
# Definimos el mínimo de observaciones necesarias para calcular estadísticas de un parámetro
MIN_N = 5
# Definimos el máximo de outliers que devolvemos para no saturar la respuesta
OUTLIER_CAP = 200


def _quartiles(sorted_vals):
    """Q1 and Q3 via linear interpolation on the sorted list (Tukey-ish,
    inclusive median method — good enough for outlier fences)."""
    # Guardamos el tamaño de la lista para calcular los rangos de percentil
    n = len(sorted_vals)

    def _percentile(p):
        # Si solo hay un valor, ese es el percentil (no hay nada que interpolar)
        if n == 1:
            return sorted_vals[0]
        # Calculamos el rango (posición fraccionaria) correspondiente al percentil p
        rank = p * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        # Interpolamos linealmente entre los dos valores vecinos
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

    # Devolvemos Q1 (percentil 25) y Q3 (percentil 75)
    return _percentile(0.25), _percentile(0.75)


def _collect(db):
    """Pull every operational drilling-parameter reading across all wells.

    Returns a list of dicts: {well, depth_md, rop, mse_ksi, wob, rpm,
    spp_psi, torque_ftlb} with Numeric columns coerced to float (or None)."""
    # Resolvemos el modelo ORM de la grilla drill-params a partir de su clave de configuración
    model = CONFIG_BY_KEY["drill-params"].model
    # Creamos el repositorio que nos deja listar los reportes diarios por evento
    report_repo = DailyReportRepository(db)

    def _f(v):
        # Si el valor es None lo dejamos como None (no hay lectura)
        if v is None:
            return None
        try:
            # Convertimos la columna Numeric a float para poder operar con ella
            return float(v)
        except (TypeError, ValueError):
            # Si no se puede convertir, tratamos el valor como ausente
            return None

    points = []
    # Recorremos todos los eventos (campañas de perforación) registrados
    for ev in db.execute(select(Event)).scalars().all():
        # Resolvemos el wellbore y el pozo del evento para obtener el nombre del pozo
        wb = db.get(Wellbore, ev.wellbore_id)
        well = db.get(Well, wb.well_id) if wb else None
        well_label = (well.legal_well_name if well and well.legal_well_name else "—")
        # Recorremos cada reporte diario del evento
        for report in report_repo.list_for_event(ev.id):
            # Leemos las filas de la grilla drill-params capturadas para ese reporte
            rows = GridRepository(db, model, parent_field="daily_report_id").list_for_parent(report.id)
            for r in rows:
                # Armamos un punto con los parámetros que nos interesa analizar, coercionados a float
                points.append({
                    "well": well_label,
                    "depth_md": _f(getattr(r, "depth_md", None)),
                    "rop": _f(getattr(r, "rop", None)),
                    "mse_ksi": _f(getattr(r, "mse_ksi", None)),
                    "wob": _f(getattr(r, "wob", None)),
                    "rpm": _f(getattr(r, "rpm", None)),
                    "spp_psi": _f(getattr(r, "spp_psi", None)),
                    "torque_ftlb": _f(getattr(r, "torque_ftlb", None)),
                })
    # Devolvemos todos los puntos recolectados
    return points


def analyze(db, **kwargs) -> dict:
    # Recolectamos todos los puntos de parámetros de perforación de todos los pozos
    points = _collect(db)

    # Definimos la respuesta vacía que devolvemos cuando no hay datos capturados
    empty = {
        "params_stats": [],
        "outliers": [],
        "total_points": 0,
        "total_outliers": 0,
        "pct_outliers": 0.0,
        "series_by_param": {},
        "has_data": False,
    }
    if not points:
        return empty

    params_stats = []
    outliers = []
    # Guardamos por parámetro qué puntos son outlier, para poder armar la serie del
    # gráfico ya con la bandera de outlier resuelta.
    flags_by_param = {}   # param -> list of (point_index, is_outlier)
    counts_by_param = {}  # param -> non-null count

    # Analizamos cada parámetro de la lista PARAMS por separado
    for param in PARAMS:
        # Tomamos los valores no nulos de este parámetro, junto con su índice original
        vals = [(i, p[param]) for i, p in enumerate(points) if p.get(param) is not None]
        counts_by_param[param] = len(vals)
        # Si no hay suficientes observaciones, no calculamos estadísticas para este parámetro
        if len(vals) < MIN_N:
            continue

        xs = [v for _, v in vals]
        # Calculamos media, desviación estándar poblacional y mediana
        m = _mean(xs)
        sd = _pstdev(xs)  # population std; robust to n and never raises on n>=1
        med = _median(xs)
        # Calculamos Q1/Q3 y el rango intercuartílico para las cercas de Tukey
        q1, q3 = _quartiles(sorted(xs))
        iqr = q3 - q1
        lo_fence = q1 - IQR_K * iqr
        hi_fence = q3 + IQR_K * iqr

        param_flags = []
        n_out = 0
        # Evaluamos cada observación contra ambos métodos (z-score e IQR)
        for idx, x in vals:
            z = (x - m) / sd if sd > 0 else 0.0
            by_z = sd > 0 and abs(z) > Z_THRESH
            by_iqr = iqr > 0 and (x < lo_fence or x > hi_fence)
            is_out = by_z or by_iqr
            param_flags.append((idx, is_out))
            if is_out:
                n_out += 1
                # Registramos qué método(s) marcaron el punto como outlier
                if by_z and by_iqr:
                    method = "z+iqr"
                elif by_z:
                    method = "z"
                else:
                    method = "iqr"
                outliers.append({
                    "well": points[idx]["well"],
                    "depth_md": points[idx].get("depth_md"),
                    "param": param,
                    "value": round(x, 3),
                    "z": round(z, 2),
                    "method": method,
                })

        flags_by_param[param] = param_flags
        n = len(xs)
        # Armamos el resumen estadístico de este parámetro
        params_stats.append({
            "param": param,
            "n": n,
            "mean": round(m, 3),
            "std": round(sd, 3),
            "median": round(med, 3),
            "q1": round(q1, 3),
            "q3": round(q3, 3),
            "n_outliers": n_out,
            "pct_outliers": round(100.0 * n_out / n, 1) if n else 0.0,
        })

    # Totalizamos puntos y outliers a través de todos los parámetros analizados
    total_points = sum(s["n"] for s in params_stats)
    total_outliers = sum(s["n_outliers"] for s in params_stats)
    pct_outliers = round(100.0 * total_outliers / total_points, 1) if total_points else 0.0

    # Ordenamos los outliers del más extremo al menos extremo y limitamos la cantidad a mostrar
    outliers.sort(key=lambda o: abs(o["z"]), reverse=True)
    outliers = outliers[:OUTLIER_CAP]

    # Elegimos el parámetro que alimenta el gráfico: el más poblado (los empates se
    # resuelven con el orden de preferencia _CHART_PREF).
    series_by_param = {}
    analysed = [s["param"] for s in params_stats]
    if analysed:
        chart_param = max(
            analysed,
            key=lambda p: (counts_by_param.get(p, 0), -_CHART_PREF.index(p) if p in _CHART_PREF else 0),
        )
        flag_map = dict(flags_by_param.get(chart_param, []))
        series = []
        i = 0
        # Armamos la serie del gráfico solo con los puntos que tienen valor para el parámetro elegido
        for idx, p in enumerate(points):
            v = p.get(chart_param)
            if v is None:
                continue
            series.append({"i": i, "value": round(v, 3), "outlier": bool(flag_map.get(idx, False))})
            i += 1
        series_by_param[chart_param] = series

    # Devolvemos el resultado completo del análisis de calidad de datos
    return {
        "params_stats": params_stats,
        "outliers": outliers,
        "total_points": total_points,
        "total_outliers": total_outliers,
        "pct_outliers": pct_outliers,
        "series_by_param": series_by_param,
        "has_data": True,
    }
