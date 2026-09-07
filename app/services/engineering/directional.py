"""Directional design & anti-collision — a GENERATOR module.

From the trajectory-design inputs (KOP, build rate, tangent inclination, target
azimuth, TD) it builds a build-and-hold well path, runs minimum-curvature to get
TVD/N-S/E-W/DLS, and can write those stations straight into the Directional Plan
program grid ("Apply to program") — the way WellPlan generates the plan. It then
runs anti-collision of that path against the offset wells' plans (ISCWSA-style
separation factor at pad-slot offsets)."""
# Importamos math para trigonometría (cierre, azimut de cierre, separación angular)
import math
# Importamos dataclass para describir cada input del formulario de diseño
from dataclasses import dataclass

# Importamos WellContext, el contexto con el plan, casing y pozos vecinos
from app.services.engineering.context import WellContext
# Importamos recompute_survey, el motor de mínima curvatura compartido con Planning
from app.services.survey_calc import recompute_survey

PROGRAM_TARGETS = ["directional-plan"]  # this module generates the Directional Plan grid


def context_defaults(ctx) -> dict:
    """Seed the design inputs from the well-plan header so the generated
    trajectory starts coherent with the plan intent (KOP, target, TD)."""
    p = ctx.plan
    if not p:
        # Sin plan de pozo cargado no hay valores por defecto que sembrar
        return {}
    out = {}
    if p.kop_md is not None:
        # Tomamos el punto de desviación (KOP) declarado en el plan
        out["kop"] = float(p.kop_md)
    if p.max_inclination is not None:
        # Usamos la inclinación máxima del plan como inclinación de tangente por defecto
        out["tangent_inc"] = float(p.max_inclination)
    if p.target_azimuth is not None:
        # Tomamos el azimut objetivo del plan
        out["azimuth"] = float(p.target_azimuth)
    if p.authorized_md is not None:
        # Tomamos la profundidad total autorizada como TD por defecto
        out["td_md"] = float(p.authorized_md)
    return out


# Definimos la estructura de cada input del formulario de diseño direccional
@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


# Declaramos los inputs del diseño (KOP, build rate, azimut, TD, parámetros de anticolisión, etc.)
INPUTS = [
    Inp("kop", "Kick-off point (KOP)", 3400, "ft"),
    Inp("build_rate", "Build rate", 2.5, "°/100ft"),
    Inp("tangent_inc", "Tangent inclination", 22, "°"),
    Inp("azimuth", "Target azimuth", 142, "°"),
    Inp("td_md", "Total depth (MD)", 8900, "ft"),
    Inp("station_step", "Station interval", 200, "ft"),
    Inp("slot_spacing", "Pad slot spacing", 30, "ft"),
    Inp("slot_azimuth", "Slot layout azimuth", 90, "°"),
    Inp("uncertainty_pct", "Position uncertainty (of MD)", 0.5, "%"),
    Inp("dls_limit", "DLS alarm limit", 3.0, "°/100ft"),
    Inp("sf_alarm", "Separation-factor alarm", 1.5, ""),
]


def _generate_stations(kop, build_rate, tangent_inc, azimuth, td, step):
    """Build-and-hold path: vertical → build at build_rate to tangent_inc → hold."""
    # Forzamos un paso mínimo de 50 ft entre estaciones
    step = max(step, 50)
    # Calculamos la longitud de la sección de build a partir de la tasa de construcción
    build_len = (tangent_inc / build_rate) * 100 if build_rate > 0 else 0
    eob = kop + build_len
    out = {}

    def add(md, inc):
        # Guardamos la estación, acotando la inclinación entre 0 y la inclinación de tangente
        out[round(md, 1)] = (round(min(max(inc, 0), tangent_inc), 2), azimuth)

    # Tramo vertical: inclinación 0 hasta el KOP
    md = 0.0
    while md < kop:
        add(md, 0.0); md += step
    add(kop, 0.0)
    # Tramo de build: la inclinación crece linealmente con la tasa de construcción
    md = kop + step
    while md < eob:
        add(md, (md - kop) / 100.0 * build_rate); md += step
    add(eob, tangent_inc)
    # Tramo de hold: inclinación de tangente constante hasta el TD
    md = eob + step
    while md < td:
        add(md, tangent_inc); md += step
    add(td, tangent_inc)
    # Devolvemos las estaciones ordenadas por profundidad, con los campos calculados aún vacíos
    return [{"md": m, "inclination": v[0], "azimuth": v[1], "tvd": None, "ns": None, "ew": None, "dls": None}
            for m, v in sorted(out.items())]


def generate_rows(params: dict, ctx: WellContext, target: str = "directional-plan") -> list[dict]:
    """Rows to write into the Directional Plan grid (computed cols filled)."""
    # Completamos cada input con su valor por defecto si no vino en params
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    rows = _generate_stations(p["kop"], p["build_rate"], p["tangent_inc"], p["azimuth"], p["td_md"], p["station_step"])
    # Creamos una clase liviana ad-hoc para poder pasar las filas por referencia a recompute_survey
    _Row = type("R", (), {})
    objs = []
    for r in rows:
        o = _Row()
        for k, v in r.items():
            setattr(o, k, v)
        objs.append(o)
    recompute_survey(objs)  # fills tvd/ns/ew/dls in place
    # Devolvemos las filas ya con TVD/NS/EW/DLS calculados por mínima curvatura
    return [{"md": o.md, "inclination": o.inclination, "azimuth": o.azimuth,
             "tvd": o.tvd, "ns": o.ns, "ew": o.ew, "dls": o.dls} for o in objs]


