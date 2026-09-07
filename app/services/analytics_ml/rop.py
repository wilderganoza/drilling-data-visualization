"""ROP Optimisation — MSE founder-point analysis.

Reads per-interval drilling parameters (WOB, RPM, flow, torque, ROP, MSE) from
the drill-params capture grid for an event and derives, from this well's own
data, the most efficient operating point (minimum Mechanical Specific Energy),
the founder point (where more WOB stops buying ROP), a ROP-vs-WOB regression and
per-formation WOB/RPM/flow recommendations. Teale (1965) MSE founder-point method.

Falls back to coarse daily-average ROP when no per-interval readings exist.
"""
# Importamos CONFIG_BY_KEY para resolver el modelo de la grilla drill-params
from app.models.capture import CONFIG_BY_KEY
# Importamos GridRepository para leer las filas capturadas de la grilla
from app.repositories.capture_repository import GridRepository
# Importamos DailyReportRepository para listar los reportes diarios de un evento
from app.repositories.daily_report_repository import DailyReportRepository
# Importamos sensor_source para preferir los datos reales de sensores cuando el pozo tiene enlace legacy
from app.services.analytics_ml import sensor_source


def _f(v):
    """Numeric column (or None) -> float or None."""
    # Si el valor es None, no hay lectura
    if v is None:
        return None
    try:
        # Convertimos la columna Numeric a float
        return float(v)
    except (TypeError, ValueError):
        # Si no se puede convertir, lo tratamos como ausente
        return None


def _collect_points(db, event_id):
    """Return (points, coarse). points sorted by depth_md."""
    # Listamos los reportes diarios del evento y resolvemos el modelo de la grilla drill-params
    reports = DailyReportRepository(db).list_for_event(event_id)
    model = CONFIG_BY_KEY["drill-params"].model
    points = []

    # Recorremos cada reporte diario y sus filas de la grilla para armar los puntos por intervalo
    for report in reports:
        rows = GridRepository(db, model, parent_field="daily_report_id").list_for_parent(report.id)
        for r in rows:
            depth = _f(getattr(r, "depth_md", None))
            rop = _f(getattr(r, "rop", None))
            # Si no hay ni profundidad ni ROP, el punto no aporta nada, lo descartamos
            if depth is None and rop is None:
                continue
            points.append({
                "depth_md": depth,
                "formation": getattr(r, "formation", None) or None,
                "wob": _f(getattr(r, "wob", None)),
                "rpm": _f(getattr(r, "rpm", None)),
                "flow_gpm": _f(getattr(r, "flow_gpm", None)),
                "torque": _f(getattr(r, "torque_ftlb", None)),
                "rop": rop,
                "mse_ksi": _f(getattr(r, "mse_ksi", None)),
            })

    # Si obtuvimos puntos por intervalo, los ordenamos por profundidad y los devolvemos como "finos"
    if points:
        points.sort(key=lambda p: (p["depth_md"] is None, p["depth_md"] or 0.0))
        return points, False

    # Fallback: coarse daily-average ROP, no per-interval WOB/RPM/MSE.
    # Si no hubo datos por intervalo, calculamos un ROP promedio diario como respaldo
    for report in reports:
        depth = _f(getattr(report, "md", None))
        progress = _f(getattr(report, "progress", None))
        rot = _f(getattr(report, "rotating_hrs", None)) or 0.0
        sld = _f(getattr(report, "sliding_hrs", None)) or 0.0
        hrs = (rot + sld) or 1.0
        rop = (progress / hrs) if progress is not None else None
        if depth is None and rop is None:
            continue
        points.append({
            "depth_md": depth,
            "formation": getattr(report, "formation", None) or None,
            "wob": None, "rpm": None, "flow_gpm": None, "torque": None,
            "rop": rop, "mse_ksi": None,
        })

    # Ordenamos por profundidad y marcamos el resultado como "grueso" (coarse=True)
    points.sort(key=lambda p: (p["depth_md"] is None, p["depth_md"] or 0.0))
    return points, True


def _regression(pairs):
    """Least-squares ROP = m*WOB + b over [(wob, rop)]. Pure Python."""
    # Necesitamos al menos 2 puntos para ajustar una recta
    n = len(pairs)
    if n < 2:
        return {"m": None, "b": None}
    # Calculamos las sumas necesarias para la regresión lineal por mínimos cuadrados
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    sxx = sum(x * x for x, _ in pairs)
    sxy = sum(x * y for x, y in pairs)
    denom = n * sxx - sx * sx
    # Si el denominador es cero (todos los WOB iguales), no hay pendiente definida
    if denom == 0:
        return {"m": None, "b": None}
    # Calculamos pendiente e intercepto de la recta ROP = m*WOB + b
    m = (n * sxy - sx * sy) / denom
    b = (sy - m * sx) / n
    return {"m": round(m, 3), "b": round(b, 2)}


