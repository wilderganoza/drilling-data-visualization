"""Swab & surge — tripping pressure surges and the safe trip-speed envelope.

Burkhardt clinging-constant method. As the string is tripped, mud clings to the
pipe and is displaced up (surge, running in) or dragged down (swab, pulling out)
the annulus. The effective mud velocity in the annulus is

  closed end:  Va = Vp·(Kc + do²/(dh²−do²))
  open  end:   Va = Vp·(Kc + (do²−di²)/(dh²−do²))

with Kc≈0.45 the Burkhardt clinging constant and Vp the (peak) pipe velocity.
That equivalent annular velocity is turned into an equivalent circulating rate
Q and the annular frictional pressure loss (power-law field equations, same as
hydraulics) is evaluated over the open-hole annulus. Surge adds to the bottom-
hole pressure (→ ECD, risk of losses vs frac), swab subtracts from it (→ EMW,
risk of a kick vs pore). The maximum safe trip speed is the speed at which the
surge just reaches the frac limit (or swab just reaches pore)."""
# Importamos math para las funciones trigonométricas y raíces de las fórmulas de swab/surge
import math
# Importamos dataclass para declarar la estructura de cada input del formulario
from dataclasses import dataclass

# Importamos WellContext, el perfil compartido del pozo (hole program, TVD, presiones de poro/frac)
from app.services.engineering.context import WellContext


@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


INPUTS = [
    Inp("trip_speed", "Pipe trip speed", 90, "ft/min"),
    Inp("mw", "Mud weight", 9.9, "ppg"),
    Inp("pv", "Plastic viscosity", 18, "cP"),
    Inp("yp", "Yield point", 22, "lbf/100ft²"),
    Inp("dp_od", "Pipe/BHA OD", 5.0, "in"),
    Inp("dp_id", "Pipe ID", 4.276, "in"),
    Inp("hole_size", "Hole/casing ID", 8.5, "in"),
    Inp("closed_end", "Closed end (float)", 1, "1=yes 0=no", "number"),
    Inp("avg_joint", "Stand length", 93, "ft"),
    Inp("acceleration", "Peak/avg velocity factor", 1.5, ""),
]

KC = 0.45  # Burkhardt clinging constant (approximation)


def _powerlaw(pv, yp):
    # Derivamos el índice de flujo n y la consistencia K del modelo de potencia a partir de PV/YP
    n = 3.32 * math.log10((2 * pv + yp) / (pv + yp)) if (pv + yp) > 0 else 1.0
    K = (pv + yp) / (511 ** n)
    return round(n, 3), K


def _v_annulus(q, d2, d1):
    # Calculamos la velocidad en el anular (ft/min) a partir del caudal equivalente y los diámetros
    return 24.51 * q / (d2 * d2 - d1 * d1) if (d2 * d2 - d1 * d1) > 0 else 0


def _crit_v(pv, yp, rho, d):
    # Calculamos la velocidad crítica que separa el régimen laminar del turbulento
    return (1.08 * pv + 1.08 * math.sqrt(pv * pv + 12.34 * d * d * yp * rho)) / (rho * d)


def _dp_annulus(L, pv, yp, rho, q, d2, d1):
    """Annular frictional pressure loss (psi) — power-law field equation with
    laminar/turbulent selected by the critical velocity (same as hydraulics)."""
    # Calculamos la velocidad anular para este tramo
    v = _v_annulus(q, d2, d1)
    gap = d2 - d1
    # Guardamos contra división por cero cuando el gap o la longitud del tramo no son válidos
    if gap <= 0 or L <= 0:
        return 0.0, v
    # Calculamos la caída de presión laminar y turbulenta en el anular
    lam = (L * pv * v) / (60000 * gap * gap) + (L * yp) / (200 * gap)
    turb = (7.7e-5 * rho ** 0.8 * q ** 1.8 * pv ** 0.2 * L) / (gap ** 3 * (d2 + d1) ** 1.8)
    # Elegimos el régimen (laminar/turbulento) comparando contra la velocidad crítica
    return (turb if v > _crit_v(pv, yp, rho, gap) else lam), v


def _clinging_frac(do, di, dh, closed):
    """Fraction of pipe velocity seen by the annular mud (Burkhardt)."""
    denom = dh * dh - do * do
    # Guardamos contra división por cero cuando el hueco no es mayor que el OD de la tubería
    if denom <= 0:
        return 0.0
    # Distinguimos extremo cerrado (float) de extremo abierto para la constante de Burkhardt
    if closed:
        return KC + do * do / denom
    return KC + (do * do - di * di) / denom


def context_defaults(ctx: WellContext) -> dict:
    """Seed the trip mud weight from the shared pore profile (pore + trip margin)."""
    # Si no hay perfil de geopresión compartido, no sembramos ningún valor por defecto
    if not ctx.has_geopressure():
        return {}
    tvd = ctx.td_tvd()
    # Leemos la presión de poro en el TVD de profundidad total (TD)
    pore = ctx.pore_at(tvd) if tvd else None
    if pore is None:
        return {}
    # Sugerimos un peso de lodo con un margen de viaje (trip margin) de 0.4 ppg sobre la presión de poro
    return {"mw": round(pore + 0.4, 1)}


