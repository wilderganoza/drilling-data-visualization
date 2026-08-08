"""Plan-vs-Actual variance for an Event — closes the loop between the plan
(time-depth curve, AFE budget, casing seat depths) and what actually happened
(daily MD, cumulative cost, casing run). Builds on `event_metrics` for the
aggregate KPIs and adds the day-by-day depth table and the casing comparison."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.capture import CONFIG_BY_KEY
from app.models.planning_capture import PLAN_CONFIG_BY_KEY
from app.repositories.capture_repository import GridRepository
from app.repositories.daily_report_repository import DailyReportRepository
from app.services.event_analytics import event_metrics


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _plan_md_at_day(planned: list[dict], day: int) -> Optional[float]:
    """Interpolate planned MD at a given day number from the time-depth plan."""
    pts = sorted([(p.get("day"), p.get("md") if p.get("md") is not None else p.get("planned_md"))
                  for p in planned if p.get("day") is not None], key=lambda x: x[0])
    pts = [(d, m) for d, m in pts if m is not None]
    if not pts:
        return None
    if day <= pts[0][0]:
        return pts[0][1]
    for (d1, m1), (d2, m2) in zip(pts, pts[1:]):
        if d1 <= day <= d2 and d2 != d1:
            return round(m1 + (m2 - m1) * (day - d1) / (d2 - d1), 1)
    return pts[-1][1]


def compute_variance(db: Session, event_id: str) -> dict:
    metrics = event_metrics(db, event_id)
    k = metrics["kpis"]

    # --- day-by-day depth table (actual vs planned MD, behind/ahead) ---
    actual = metrics.get("actual_depth", [])
    planned = metrics.get("planned_depth", [])
    day_rows = []
    for i, a in enumerate(actual, start=1):
        amd = a.get("md")
        pmd = _plan_md_at_day(planned, i)
        delta = round(amd - pmd, 1) if (amd is not None and pmd is not None) else None
        day_rows.append({"day": i, "date": a.get("date"), "actual_md": amd,
                         "planned_md": pmd, "delta": delta,
                         "status": ("ahead" if (delta is not None and delta >= 0) else "behind") if delta is not None else None})

    # --- casing: planned seat vs actual shoe run ---
    planned_casing = GridRepository(db, PLAN_CONFIG_BY_KEY["casing-program"].model, parent_field="event_id").list_for_parent(event_id)
    actual_by_string: dict[str, float] = {}
    run_cfg = CONFIG_BY_KEY.get("casing-running")
    if run_cfg:
        for rep in DailyReportRepository(db).list_for_event(event_id):
            for r in GridRepository(db, run_cfg.model, parent_field="daily_report_id").list_for_parent(rep.id):
                s = (r.string or "").strip()
                shoe = _f(r.actual_shoe_md)
                if s and shoe is not None:
                    actual_by_string[s] = shoe  # latest run wins
    casing = []
    for c in planned_casing:
        s = (c.string or "").strip()
        planned_shoe = _f(c.setting_md)
        actual_shoe = actual_by_string.get(s)
        delta = round(actual_shoe - planned_shoe, 1) if (actual_shoe is not None and planned_shoe is not None) else None
        casing.append({"string": s or "—", "od_in": _f(c.od_in), "planned_shoe": planned_shoe,
                       "actual_shoe": actual_shoe, "delta": delta,
                       "status": ("run" if actual_shoe is not None else "pending")})

    cost = {"actual": k.get("total_actual_cost"), "budget": k.get("budget_total"),
            "pct": k.get("cost_pct"),
            "variance": (round(k["total_actual_cost"] - k["budget_total"], 0)
                         if k.get("total_actual_cost") is not None and k.get("budget_total") else None)}

    return {"metrics": metrics, "kpis": k, "day_rows": day_rows, "casing": casing, "cost": cost}
