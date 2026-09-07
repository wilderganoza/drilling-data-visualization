"""NPT Analytics — categorisation, statistical anomaly detection and heuristic
risk scoring over the NPT knowledge-management record.

No trained model today: events are bucketed into a fixed taxonomy by keyword,
per-category hours distributions are screened for outliers with a robust
median/MAD z-score, and each category gets a 0..100 risk score from its
frequency and average duration. The per-event feature rows this builds
(category, hours, cost, md, well) are exactly the features a supervised
classifier would consume once enough labelled wells are loaded — see ml_note.
"""
# Importamos median/pstdev para las estadísticas robustas de la distribución de horas por categoría
from statistics import median, pstdev

# Importamos select para consultar los eventos NPT
from sqlalchemy import select

# Importamos DailyReport para resolver a qué pozo pertenece cada evento NPT
from app.models.daily_report import DailyReport
# Importamos Event/Well/Wellbore para subir por la jerarquía desde el reporte diario hasta el nombre del pozo
from app.models.hierarchy import Event, Well, Wellbore
# Importamos NptEvent, el modelo de origen de los eventos de tiempo no productivo
from app.models.npt import NptEvent

# Definimos la taxonomía fija de categorías de NPT
NPT_CATEGORIES = [
    "Stuck Pipe",
    "Well Control",
    "Mud / Losses",
    "Equipment Failure",
    "Bit / BHA",
    "Directional / MWD",
    "Cementing",
    "Wellbore Instability",
    "Waiting (Weather/Logistics)",
    "Rig / Surface",
    "Other",
]

# Definimos las reglas de palabras clave en orden — la primera coincidencia gana,
# por eso las categorías más específicas van primero.
_KEYWORDS = [
    ("Stuck Pipe", ("stuck", "pack off", "pack-off", "packoff", "differential stick")),
    ("Well Control", ("kick", "well control", "influx", "shut in", "shut-in", "gas migration")),
    ("Mud / Losses", ("loss", "losses", "mud ", " mud", "seepage", "returns", "lost circulation")),
    ("Cementing", ("cement", "squeeze", "plug back", "toc")),
    ("Directional / MWD", ("mwd", "lwd", "survey", "directional", "steering", "toolface", "gyro")),
    ("Bit / BHA", ("bit", "bha", "dull", "nozzle", "reamer", "stabilizer")),
    ("Wellbore Instability", ("wellbore", "collapse", "tight", "instability", "cavings", "sloughing")),
    ("Waiting (Weather/Logistics)", ("weather", "wait", "waiting", "logistic", "wow", "delay")),
    ("Equipment Failure", ("pump", "equipment", "failure", "motor", "top drive", "topdrive", "swivel", "power", "hydraulic")),
    ("Rig / Surface", ("rig", "surface", "bop", "derrick", "drawworks", "crane")),
]


def _f(v) -> float:
    """Numeric → float, tolerating None / Decimal / bad values."""
    # Intentamos convertir a float, tratando None como 0.0
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        # Devolvemos 0.0 si el valor no es convertible
        return 0.0


def categorize(event) -> str:
    """Keyword-match an NPT event into one of NPT_CATEGORIES."""
    # Concatenamos los campos de texto relevantes del evento en minúsculas para buscar palabras clave
    text = " ".join([
        (event.npt_type or ""),
        (event.cause or ""),
        (event.title or ""),
    ]).lower()
    # Recorremos las reglas en orden (la primera coincidencia gana)
    for category, keywords in _KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    # Devolvemos "Other" cuando ninguna palabra clave coincide
    return "Other"


def _mad(values, med) -> float:
    """Median absolute deviation."""
    # Si no hay valores, no hay desviación que calcular
    if not values:
        return 0.0
    # Calculamos la mediana de las desviaciones absolutas respecto a la mediana
    return median([abs(x - med) for x in values])