def compute(params: dict, ctx: WellContext) -> dict:
    # Completamos cada input con su valor por defecto y lo convertimos a float
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    mw, pv, yp = p["mw"], p["pv"], p["yp"]
    do, di = p["dp_od"], p["dp_id"]
    closed = p["closed_end"] >= 0.5
    vp = p["trip_speed"] * p["acceleration"]  # peak pipe velocity (ft/min)

    td = ctx.td() or 10000
    tvd_td = ctx.td_tvd() or td

    # Sections to integrate the annular loss over: prefer the real hole program,
    # else a single conservative section spanning TD at the input hole size.
    # Armamos las secciones sobre las que integrar la pérdida anular, priorizando el hole program real
    sections = []
    for h in ctx.hole:
        dh = h.get("hole_size_in"); top = h.get("top_md"); bot = h.get("bottom_md")
        # Saltamos secciones sin datos suficientes (tamaño de hueco o profundidades faltantes/ inválidas)
        if not dh or top is None or bot is None or bot <= top:
            continue
        sections.append({"section": h.get("section"), "dh": dh, "top": top, "bot": bot})
    # Si no hay hole program, usamos una única sección conservadora que cubre todo el TD
    if not sections:
        sections = [{"section": "Open hole", "dh": p["hole_size"], "top": 0.0, "bot": td}]

    def pore_at(tvd):
        # Leemos la presión de poro del perfil compartido, o estimamos con un margen bajo el MW
        v = ctx.pore_at(tvd) if ctx.has_geopressure() else None
        return v if v is not None else round(mw - 0.5, 2)

    def frac_at(tvd):
        # Leemos la presión de fractura del perfil compartido, o estimamos con un margen sobre el MW
        v = ctx.frac_at(tvd) if ctx.has_geopressure() else None
        return v if v is not None else round(mw + 3.0, 2)

    # Per-section clinging displacement → equivalent Q → frictional ΔP, cumulative.
    # Recorremos cada sección: desplazamiento por adherencia -> caudal equivalente -> ΔP friccional, acumulado
    cum_dp = 0.0
    va_last = 0.0
    q_last = 0.0
    profile = []
    for s in sections:
        dh = s["dh"]
        frac = _clinging_frac(do, di, dh, closed)
        va = vp * frac                                   # ft/min
        q = va * (dh * dh - do * do) / 24.51             # gpm (inverse of _v_annulus)
        dp, _ = _dp_annulus(s["bot"] - s["top"], pv, yp, mw, q, dh, do)
        cum_dp += dp
        va_last, q_last = va, q
        tvd_bot = ctx.tvd_at(s["bot"]) or s["bot"]
        d = (cum_dp / (0.052 * tvd_bot)) if tvd_bot else 0.0
        # Guardamos el punto del perfil con las EMW de surge/swab y la ventana de poro/frac en este TVD
        profile.append({
            "section": s["section"], "md": round(s["bot"]), "tvd": round(tvd_bot),
            "surge_emw": round(mw + d, 2), "swab_emw": round(mw - d, 2),
            "pore": round(pore_at(tvd_bot), 2), "frac": round(frac_at(tvd_bot), 2),
        })

    # La magnitud friccional es la misma para surge y swab; solo cambia el signo sobre la BHP
    surge_dp = cum_dp
    swab_dp = cum_dp  # same frictional magnitude, opposite sign on BHP
    dh_bhp = 0.052 * tvd_td
    # Calculamos las EMW de surge (suma) y swab (resta) en el TD
    surge_emw = mw + surge_dp / dh_bhp if dh_bhp else mw
    swab_emw = mw - swab_dp / dh_bhp if dh_bhp else mw

    pore_emw = pore_at(tvd_td)
    frac_emw = frac_at(tvd_td)

    # Max safe trip speed — linear scale of the computed case to the window limit.
    # Escalamos linealmente la velocidad calculada hasta el límite de la ventana (frac para surge, poro para swab)
    if surge_dp > 0:
        max_surge_speed = p["trip_speed"] * (frac_emw - mw) * dh_bhp / surge_dp
        max_swab_speed = p["trip_speed"] * (mw - pore_emw) * dh_bhp / swab_dp
    else:
        max_surge_speed = max_swab_speed = float("inf")
    max_surge_speed = max(0.0, max_surge_speed)
    max_swab_speed = max(0.0, max_swab_speed)
    # La velocidad máxima segura es la más restrictiva entre surge y swab
    max_safe_speed = min(max_surge_speed, max_swab_speed)

    # Verificamos que ni el surge exceda la fractura ni el swab caiga bajo el poro
    window_ok = (surge_emw <= frac_emw) and (swab_emw >= pore_emw)

    def _r(x):
        # Redondeamos a entero si es infinito (sin límite práctico), si no a 1 decimal
        return round(x) if math.isinf(x) else round(x, 1)

    # Devolvemos todos los resultados calculados para la vista de swab/surge
    return {
        "surge_dp": round(surge_dp),
        "swab_dp": round(swab_dp),
        "surge_emw": round(surge_emw, 2),
        "swab_emw": round(swab_emw, 2),
        "pore_emw": round(pore_emw, 2),
        "frac_emw": round(frac_emw, 2),
        "max_surge_speed": _r(max_surge_speed),
        "max_swab_speed": _r(max_swab_speed),
        "max_safe_speed": _r(max_safe_speed),
        "va": round(va_last),
        "q_equiv": round(q_last),
        "tvd": round(tvd_td),
        "trip_speed": round(p["trip_speed"]),
        "closed": closed,
        "window_ok": window_ok,
        "surge_over_frac": surge_emw > frac_emw,
        "swab_under_pore": swab_emw < pore_emw,
        "profile": profile,
    }
