"""EAC / Cost & Time Forecast — earned-value analysis on top of the operational
event metrics. Given the captured actuals (cumulative cost, depth-vs-days) and
the AFE budget + well plan, compute CPI / SPI, the estimate-at-completion (EAC)
family and project the cost and depth curves forward at the current run-rate.

Pure read/derive: consumes ``analytics.event_metrics`` and returns plain
dicts/lists/floats ready to hand straight to the template as JSON. Every value
from the upstream metrics may be ``None`` — everything here is guarded."""
from __future__ import annotations

from typing import Optional


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _pos(v) -> Optional[float]:
    """Return v as a float only when strictly positive — used to guard divisors."""
    f = _num(v)
    return f if (f is not None and f > 0) else None


def _r(v, nd=2) -> Optional[float]:
    f = _num(v)
    return round(f, nd) if f is not None else None


def analyze(db, event_id) -> dict:
    from app.services.event_analytics import event_metrics

    if not event_id:
        return {"ok": False, "error": "No event selected."}

    m = event_metrics(db, event_id)
    k = m.get("kpis") or {}

    bac = _pos(k.get("budget_total"))
    ac = _num(k.get("total_actual_cost"))
    pct_raw = _num(k.get("pct_complete"))          # 0..100 by depth
    days_elapsed = _num(k.get("days_elapsed"))
    planned_days = _pos(k.get("planned_days"))
    planned_final_md = _pos(k.get("planned_final_md"))
    current_md = _num(k.get("current_md"))
    cost_pct = _num(k.get("cost_pct"))

    # --- Need the AFE budget and a physical %-complete to earn value at all ---
    if bac is None:
        return {"ok": False, "error": "No AFE budget set on the well plan — cannot compute earned value.",
                "cost_forecast": [], "depth_forecast": []}
    if pct_raw is None:
        return {"ok": False, "error": "No depth / plan data to measure %-complete — cannot forecast.",
                "cost_forecast": [], "depth_forecast": []}

    pct = max(0.0, min(1.0, pct_raw / 100.0))       # physical fraction complete
    ac = ac if ac is not None else 0.0

    # --- Earned value core ---
    ev = pct * bac                                   # earned value (BCWP)
    if planned_days and days_elapsed is not None:
        pv = bac * max(0.0, min(1.0, days_elapsed / planned_days))
    else:
        pv = bac * pct                               # fallback: no schedule baseline
    pv = pv or 0.0

    cpi = ev / ac if ac > 0 else None                # cost performance index
    spi = ev / pv if pv > 0 else None                # schedule performance index

    eac_cpi = bac / cpi if (cpi and cpi > 0) else None
    eac_composite = ac + (bac - ev) / cpi if (cpi and cpi > 0) else None
    etc = (eac_cpi - ac) if eac_cpi is not None else None
    vac = (bac - eac_cpi) if eac_cpi is not None else None

    # --- Schedule forecast: two independent estimates ---
    forecast_days = planned_days / spi if (planned_days and spi and spi > 0) else None
    linear_forecast_days = days_elapsed / pct if (days_elapsed is not None and pct > 0) else None
    # day we forecast the job to finish on (best available estimate)
    final_day = forecast_days or linear_forecast_days or planned_days or days_elapsed

    kpis = {
        "BAC": _r(bac), "AC": _r(ac), "EV": _r(ev), "PV": _r(pv),
        "CPI": _r(cpi, 3), "SPI": _r(spi, 3),
        "EAC_cpi": _r(eac_cpi), "EAC_composite": _r(eac_composite),
        "ETC": _r(etc), "VAC": _r(vac),
        "forecast_days": _r(forecast_days, 1),
        "linear_forecast_days": _r(linear_forecast_days, 1),
        "planned_days": _r(planned_days, 1),
        "days_elapsed": _r(days_elapsed, 1),
        "pct_complete": _r(pct_raw, 1),
        "cost_pct": _r(cost_pct, 1),
    }

    cost_forecast = _build_cost_forecast(m.get("cost_series") or [], ac, days_elapsed,
                                         final_day, eac_cpi, bac)
    depth_forecast = _build_depth_forecast(m.get("actual_depth") or [], m.get("planned_depth") or [],
                                           current_md, days_elapsed, planned_final_md, final_day)

    ok = bool(cost_forecast) or bool(depth_forecast)
    return {"ok": ok, "kpis": kpis, "cost_forecast": cost_forecast, "depth_forecast": depth_forecast,
            "final_day": _r(final_day, 1)}


