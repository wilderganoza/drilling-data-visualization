"""NPT Analytics — categorisation, statistical anomaly detection and heuristic
risk scoring over the NPT knowledge-management record.

No trained model today: events are bucketed into a fixed taxonomy by keyword,
per-category hours distributions are screened for outliers with a robust
median/MAD z-score, and each category gets a 0..100 risk score from its
frequency and average duration. The per-event feature rows this builds
(category, hours, cost, md, well) are exactly the features a supervised
classifier would consume once enough labelled wells are loaded — see ml_note.
"""
from statistics import median, pstdev

from sqlalchemy import select

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

# Ordered keyword rules — first hit wins, so more specific categories come first.
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
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def categorize(event) -> str:
    """Keyword-match an NPT event into one of NPT_CATEGORIES."""
    text = " ".join([
        (event.npt_type or ""),
        (event.cause or ""),
        (event.title or ""),
    ]).lower()
    for category, keywords in _KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    return "Other"


def _mad(values, med) -> float:
    """Median absolute deviation."""
    if not values:
        return 0.0
    return median([abs(x - med) for x in values])


def analyze(db) -> dict:
    from app.models.daily_report import DailyReport
    from app.models.hierarchy import Event, Well, Wellbore
    from app.models.npt import NptEvent

    # report_id -> (well_label, event_id) mapping, built lazily/cached.
    report_map: dict = {}

    def resolve_well(report_id):
        if report_id in report_map:
            return report_map[report_id]
        label, ev_id = "Unknown well", None
        rep = db.get(DailyReport, report_id) if report_id else None
        if rep is not None:
            ev_id = rep.event_id
            ev = db.get(Event, rep.event_id) if rep.event_id else None
            wb = db.get(Wellbore, ev.wellbore_id) if ev else None
            well = db.get(Well, wb.well_id) if wb else None
            if well and well.legal_well_name:
                label = well.legal_well_name
        report_map[report_id] = (label, ev_id)
        return report_map[report_id]

    # ---- Build per-event feature rows ------------------------------------
    rows = []
    for ev in db.execute(select(NptEvent)).scalars().all():
        # Skip corrected/superseded records — keep the current chain head only.
        if getattr(ev, "superseded_by_id", None) is not None:
            continue
        well, _ = resolve_well(ev.daily_report_id)
        hours = _f(ev.gross_hours) or _f(ev.net_hours) or 0.0
        cost = _f(ev.type_cost) + _f(ev.equip_cost) + _f(ev.other_cost)
        rows.append({
            "category": categorize(ev),
            "well": well,
            "hours": round(hours, 2),
            "cost": round(cost, 2),
            "md": _f(ev.failure_md),
            "title": ev.title or ev.cause or ev.npt_type or "NPT event",
        })

    total_events = len(rows)
    total_hours = round(sum(r["hours"] for r in rows), 2)
    total_cost = round(sum(r["cost"] for r in rows), 2)

    # ---- Descriptive: per category ---------------------------------------
    cat_map: dict = {}
    for r in rows:
        c = cat_map.setdefault(r["category"], {"category": r["category"], "count": 0, "hours": 0.0, "cost": 0.0, "_hours_list": []})
        c["count"] += 1
        c["hours"] += r["hours"]
        c["cost"] += r["cost"]
        c["_hours_list"].append(r["hours"])

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

    # ---- Descriptive: per well -------------------------------------------
    well_map: dict = {}
    for r in rows:
        w = well_map.setdefault(r["well"], {"well": r["well"], "count": 0, "hours": 0.0, "cost": 0.0})
        w["count"] += 1
        w["hours"] += r["hours"]
        w["cost"] += r["cost"]
    by_well = sorted(
        [{"well": w["well"], "count": w["count"], "hours": round(w["hours"], 2), "cost": round(w["cost"], 2)} for w in well_map.values()],
        key=lambda x: x["hours"], reverse=True,
    )

    # ---- Anomaly detection ------------------------------------------------
    # Robust median/MAD z-score per category on the hours distribution.
    anomalies = []
    cost_threshold = None
    if rows:
        sorted_costs = sorted(r["cost"] for r in rows)
        # top 10% cost cutoff (90th percentile)
        idx = max(0, min(len(sorted_costs) - 1, int(round(0.9 * (len(sorted_costs) - 1)))))
        cost_threshold = sorted_costs[idx]

    cat_hours = {c["category"]: c["_hours_list"] for c in categories_stats}
    cat_stats_h = {}
    for cat, vals in cat_hours.items():
        med = median(vals) if vals else 0.0
        mad = _mad(vals, med)
        std = pstdev(vals) if len(vals) > 1 else 0.0
        cat_stats_h[cat] = (med, mad, std)

    for r in rows:
        med, mad, std = cat_stats_h.get(r["category"], (0.0, 0.0, 0.0))
        reasons = []
        if mad > 0:
            z = 0.6745 * (r["hours"] - med) / mad
            if abs(z) > 3.5:
                reasons.append("duration outlier (robust z={:.1f})".format(z))
        elif std > 0 and r["hours"] > med + 2 * std:
            reasons.append("duration outlier (>{:.1f}h)".format(med + 2 * std))
        if cost_threshold is not None and r["cost"] > 0 and r["cost"] >= cost_threshold and total_events >= 5:
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
    anomalies.sort(key=lambda a: a["hours"], reverse=True)

    # ---- Risk scoring -----------------------------------------------------
    # risk = normalized(frequency) * normalized(avg_hours), scaled 0..100.
    max_count = max((c["count"] for c in categories_stats), default=0)
    max_avg = max((c["avg_hours"] for c in categories_stats), default=0.0)
    for c in categories_stats:
        freq_n = (c["count"] / max_count) if max_count else 0.0
        dur_n = (c["avg_hours"] / max_avg) if max_avg else 0.0
        c["risk"] = round(100.0 * (freq_n * dur_n) ** 0.5, 1)
        c.pop("_hours_list", None)

    categories_stats.sort(key=lambda c: (c["risk"], c["hours"]), reverse=True)

    top_risk_category = categories_stats[0]["category"] if categories_stats else None
    # Overall NPT risk index: hours-weighted mean of category risks, 0..100.
    if total_hours > 0 and categories_stats:
        npt_risk_index = round(sum(c["risk"] * c["hours"] for c in categories_stats) / total_hours, 1)
    else:
        npt_risk_index = 0.0

    ml_note = (
        "These per-event feature rows (category, hours, cost, failure depth, well) are ready "
        "for a supervised classifier once more wells are loaded. Today the analysis is purely "
        "descriptive plus statistical anomaly detection (robust median/MAD z-score) — no model "
        "is trained, so results stay explainable and need no labelled history."
    )

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
