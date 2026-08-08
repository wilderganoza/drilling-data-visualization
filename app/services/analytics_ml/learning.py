"""Cross-well learning curves + lessons mining.

Two related surfaces built on the field benchmark:

* **Learning curve** — order the field's wells by spud date, then fit a power
  law y = a·n^b to the normalised KPIs (cost/ft, days/1000 ft) versus well
  index n. The exponent b is the classic learning slope; the improvement per
  doubling of experience is 1 − 2^b. A negative b (and positive rate) means the
  team is getting cheaper/faster well over well.
* **Lessons mining** — roll the per-event lessons-learned register up by
  category and surface the highest-NPT lessons so the next well's plan can act
  on them.

Everything is pure-Python (math only) and honest about missing data: any KPI
that can't be computed is skipped rather than guessed.
"""
import math

# Standard bit / hole sizes (inches) — snap captured hole_size to the nearest of
# these so a 12.25 vs 12.250 vs 12.24 all aggregate into one section.
_STD_SIZES = [
    36.0, 26.0, 24.0, 22.0, 20.0, 17.5, 16.0, 14.75, 13.5, 12.25,
    9.875, 8.75, 8.5, 6.5, 6.125, 5.875, 4.75,
]


def _f(v):
    """Coerce a possibly-Numeric/None value to float, or None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _snap_size(v):
    v = _f(v)
    if v is None or v <= 0:
        return None
    best = min(_STD_SIZES, key=lambda s: abs(s - v))
    return best if abs(best - v) <= 0.4 else round(v, 3)


def _power_fit(points):
    """Fit y = a·n^b by ordinary least squares on the log-log transform.

    `points` is a list of (n, y) with n >= 1 and y > 0. Returns
    {a, b, r2, rate} or None when there are fewer than 3 usable points. `rate`
    is the fractional improvement per doubling of experience (1 − 2^b)."""
    pts = [(n, y) for (n, y) in points if n and n > 0 and y and y > 0]
    if len(pts) < 3:
        return None
    xs = [math.log(n) for n, _ in pts]
    ys = [math.log(y) for _, y in pts]
    k = len(pts)
    mx = sum(xs) / k
    my = sum(ys) / k
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    ln_a = my - b * mx
    a = math.exp(ln_a)
    # R² in log space.
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (ln_a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    return {
        "a": round(a, 2),
        "b": round(b, 4),
        "r2": round(r2, 3),
        "rate": round(1.0 - 2.0 ** b, 4),
    }


def analyze(db) -> dict:
    from sqlalchemy import select

    from app.models.hierarchy import Event, Well, Wellbore
    from app.models.registers import REGISTER_CONFIG_BY_KEY
    from app.repositories.capture_repository import GridRepository
    from app.repositories.daily_report_repository import DailyReportRepository
    from app.services.benchmarking import benchmark_field

    # --- benchmark rows keyed by event ---------------------------------------
    bench = {r["event_id"]: r for r in benchmark_field(db)}

    # --- spud ordering + well labels -----------------------------------------
    evs = db.execute(select(Event)).scalars().all()

    def _label(ev):
        wb = db.get(Wellbore, ev.wellbore_id) if ev.wellbore_id else None
        well = db.get(Well, wb.well_id) if wb else None
        return (well.legal_well_name if well and well.legal_well_name else None) or ev.event_code or str(ev.id)

    labels = {str(ev.id): _label(ev) for ev in evs}
    # Order by spud (start_date); events without a date sort last but keep a
    # stable order so the chronological index is deterministic.
    ordered = sorted(evs, key=lambda e: (e.start_date is None, e.start_date or 0, str(e.id)))

    # --- learning sequence ----------------------------------------------------
    wells = []
    n = 0
    for ev in ordered:
        eid = str(ev.id)
        row = bench.get(eid)
        if not row:
            continue  # only wells with captured operations enter the curve
        md = _f(row.get("final_md"))
        days = _f(row.get("days"))
        cost = _f(row.get("cost"))
        cost_per_ft = round(cost / md, 1) if (cost is not None and md) else _f(row.get("cost_per_ft"))
        days_per_1000ft = round(days / (md / 1000.0), 2) if (days is not None and md) else _f(row.get("days_per_1000ft"))
        avg_ft_per_day = round(md / days, 1) if (md is not None and days) else _f(row.get("avg_ft_per_day"))
        n += 1
        wells.append({
            "n": n,
            "well": labels.get(eid, eid),
            "spud": ev.start_date.isoformat() if ev.start_date else None,
            "cost_per_ft": cost_per_ft,
            "days_per_1000ft": days_per_1000ft,
            "avg_ft_per_day": avg_ft_per_day,
            "final_md": md,
            "days": round(days, 1) if days is not None else None,
            "npt_pct": _f(row.get("npt_pct")),
        })

    fit_cost = _power_fit([(w["n"], w["cost_per_ft"]) for w in wells if w["cost_per_ft"]])
    fit_days = _power_fit([(w["n"], w["days_per_1000ft"]) for w in wells if w["days_per_1000ft"]])

    # --- by-section aggregation (across every well) --------------------------
    # Per (event, section) accumulate drilling days (rotating+sliding) and
    # footage (progress), then roll up per section across wells.
    per_well_section = {}  # (eid, size) -> {"days":x, "ft":y}
    dr_repo = DailyReportRepository(db)
    for ev in ordered:
        eid = str(ev.id)
        for rep in dr_repo.list_for_event(eid):
            size = _snap_size(rep.hole_size)
            if size is None:
                continue
            rot = _f(rep.rotating_hrs) or 0.0
            sld = _f(rep.sliding_hrs) or 0.0
            prog = _f(rep.progress) or 0.0
            key = (eid, size)
            acc = per_well_section.setdefault(key, {"days": 0.0, "ft": 0.0})
            acc["days"] += (rot + sld) / 24.0
            acc["ft"] += prog

    by_size = {}  # size -> {wells:set, days, ft}
    for (eid, size), acc in per_well_section.items():
        s = by_size.setdefault(size, {"wells": set(), "days": 0.0, "ft": 0.0})
        s["wells"].add(eid)
        s["days"] += acc["days"]
        s["ft"] += acc["ft"]

    sections = []
    for size, s in sorted(by_size.items(), key=lambda kv: -kv[0]):  # largest hole first (top → bottom)
        wc = len(s["wells"]) or 1
        total_days = s["days"]
        total_ft = s["ft"]
        sections.append({
            "section": f'{size:g}"',
            "wells_count": len(s["wells"]),
            "avg_days": round(total_days / wc, 1),
            "avg_ft_per_day": round(total_ft / total_days, 1) if total_days > 0 else None,
            # No per-report cost is captured, so section cost isn't derivable
            # honestly — reported as unavailable rather than fabricated.
            "avg_cost": None,
        })

    # --- lessons mining -------------------------------------------------------
    lesson_model = REGISTER_CONFIG_BY_KEY["lessons-learned"].model
    by_cat = {}  # category -> {count, npt_hours}
    all_lessons = []
    for ev in ordered:
        eid = str(ev.id)
        rows = GridRepository(db, lesson_model, parent_field="event_id").list_for_parent(eid)
        for r in rows:
            cat = getattr(r, "category", None) or "Uncategorised"
            npt = _f(getattr(r, "npt_hours", None)) or 0.0
            c = by_cat.setdefault(cat, {"count": 0, "npt_hours": 0.0})
            c["count"] += 1
            c["npt_hours"] += npt
            all_lessons.append({
                "well": labels.get(eid, eid),
                "category": cat,
                "phase": getattr(r, "phase", None),
                "lesson": getattr(r, "lesson", None) or getattr(r, "event_description", None),
                "recommendation": getattr(r, "recommendation", None),
                "npt_hours": npt,
                "impact": getattr(r, "impact", None),
            })

    lessons_by_category = sorted(
        ({"category": k, "count": v["count"], "npt_hours": round(v["npt_hours"], 1)} for k, v in by_cat.items()),
        key=lambda x: x["npt_hours"], reverse=True,
    )
    top_lessons = sorted(all_lessons, key=lambda x: x["npt_hours"], reverse=True)[:10]
    for t in top_lessons:
        t["npt_hours"] = round(t["npt_hours"], 1)

    return {
        "wells": wells,
        "fit_cost": fit_cost,
        "fit_days": fit_days,
        "sections": sections,
        "lessons_by_category": lessons_by_category,
        "top_lessons": top_lessons,
        "n_wells": len(wells),
        "n_lessons": len(all_lessons),
        "depth_unit": "ft",
    }
