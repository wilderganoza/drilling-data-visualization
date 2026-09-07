"""Derived operational alerts from an event's metrics (see analytics.py).
Pure function over the metrics dict — no DB access. Levels: 'danger' (needs
attention now), 'warning' (watch), 'info' (context)."""
# Importamos Optional para tipar el monto que puede venir ausente en _money
from typing import Optional


def _alert(level: str, title: str, message: str) -> dict:
    # Empaquetamos la alerta en un diccionario simple (nivel, título, mensaje)
    return {"level": level, "title": title, "message": message}


def event_alerts(metrics: dict) -> list[dict]:
    # Extraemos los KPIs del diccionario de métricas del evento
    k = metrics.get("kpis", {})
    out: list[dict] = []

    # Evaluamos el estado del presupuesto AFE (avisamos si falta o si se acerca/supera el límite)
    cost_pct = k.get("cost_pct")
    budget = k.get("budget_total")
    if budget is None:
        out.append(_alert("info", "No AFE budget", "Set the AFE budget total in Planning to enable cost tracking."))
    elif cost_pct is not None:
        if cost_pct >= 100:
            out.append(_alert("danger", "Over AFE budget", f"Actual cost is {cost_pct:.0f}% of the AFE ({_money(k.get('total_actual_cost'))} of {_money(budget)})."))
        elif cost_pct >= 90:
            out.append(_alert("warning", "Approaching AFE budget", f"Actual cost is {cost_pct:.0f}% of the AFE budget."))

    # Evaluamos el tiempo no productivo (NPT) del evento contra umbrales de alerta
    npt_pct = k.get("npt_pct")
    if npt_pct is not None:
        if npt_pct >= 20:
            out.append(_alert("danger", "High NPT", f"Non-productive time is {npt_pct:.0f}% of total time ({k.get('npt_hours')} h across {k.get('npt_events')} events)."))
        elif npt_pct >= 10:
            out.append(_alert("warning", "Elevated NPT", f"Non-productive time is {npt_pct:.0f}% of total time."))

    # Evaluamos el atraso/adelanto respecto a la curva de tiempo-profundidad planeada
    dd = k.get("days_delta")
    if dd is not None:
        if dd >= 3:
            out.append(_alert("danger", "Behind schedule", f"{dd:.0f} days behind the planned time-depth curve."))
        elif dd >= 1:
            out.append(_alert("warning", "Slipping vs plan", f"{dd:.0f} day(s) behind plan."))
        elif dd <= -1:
            out.append(_alert("info", "Ahead of schedule", f"{abs(dd):.0f} day(s) ahead of plan."))

    # Avisamos cuando el pozo se acerca a la profundidad final planeada (TD)
    pct = k.get("pct_complete")
    if pct is not None and 95 <= pct < 100:
        out.append(_alert("info", "Approaching TD", f"At {pct:.0f}% of planned final depth."))

    # Ordenamos las alertas mostrando primero las más críticas (danger, luego warning, luego info)
    order = {"danger": 0, "warning": 1, "info": 2}
    out.sort(key=lambda a: order.get(a["level"], 3))
    # Devolvemos la lista de alertas ya ordenada
    return out


def _money(v: Optional[float]) -> str:
    # Formateamos el monto como moneda; si no hay valor, mostramos un guion largo
    if v is None:
        return "—"
    return "${:,.0f}".format(v)