def analyze(db) -> dict:
    # Mapeamos report_id -> (well_label, event_id), construido y cacheado a demanda
    report_map: dict = {}

    def resolve_well(report_id):
        # Si ya resolvimos este reporte antes, reutilizamos el resultado cacheado
        if report_id in report_map:
            return report_map[report_id]
        label, ev_id = "Unknown well", None
        # Buscamos el reporte diario para subir por la jerarquía hasta el pozo
        rep = db.get(DailyReport, report_id) if report_id else None
        if rep is not None:
            ev_id = rep.event_id
            # Subimos del reporte al evento, del evento al wellbore y del wellbore al pozo
            ev = db.get(Event, rep.event_id) if rep.event_id else None
            wb = db.get(Wellbore, ev.wellbore_id) if ev else None
            well = db.get(Well, wb.well_id) if wb else None
            if well and well.legal_well_name:
                label = well.legal_well_name
        # Guardamos el resultado en el caché antes de devolverlo
        report_map[report_id] = (label, ev_id)
        return report_map[report_id]

    # ---- Construimos las filas de features por evento ---------------------
    rows = []
    for ev in db.execute(select(NptEvent)).scalars().all():
        # Saltamos los registros corregidos/reemplazados — nos quedamos solo con la cabeza vigente de la cadena.
        if getattr(ev, "superseded_by_id", None) is not None:
            continue
        # Resolvemos el pozo al que pertenece el evento
        well, _ = resolve_well(ev.daily_report_id)
        # Preferimos horas brutas; si no hay, usamos horas netas
        hours = _f(ev.gross_hours) or _f(ev.net_hours) or 0.0
        # Sumamos los tres componentes de costo del evento
        cost = _f(ev.type_cost) + _f(ev.equip_cost) + _f(ev.other_cost)
        # Agregamos la fila de features de este evento
        rows.append({
            "category": categorize(ev),
            "well": well,
            "hours": round(hours, 2),
            "cost": round(cost, 2),
            "md": _f(ev.failure_md),
            "title": ev.title or ev.cause or ev.npt_type or "NPT event",
        })

    # Calculamos los totales generales
    total_events = len(rows)
    total_hours = round(sum(r["hours"] for r in rows), 2)
    total_cost = round(sum(r["cost"] for r in rows), 2)

    # ---- Estadística descriptiva: por categoría ----------------------------
    cat_map: dict = {}
    for r in rows:
        # Acumulamos count/hours/cost/_hours_list por categoría
        c = cat_map.setdefault(r["category"], {"category": r["category"], "count": 0, "hours": 0.0, "cost": 0.0, "_hours_list": []})
        c["count"] += 1
        c["hours"] += r["hours"]
        c["cost"] += r["cost"]
        c["_hours_list"].append(r["hours"])

    # Armamos la lista final de estadísticas por categoría (redondeando y calculando el promedio de horas)
    categories_stats = []
    for c in cat_map.values():
        avg_hours = c["hours"] / c["count"] if c["count"] else 0.0
        categories_stats.append({
            "category": c["category"],
            "count": c["count"],
            "hours": round(c["hours"], 2),
            "cost": round(c["cost"], 2),
            "avg_hours": round(avg_hours, 2),
            "_hours_list": c["_hours_list"],
        })

    # ---- Estadística descriptiva: por pozo ---------------------------------
    well_map: dict = {}
    for r in rows:
        # Acumulamos count/hours/cost por pozo
        w = well_map.setdefault(r["well"], {"well": r["well"], "count": 0, "hours": 0.0, "cost": 0.0})
        w["count"] += 1
        w["hours"] += r["hours"]
        w["cost"] += r["cost"]
    # Ordenamos los pozos de mayor a menor horas de NPT
    by_well = sorted(
        [{"well": w["well"], "count": w["count"], "hours": round(w["hours"], 2), "cost": round(w["cost"], 2)} for w in well_map.values()],
        key=lambda x: x["hours"], reverse=True,
    )

    # ---- Detección de anomalías ---------------------------------------------
    # Usamos un z-score robusto (mediana/MAD) por categoría sobre la distribución de horas.
    anomalies = []
    cost_threshold = None
    if rows:
        sorted_costs = sorted(r["cost"] for r in rows)
        # Calculamos el punto de corte del 10% más costoso (percentil 90)
        idx = max(0, min(len(sorted_costs) - 1, int(round(0.9 * (len(sorted_costs) - 1)))))
        cost_threshold = sorted_costs[idx]

    # Calculamos mediana/MAD/desviación estándar de horas por categoría, para usarlas como referencia de anomalía
    cat_hours = {c["category"]: c["_hours_list"] for c in categories_stats}
    cat_stats_h = {}
    for cat, vals in cat_hours.items():
        med = median(vals) if vals else 0.0
        mad = _mad(vals, med)
        std = pstdev(vals) if len(vals) > 1 else 0.0
        cat_stats_h[cat] = (med, mad, std)

    # Recorremos cada evento y marcamos como anomalía el que se salga del rango esperado de su categoría
    for r in rows:
        med, mad, std = cat_stats_h.get(r["category"], (0.0, 0.0, 0.0))
        reasons = []
        if mad > 0:
            # Usamos el z-score robusto basado en MAD (constante 0.6745 para que sea comparable a un z-score normal)
            z = 0.6745 * (r["hours"] - med) / mad
            if abs(z) > 3.5:
                reasons.append("duration outlier (robust z={:.1f})".format(z))
        elif std > 0 and r["hours"] > med + 2 * std:
            # Si el MAD es cero (poca variación), caemos a un umbral simple de 2 desviaciones estándar
            reasons.append("duration outlier (>{:.1f}h)".format(med + 2 * std))
        if cost_threshold is not None and r["cost"] > 0 and r["cost"] >= cost_threshold and total_events >= 5:
            # Marcamos también los eventos cuyo costo cae en el 10% más alto (solo si hay suficientes eventos)
            reasons.append("cost in top 10%")
        if reasons:
            anomalies.append({
                "well": r["well"],
                "category": r["category"],
                "hours": r["hours"],
                "cost": r["cost"],
                "md": r["md"],
                "reason": "; ".join(reasons),
            })
    # Ordenamos las anomalías de mayor a menor duración
    anomalies.sort(key=lambda a: a["hours"], reverse=True)

    # ---- Puntaje de riesgo ---------------------------------------------------
    # risk = normalizado(frecuencia) * normalizado(horas_promedio), escalado 0..100.
    max_count = max((c["count"] for c in categories_stats), default=0)
    max_avg = max((c["avg_hours"] for c in categories_stats), default=0.0)
    for c in categories_stats:
        # Normalizamos frecuencia y duración promedio contra el máximo observado
        freq_n = (c["count"] / max_count) if max_count else 0.0
        dur_n = (c["avg_hours"] / max_avg) if max_avg else 0.0
        # Combinamos ambos factores con la media geométrica y escalamos a 0..100
        c["risk"] = round(100.0 * (freq_n * dur_n) ** 0.5, 1)
        # Quitamos la lista auxiliar de horas — ya no la necesitamos en la salida
        c.pop("_hours_list", None)

    # Ordenamos las categorías de mayor a menor riesgo (y horas como desempate)
    categories_stats.sort(key=lambda c: (c["risk"], c["hours"]), reverse=True)

    # Identificamos la categoría de mayor riesgo
    top_risk_category = categories_stats[0]["category"] if categories_stats else None
    # Calculamos el índice de riesgo NPT general: media de los riesgos por categoría, ponderada por horas, 0..100.
    if total_hours > 0 and categories_stats:
        npt_risk_index = round(sum(c["risk"] * c["hours"] for c in categories_stats) / total_hours, 1)
    else:
        npt_risk_index = 0.0

    # Documentamos en la nota qué tan lista está esta capa para un modelo supervisado a futuro
    ml_note = (
        "These per-event feature rows (category, hours, cost, failure depth, well) are ready "
        "for a supervised classifier once more wells are loaded. Today the analysis is purely "
        "descriptive plus statistical anomaly detection (robust median/MAD z-score) — no model "
        "is trained, so results stay explainable and need no labelled history."
    )

    # Devolvemos el resultado completo del análisis: estadísticas, anomalías y el índice de riesgo
    return {
        "categories_stats": categories_stats,
        "by_well": by_well,
        "anomalies": anomalies,
        "total_events": total_events,
        "total_hours": total_hours,
        "total_cost": total_cost,
        "npt_risk_index": npt_risk_index,
        "top_risk_category": top_risk_category,
        "ml_note": ml_note,
    }
