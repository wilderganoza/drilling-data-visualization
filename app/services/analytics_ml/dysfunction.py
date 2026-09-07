"""Drilling dysfunction detection — screening heuristics on the DAILY drilling
record (founder / bit dulling, bit balling, stick-slip, washout / pack-off).

HONEST SCOPE: true stick-slip and bit-balling detection needs high-frequency
(seconds) surface & downhole data. This module screens the daily captured
drilling-parameter record with physics-based heuristics on MSE, ROP, SPP and
torque trends versus the previous point / running references. Flags are
indicative, not definitive.

Contract: analyze(db, event_id) -> dict with keys
    ok, error?, flags, health_score, series, summary, coarse
"""
from __future__ import annotations

# Importamos statistics para calcular la mediana de las relaciones torque/WOB
import statistics

# Importamos el catálogo de grids de captura para ubicar la config de "drill-params"
from app.models.capture import CONFIG_BY_KEY
# Importamos el repositorio genérico de grids para leer las filas de drill-params
from app.repositories.capture_repository import GridRepository
# Importamos el repositorio de reportes diarios para recorrer los reportes del evento
from app.repositories.daily_report_repository import DailyReportRepository
# Importamos sensor_source para preferir los datos reales de sensores (well_data) cuando existen
from app.services.analytics_ml import sensor_source

_SEV_WEIGHT = {"High": 12, "Medium": 7, "Low": 3}


def _f(v):
    """Coerce a Numeric/None DB value to float or None."""
    # Si el valor es None, no hay nada que convertir
    if v is None:
        return None
    # Intentamos convertir a float; si falla, tratamos el valor como ausente
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _median(vals):
    # Descartamos los valores None antes de calcular la mediana
    vals = [v for v in vals if v is not None]
    # Devolvemos la mediana solo si quedó al menos un valor
    return statistics.median(vals) if vals else None