def _founder(points):
    """Min-MSE operating point + founder WOB (where ROP stops rising with WOB)."""
    # Filtramos los puntos que tienen WOB y MSE para poder ubicar el punto óptimo
    with_mse = [p for p in points if p["wob"] is not None and p["mse_ksi"] is not None]
    wob_opt = mse_min = rop_at_opt = None
    if with_mse:
        # Buscamos el punto de menor MSE (el más eficiente energéticamente)
        best = min(with_mse, key=lambda p: p["mse_ksi"])
        wob_opt = round(best["wob"], 1)
        mse_min = round(best["mse_ksi"], 1)
        rop_at_opt = round(best["rop"], 1) if best["rop"] is not None else None

    # Founder WOB: bin points by WOB (integer klbf), average ROP per bin, then
    # scan bins by ascending WOB and flag the first WOB where ROP drops vs the
    # previous (lower-WOB) bin — beyond that, more weight no longer buys ROP.
    with_wob = [p for p in points if p["wob"] is not None and p["rop"] is not None]
    wob_founder = None
    if len(with_wob) >= 3:
        # Agrupamos los puntos por WOB redondeado a entero (klbf)
        bins = {}
        for p in with_wob:
            key = round(p["wob"])
            bins.setdefault(key, []).append(p["rop"])
        # Promediamos el ROP por bin y ordenamos por WOB ascendente
        binned = sorted((k, sum(v) / len(v)) for k, v in bins.items())
        # Buscamos el primer bin donde el ROP promedio cae respecto al bin anterior (WOB de founder)
        for i in range(1, len(binned)):
            if binned[i][1] < binned[i - 1][1]:
                wob_founder = round(float(binned[i - 1][0]), 1)
                break

    # Devolvemos el punto óptimo (mínima MSE) y el WOB de founder detectado
    return {"wob_opt": wob_opt, "mse_min": mse_min,
            "rop_at_opt": rop_at_opt, "wob_founder": wob_founder}


def _recommendations(points):
    """Per formation, recommend WOB/RPM/flow at that formation's min-MSE point."""
    # Agrupamos los puntos por formación, solo los que tienen WOB y MSE
    groups = {}
    for p in points:
        if p["formation"] and p["wob"] is not None and p["mse_ksi"] is not None:
            groups.setdefault(p["formation"], []).append(p)

    recs = []
    # Para cada formación, recomendamos los parámetros del punto de menor MSE
    for formation, pts in groups.items():
        best = min(pts, key=lambda p: p["mse_ksi"])
        recs.append({
            "formation": formation,
            "wob": round(best["wob"], 1) if best["wob"] is not None else None,
            "rpm": round(best["rpm"]) if best["rpm"] is not None else None,
            "flow": round(best["flow_gpm"]) if best["flow_gpm"] is not None else None,
            "rop_expected": round(best["rop"], 1) if best["rop"] is not None else None,
            "mse": round(best["mse_ksi"], 1),
        })
    # Ordenamos las recomendaciones de menor a mayor MSE (mejores primero)
    recs.sort(key=lambda r: r["mse"])
    return recs


def _summary(points):
    # Calculamos el ROP y MSE promedio sobre los puntos que tienen esos valores
    rops = [p["rop"] for p in points if p["rop"] is not None]
    mses = [p["mse_ksi"] for p in points if p["mse_ksi"] is not None]
    avg_rop = round(sum(rops) / len(rops), 1) if rops else None
    avg_mse = round(sum(mses) / len(mses), 1) if mses else None

    # Buscamos el intervalo con mejor ROP para destacarlo en el resumen
    best_interval = None
    best = max((p for p in points if p["rop"] is not None),
               key=lambda p: p["rop"], default=None)
    if best is not None:
        best_interval = {
            "depth_md": round(best["depth_md"], 1) if best["depth_md"] is not None else None,
            "formation": best["formation"],
            "rop": round(best["rop"], 1),
        }
    # Devolvemos el resumen con promedios, cantidad de puntos y el mejor intervalo
    return {"avg_rop": avg_rop, "avg_mse": avg_mse,
            "n_points": len(points), "best_interval": best_interval}


def analyze(db, event_id, domain="depth"):
    # Definimos la respuesta vacía que devolvemos cuando no hay evento o no hay datos
    empty = {"ok": False, "error": "No drilling data for this well. Capture the drill-params grid, "
             "or link the well to a sensor dataset (Master Data → legacy well).",
             "points": [], "founder": {}, "regression": {"m": None, "b": None},
             "recommendations": [], "summary": {"avg_rop": None, "avg_mse": None, "n_points": 0},
             "coarse": False, "source": "none", "sensor_note": None}
    if not event_id:
        return empty

    # Prefer the REAL sensor record (well_data via the well's legacy link); fall
    # back to the manually-captured drill-params grid.
    source = "drill-params"
    sensor_note = None
    try:
        # Intentamos leer primero los datos reales de sensores (well_data vía el enlace legacy del pozo)
        sd = sensor_source.drilling_points(db, event_id, domain=domain)
        if sd["points"]:
            points = sd["points"]
            for p in points:
                p["torque"] = p.pop("torque_ftlb", None)   # normalise key for this module
            coarse = False
            source = sd["source"]
            # Explicamos por qué no se calcula MSE con datos de sensor (faltan torque de superficie y bit size)
            sensor_note = ("Real sensor data ({:,} pts, {} domain). Surface torque and bit size "
                           "are not in the sensor channel set, so MSE is not computed — the founder "
                           "point is taken from the ROP-vs-WOB response.").format(sd["n"], domain)
        else:
            # Si no hay datos de sensor, recurrimos a la grilla drill-params capturada manualmente
            points, coarse = _collect_points(db, event_id)
    except Exception as exc:  # pragma: no cover - defensive
        # Si algo falla leyendo los datos, devolvemos el error en vez de romper la página
        return dict(empty, error="Could not read drilling data: %s" % exc)

    if not points:
        return empty

    # Ajustamos la regresión ROP vs WOB con los puntos que tienen ambos valores
    regression = _regression([(p["wob"], p["rop"]) for p in points
                              if p["wob"] is not None and p["rop"] is not None])

    # Devolvemos el análisis completo: puntos, founder point, regresión, recomendaciones y resumen
    return {
        "ok": True,
        "coarse": coarse,
        "source": source,
        "sensor_note": sensor_note,
        "points": points,
        "founder": _founder(points),
        "regression": regression,
        "recommendations": _recommendations(points),
        "summary": _summary(points),
    }