def _build_cost_forecast(cost_series, ac, days_elapsed, final_day, eac, bac) -> list[dict]:
    """Actual cumulative cost vs a run-rate projection to the forecast final day.

    ``actual`` is populated only on days already reported; ``forecast`` runs from
    the last actual point forward (so the two lines join) up to ``final_day``,
    scaled so it lands on the EAC when we have one."""
    pts = [{"day": _num(p.get("day")), "cum": _num(p.get("cumulative"))}
           for p in cost_series if _num(p.get("day")) is not None and _num(p.get("cumulative")) is not None]
    pts.sort(key=lambda p: p["day"])
    if not pts:
        return []

    last_day = pts[-1]["day"]
    last_cum = pts[-1]["cum"]

    # run-rate slope ($/day): prefer the observed cumulative/day, fall back to AC/elapsed
    slope = None
    if last_day and last_day > 0:
        slope = last_cum / last_day
    elif days_elapsed and days_elapsed > 0 and ac is not None:
        slope = ac / days_elapsed

    end_day = final_day if (final_day and final_day > last_day) else last_day
    # target end value: land on EAC when available, else project at the run-rate
    if eac is not None and eac >= last_cum and end_day > last_day:
        proj_slope = (eac - last_cum) / (end_day - last_day)
    else:
        proj_slope = slope if slope is not None else 0.0

    rows = [{"day": round(p["day"], 2), "actual": round(p["cum"], 2), "forecast": None} for p in pts]
    # anchor the forecast line on the last actual point so the two curves meet
    rows[-1]["forecast"] = round(last_cum, 2)

    if end_day > last_day:
        step = max(1.0, (end_day - last_day) / 12.0)
        d = last_day + step
        while d < end_day - 1e-9:
            rows.append({"day": round(d, 2), "actual": None,
                         "forecast": round(last_cum + proj_slope * (d - last_day), 2)})
            d += step
        rows.append({"day": round(end_day, 2), "actual": None,
                     "forecast": round(last_cum + proj_slope * (end_day - last_day), 2)})
    rows.sort(key=lambda r: r["day"])
    return rows


def _build_depth_forecast(actual_depth, planned_depth, current_md, days_elapsed,
                          planned_final_md, final_day) -> list[dict]:
    """MD-vs-day: actual, planned baseline and a run-rate projection to TD.

    Forecast extends the actual depth curve linearly at the current making-hole
    rate until it reaches the planned final MD (or the forecast final day)."""
    act = [{"day": _num(p.get("day")), "md": _num(p.get("md"))}
           for p in actual_depth if _num(p.get("day")) is not None and _num(p.get("md")) is not None]
    act.sort(key=lambda p: p["day"])
    plan = [{"day": _num(p.get("day")), "md": _num(p.get("md"))}
            for p in planned_depth if _num(p.get("day")) is not None and _num(p.get("md")) is not None]

    rows: dict[float, dict] = {}

    def row(day):
        return rows.setdefault(round(day, 2), {"day": round(day, 2), "actual": None,
                                               "planned": None, "forecast": None})

    for p in act:
        row(p["day"])["actual"] = round(p["md"], 2)
    for p in plan:
        row(p["day"])["planned"] = round(p["md"], 2)

    # --- run-rate projection from the last actual point ---
    if act:
        last_day = act[-1]["day"]
        last_md = act[-1]["md"]
        slope = None
        if last_day and last_day > 0:
            slope = last_md / last_day
        elif days_elapsed and days_elapsed > 0 and current_md is not None and current_md > 0:
            slope = current_md / days_elapsed

        # already at/through TD → no projection to draw
        need_forecast = not (planned_final_md and last_md >= planned_final_md)
        if slope and slope > 0 and need_forecast:
            if planned_final_md and planned_final_md > last_md:
                end_day = last_md / slope + (planned_final_md - last_md) / slope
                end_md = planned_final_md
            else:
                end_day = final_day if (final_day and final_day > last_day) else last_day
                end_md = last_md + slope * (end_day - last_day)
            row(last_day)["forecast"] = round(last_md, 2)   # anchor on last actual
            if end_day > last_day:
                step = max(1.0, (end_day - last_day) / 12.0)
                d = last_day + step
                while d < end_day - 1e-9:
                    row(d)["forecast"] = round(last_md + slope * (d - last_day), 2)
                    d += step
                row(end_day)["forecast"] = round(end_md, 2)

    return [rows[d] for d in sorted(rows)]