def analyze(db, event_id, domain="depth") -> dict:
    # Inicializamos la fuente por defecto (drill-params capturado) y la lista de puntos
    source = "drill-params"
    sensor_note = None
    points: list[dict] = []

    # Prefer the real sensor record (well_data via the well's legacy link).
    # Preferimos el registro real de sensores (well_data via el enlace legacy del pozo)
    sd = sensor_source.drilling_points(db, event_id, domain=domain)
    if sd["points"]:
        # Si hay datos de sensores, los usamos como fuente principal
        points = sd["points"]
        source = sd["source"]
        # Anotamos qué chequeos quedan limitados por no tener torque de superficie medido
        sensor_note = ("Real sensor data ({:,} pts). Surface torque is not measured, so MSE-founder "
                       "and stick-slip checks are unavailable; bit-balling and washout screening use "
                       "ROP / SPP.").format(sd["n"])
    else:
        # Si no hay datos de sensores, caemos al grid de drill-params capturado manualmente
        model = CONFIG_BY_KEY["drill-params"].model
        for report in DailyReportRepository(db).list_for_event(event_id):
            # Recorremos las filas del grid de drill-params de cada reporte diario
            rows = GridRepository(db, model, parent_field="daily_report_id").list_for_parent(report.id)
            for r in rows:
                # Convertimos cada fila a un dict con los campos numéricos coercionados
                points.append({
                    "depth_md": _f(r.depth_md), "formation": r.formation, "bit_size": _f(r.bit_size),
                    "wob": _f(r.wob), "rpm": _f(r.rpm), "flow_gpm": _f(r.flow_gpm),
                    "torque_ftlb": _f(r.torque_ftlb), "spp_psi": _f(r.spp_psi),
                    "rop": _f(r.rop), "mse_ksi": _f(r.mse_ksi),
                })

    # Si no encontramos ningún punto (ni sensores ni drill-params), devolvemos un error controlado
    if not points:
        return {"ok": False, "error": "No drilling data for this well. Capture drill-params, or link "
                "the well to a sensor dataset.", "flags": [], "series": [], "health_score": None,
                "source": "none", "sensor_note": None}

    # Sort by measured depth; points without a depth sink to the end (stable).
    # Ordenamos por profundidad medida; los puntos sin profundidad quedan al final (orden estable)
    points.sort(key=lambda p: (p["depth_md"] is None,
                               p["depth_md"] if p["depth_md"] is not None else 0.0))

    n = len(points)

    def _missing_frac(key: str) -> float:
        # Calculamos la fracción de puntos a los que les falta este campo
        return sum(1 for p in points if p[key] is None) / n

    # Coarse: the interesting fields are mostly blank — heuristics get thin.
    # Marcamos el análisis como "coarse" (grueso) cuando WOB o torque faltan en más de la mitad de los puntos
    coarse = _missing_frac("wob") > 0.5 or _missing_frac("torque_ftlb") > 0.5

    # Median torque/WOB ratio for the stick-slip screen. We flag a genuine
    # deviation from the norm (ratio >> median), NOT simply the top decile —
    # torque rising in proportion to WOB/depth is normal, not a dysfunction.
    # Calculamos la mediana de la relación torque/WOB para usarla como norma del pozo
    ratios = [p["torque_ftlb"] / p["wob"]
              for p in points
              if p["torque_ftlb"] is not None and p["wob"] and p["wob"] > 0]
    # Solo confiamos en la mediana si hay al menos 5 relaciones válidas
    ratio_med = _median(ratios) if len(ratios) >= 5 else None

    flags: list[dict] = []

    def add(p, typ, sev, evidence):
        # Agregamos una alerta con su profundidad, tipo, severidad y evidencia
        flags.append({
            "depth_md": round(p["depth_md"], 1) if p["depth_md"] is not None else None,
            "formation": p["formation"],
            "type": typ,
            "severity": sev,
            "evidence": evidence,
        })

    prev = None
    for i, p in enumerate(points):
        # Only compare consecutive points drilled with the SAME bit size — a
        # hole-size change (e.g. 17.5"→12.25") legitimately jumps MSE/SPP and
        # would otherwise raise false founder/balling/washout flags.
        # Treat unknown bit size (e.g. sensor data has no bit_size) as the same
        # bit — only a KNOWN size change should reset the comparison.
        # Verificamos que el punto actual y el anterior compartan el mismo tamaño de broca
        same_bit = (prev is not None and (
            p["bit_size"] is None or prev["bit_size"] is None
            or abs(p["bit_size"] - prev["bit_size"]) < 0.1))
        if prev is not None and same_bit:
            # Extraemos los valores actuales y previos de MSE, ROP, SPP y WOB para comparar
            mse, pmse = p["mse_ksi"], prev["mse_ksi"]
            rop, prop = p["rop"], prev["rop"]
            spp, pspp = p["spp_psi"], prev["spp_psi"]
            wob, pwob = p["wob"], prev["wob"]

            # --- Founder / bit dulling: MSE rising materially while ROP falls ---
            # (a small tick between formations is normal — require a >=15% MSE rise)
            # Detectamos founder/desgaste de broca cuando el MSE sube y el ROP baja a la vez
            if None not in (mse, pmse, rop, prop) and mse > pmse and rop < prop:
                base = pmse if pmse else 1.0
                pct = (mse - pmse) / base * 100
                # Solo alertamos si la subida de MSE es material (>=15%)
                if pct >= 15:
                    sev = "High" if pct >= 50 else "Medium" if pct >= 30 else "Low"
                    add(p, "Founder / bit dulling", sev,
                        f"MSE {pmse:.0f}->{mse:.0f} ksi (+{pct:.0f}%), ROP {prop:.0f}->{rop:.0f} ft/hr")

            # --- Bit balling: material ROP drop + SPP rise + WOB not decreasing ---
            # Detectamos embolamiento de broca cuando el ROP cae y la SPP sube a la vez
            if None not in (rop, prop, spp, pspp) and rop < prop and spp > pspp:
                # Verificamos que el WOB no haya bajado (embolamiento no se explica por menos peso)
                wob_ok = wob is None or pwob is None or wob >= pwob
                spp_pct = (spp - pspp) / pspp * 100 if pspp else 0.0
                rop_pct = (prop - rop) / prop * 100 if prop else 0.0
                if wob_ok and spp_pct >= 10 and rop_pct >= 20:
                    sev = "High" if spp_pct >= 18 and rop_pct >= 35 else "Medium"
                    wob_note = "WOB up" if (wob is not None and pwob is not None and wob > pwob) else "WOB steady"
                    add(p, "Bit balling", sev,
                        f"ROP -{rop_pct:.0f}% ({prop:.0f}->{rop:.0f}), "
                        f"SPP +{spp_pct:.0f}% ({pspp:.0f}->{spp:.0f} psi), {wob_note}")

            # --- Washout / pack-off: SPP jump >~15% without a flow change ---
            # Detectamos washout/pack-off cuando la SPP salta sin que el caudal haya cambiado
            if None not in (spp, pspp) and pspp > 0:
                spp_jump = (spp - pspp) / pspp * 100
                flow, pflow = p["flow_gpm"], prev["flow_gpm"]
                flow_change = flow is not None and pflow and abs(flow - pflow) / pflow * 100 > 5
                if spp_jump > 15 and not flow_change:
                    sev = "High" if spp_jump > 30 else "Medium"
                    add(p, "Washout / pack-off", sev,
                        f"SPP +{spp_jump:.0f}% ({pspp:.0f}->{spp:.0f} psi) with flow ~steady")

        # --- Stick-slip screen: torque/WOB ratio well above the well's norm ---
        # (proportional torque growth with WOB/depth is normal; flag only a
        # genuine excursion, ratio >= 1.5x the median ratio).
        # Comparamos la relación torque/WOB del punto contra la mediana del pozo
        tq, wob = p["torque_ftlb"], p["wob"]
        if tq is not None and ratio_med and wob and wob > 0:
            ratio = tq / wob
            if ratio >= 1.5 * ratio_med:
                sev = "Medium" if ratio >= 1.8 * ratio_med else "Low"
                add(p, "Stick-slip (screening)", sev,
                    f"torque/WOB {ratio:.0f} vs norm {ratio_med:.0f} "
                    f"(torque {tq:.0f} ft-lbf) — daily avg, screening only")

        prev = p

    # Calculamos el health score restando el peso de severidad de cada alerta desde 100
    score = 100
    for fl in flags:
        score -= _SEV_WEIGHT.get(fl["severity"], 0)
    health_score = max(0, score)

    # Armamos la serie de puntos que alimenta los gráficos del dashboard
    series = [{"depth_md": p["depth_md"], "mse_ksi": p["mse_ksi"], "rop": p["rop"],
               "torque_ftlb": p["torque_ftlb"], "spp_psi": p["spp_psi"]} for p in points]

    # Contamos cuántas alertas hay de cada tipo para el resumen
    by_type: dict[str, int] = {}
    for fl in flags:
        by_type[fl["type"]] = by_type.get(fl["type"], 0) + 1

    # Devolvemos el resultado completo del análisis de disfunciones
    return {
        "ok": True,
        "flags": flags,
        "health_score": health_score,
        "series": series,
        "summary": {"n_points": n, "n_flags": len(flags), "by_type": by_type},
        "coarse": coarse,
        "source": source,
        "sensor_note": sensor_note,
    }