def _pts(traj):
    # Convertimos la trayectoria a tuplas (md, tvd, ns, ew) ordenadas, con defaults seguros
    return sorted([(d["md"], d.get("tvd") or d["md"], d.get("ns") or 0.0, d.get("ew") or 0.0)
                   for d in traj if d.get("md") is not None])


def _pos_at_tvd(pts, tvd):
    # Interpolamos la posición (ns, ew, md) en una TVD dada, buscando el segmento que la contiene
    for (m1, t1, n1, e1), (m2, t2, n2, e2) in zip(pts, pts[1:]):
        lo, hi = min(t1, t2), max(t1, t2)
        if lo <= tvd <= hi and t2 != t1:
            f = (tvd - t1) / (t2 - t1)
            return n1 + (n2 - n1) * f, e1 + (e2 - e1) * f, m1 + (m2 - m1) * f
    # Si la TVD no cae en ningún segmento de la trayectoria, no hay posición que devolver
    return None


def compute(params: dict, ctx: WellContext) -> dict:
    # Completamos cada input con su valor por defecto si no vino en params
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    gen = generate_rows(params, ctx)  # the designed trajectory (not the stored grid)

    # Resumimos la trayectoria generada: inclinación máxima, DLS máximo y punto final
    max_inc = max((r["inclination"] or 0) for r in gen)
    dls_max = max((r["dls"] or 0) for r in gen)
    last = gen[-1]
    # Calculamos el cierre (distancia horizontal al TD) y su azimut
    closure = math.sqrt((last["ns"] or 0) ** 2 + (last["ew"] or 0) ** 2)
    closure_azi = (math.degrees(math.atan2(last["ew"] or 0, last["ns"] or 0)) + 360) % 360
    summary = {
        "kop": round(p["kop"]), "max_inc": round(max_inc, 1), "build_rate": p["build_rate"],
        "dls_max": round(dls_max, 2), "td_md": round(p["td_md"]), "td_tvd": round(last["tvd"] or 0),
        "closure": round(closure), "closure_azi": round(closure_azi), "n_stations": len(gen),
        "dls_ok": dls_max <= p["dls_limit"],
    }

    # anti-collision of the designed path vs offset wells
    # Preparamos los puntos de la trayectoria diseñada para la comparación de anticolisión
    pts = _pts([{**r} for r in gen])
    az = math.radians(p["slot_azimuth"])
    collisions, profile, min_sf_overall = [], [], None
    for idx, off in enumerate(ctx.offset_wells):
        # Convertimos la trayectoria del pozo vecino a puntos comparables
        opts = _pts(off["directional"])
        if len(opts) < 2:
            # Sin al menos 2 puntos no podemos interpolar la trayectoria vecina
            continue
        # Ubicamos el slot vecino en el pad según el espaciamiento y azimut de layout
        dx = (idx + 1) * p["slot_spacing"] * math.cos(az)
        dy = (idx + 1) * p["slot_spacing"] * math.sin(az)
        min_sf = min_dist = min_md = None
        step = max(200, int((summary["td_tvd"] or 8000) / 25))
        tvd = 0
        while tvd <= min(summary["td_tvd"] or 0, opts[-1][1]):
            a = _pos_at_tvd(pts, tvd); b = _pos_at_tvd(opts, tvd)
            if a and b:
                # Calculamos la distancia real entre ambos pozos en esta TVD (aplicando el offset del slot)
                dist = math.hypot(a[0] - (b[0] + dx), a[1] - (b[1] + dy))
                # Calculamos la incertidumbre combinada de posición como % de la MD promedio
                unc = (p["uncertainty_pct"] / 100.0) * (a[2] + b[2]) / 2
                # Calculamos el factor de separación (distancia / incertidumbre), estilo ISCWSA
                sf = dist / unc if unc > 0 else 99.9
                if min_sf is None or sf < min_sf:
                    # Guardamos el punto más crítico (menor factor de separación) encontrado hasta ahora
                    min_sf, min_dist, min_md = sf, dist, a[2]
                if idx == 0:
                    # Guardamos el perfil de SF vs TVD solo para el primer pozo vecino (para graficar)
                    profile.append({"tvd": round(tvd), "sf": round(sf, 2)})
            tvd += step
        if min_sf is not None:
            # Registramos el resultado de anticolisión contra este pozo vecino
            collisions.append({"well": off["name"], "min_sf": round(min_sf, 2), "min_dist": round(min_dist, 1),
                               "at_md": round(min_md), "ok": min_sf >= p["sf_alarm"]})
            min_sf_overall = min_sf if min_sf_overall is None else min(min_sf_overall, min_sf)

    # is the generated path already applied to the grid?
    # Comparamos el número de estaciones para saber si la trayectoria ya fue aplicada al grid guardado
    applied = len(ctx.directional) == len(gen)
    # Devolvemos el resumen, las colisiones, el perfil de SF y la trayectoria generada
    return {"summary": summary, "collisions": collisions, "profile": profile,
            "min_sf": round(min_sf_overall, 2) if min_sf_overall is not None else None,
            "sf_alarm": p["sf_alarm"], "slot_spacing": p["slot_spacing"],
            "generated": gen[:], "applied": applied, "n_generated": len(gen)}
