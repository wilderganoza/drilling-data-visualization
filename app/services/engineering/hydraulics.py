"""Drilling hydraulics — full circulating-system pressure losses, ECD, bit
hydraulics, hole cleaning and the operating (pore/frac) window.

Rheology: Power-law n,K derived from PV/YP (Bingham also reported). Frictional
losses use the standard rig-site field equations (laminar / turbulent selected
by critical velocity) for each conduit: surface equipment, drill-pipe & collar
bores, bit nozzles, and each open/cased annular section from the hole program.
Bit hydraulics: ΔP_bit, nozzle velocity, HSI, jet impact force, % of pump
pressure at the bit. Hole cleaning: annular velocity, cuttings slip velocity
(Moore) and transport ratio. ECD profile vs planned TVD, checked against the
pore/frac window."""
# Importamos math para las funciones trigonométricas y logarítmicas de las fórmulas de hidráulica
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
    Inp("flow", "Flow rate", 600, "gpm"),
    Inp("mw", "Mud weight", 9.9, "ppg"),
    Inp("pv", "Plastic viscosity", 18, "cP"),
    Inp("yp", "Yield point", 22, "lbf/100ft²"),
    Inp("dp_od", "Drill pipe OD", 5.0, "in"),
    Inp("dp_id", "Drill pipe ID", 4.276, "in"),
    Inp("collar_od", "Collar/BHA OD", 6.75, "in"),
    Inp("collar_id", "Collar/BHA ID", 2.8125, "in"),
    Inp("collar_len", "Collar/BHA length", 900, "ft"),
    Inp("nozzles", "Bit nozzles (count)", 6, "", "number"),
    Inp("nozzle_size", "Nozzle size (1/32 in)", 13, "/32in"),
    Inp("surface_case", "Surface equipment case (1-4)", 3, "", "number"),
    Inp("rop", "ROP (hole cleaning)", 60, "ft/hr"),
    Inp("cuttings_sg", "Cuttings specific gravity", 2.6, ""),
    Inp("pore_grad", "Pore pressure gradient", 0.465, "psi/ft"),
    Inp("frac_grad", "Frac gradient", 0.80, "psi/ft"),
]

# surface equivalent length as ft of 3.826" ID pipe (API cases 1-4)
_SURF_EQ = {1: 2600, 2: 946, 3: 610, 4: 424}


def _powerlaw(pv, yp):
    # Derivamos el índice de flujo n y la consistencia K del modelo de potencia a partir de PV/YP
    n = 3.32 * math.log10((2 * pv + yp) / (pv + yp)) if (pv + yp) > 0 else 1.0
    K = (pv + yp) / (511 ** n)
    return round(n, 3), K


def _v_pipe(q, d):
    # Calculamos la velocidad dentro de la tubería (ft/min) a partir del caudal y el ID
    return 24.51 * q / (d * d) if d else 0  # ft/min


def _v_annulus(q, d2, d1):
    # Calculamos la velocidad en el anular (ft/min) a partir del caudal y las áreas de los diámetros
    return 24.51 * q / (d2 * d2 - d1 * d1) if (d2 * d2 - d1 * d1) > 0 else 0


def _crit_v(pv, yp, rho, d):
    # Guardamos contra división por cero cuando la densidad o el diámetro/gap no son válidos
    if rho <= 0 or d <= 0:
        return 0.0
    # Calculamos la velocidad crítica que separa el régimen laminar del turbulento
    return (1.08 * pv + 1.08 * math.sqrt(pv * pv + 12.34 * d * d * yp * rho)) / (rho * d)


def _dp_pipe(L, pv, yp, rho, q, d):
    # Calculamos la velocidad dentro de la tubería para este tramo
    v = _v_pipe(q, d)
    # Guardamos contra división por cero cuando el ID de la tubería no es válido
    if d <= 0:
        return 0.0, v
    # Calculamos la caída de presión laminar y turbulenta (ecuaciones de campo estándar)
    lam = (L * pv * v) / (90000 * d * d) + (L * yp) / (225 * d)
    turb = (7.7e-5 * rho ** 0.8 * q ** 1.8 * pv ** 0.2 * L) / (d ** 4.8)
    # Elegimos el régimen (laminar/turbulento) comparando contra la velocidad crítica
    return turb if v > _crit_v(pv, yp, rho, d) else lam, v


def _dp_annulus(L, pv, yp, rho, q, d2, d1):
    # Calculamos la velocidad anular para este tramo
    v = _v_annulus(q, d2, d1)
    gap = d2 - d1
    # Guardamos contra división por cero cuando el gap anular no es válido
    if gap <= 0:
        return 0.0, v
    # Calculamos la caída de presión laminar y turbulenta en el anular
    lam = (L * pv * v) / (60000 * gap * gap) + (L * yp) / (200 * gap)
    turb = (7.7e-5 * rho ** 0.8 * q ** 1.8 * pv ** 0.2 * L) / (gap ** 3 * (d2 + d1) ** 1.8)
    # Elegimos el régimen (laminar/turbulento) comparando contra la velocidad crítica
    return turb if v > _crit_v(pv, yp, rho, gap) else lam, v


def _slip_velocity(dc, mw, sg):
    """Cuttings slip velocity (ft/min) — Moore correlation, simplified turbulent."""
    # Guardamos contra división por cero cuando el peso de lodo no es válido
    if mw <= 0:
        return 0.0
    # Convertimos la gravedad específica de los recortes a densidad (ppg)
    rho_c = sg * 8.33
    # Calculamos la velocidad de deslizamiento de los recortes (correlación de Moore)
    return 92 * math.sqrt(max(0.0, dc * (rho_c - mw) / mw))


def context_defaults(ctx: WellContext) -> dict:
    """Seed pore/frac gradients and drilling mud weight from the shared profile."""
    out: dict = {}
    tvd = ctx.td_tvd()
    # Si no hay perfil de geopresión o TVD conocida, no podemos sembrar valores por defecto
    if not ctx.has_geopressure() or not tvd:
        return out
    # Leemos la presión de poro y de fractura en el TVD de profundidad total (TD)
    pore, frac = ctx.pore_at(tvd), ctx.frac_at(tvd)
    if pore:
        # Convertimos la presión de poro a gradiente y sugerimos un peso de lodo con margen de 0.4 ppg
        out["pore_grad"] = round(pore * 0.052, 4)
        out["mw"] = round(pore + 0.4, 1)
    if frac:
        # Convertimos la presión de fractura a gradiente
        out["frac_grad"] = round(frac * 0.052, 4)
    return out


def compute(params: dict, ctx: WellContext) -> dict:
    # Completamos cada input con su valor por defecto y lo convertimos a float
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    q, mw, pv, yp = p["flow"], p["mw"], p["pv"], p["yp"]
    n, K = _powerlaw(pv, yp)
    td = ctx.td() or 0
    td_tvd = ctx.td_tvd() or td
    collar_top = td - p["collar_len"]
    # Read pore/frac from the shared profile when it exists, else the input gradients.
    # Determinamos si hay perfil de geopresión compartido para preferirlo sobre los gradientes del input
    _prof = ctx.has_geopressure()

    def pore_emw_at(tvd):
        # Leemos la presión de poro (EMW) del perfil compartido, o calculamos desde el gradiente del input
        v = ctx.pore_at(tvd) if _prof else None
        return v if v is not None else mw_equiv(p["pore_grad"])

    def frac_emw_at(tvd):
        # Leemos la presión de fractura (EMW) del perfil compartido, o calculamos desde el gradiente del input
        v = ctx.frac_at(tvd) if _prof else None
        return v if v is not None else mw_equiv(p["frac_grad"])

    # --- internal (pipe bore) losses ---
    # Calculamos las pérdidas de presión dentro del drill pipe (desde el tope del collar hasta superficie)
    dp_dp, v_dp_int = _dp_pipe(max(collar_top, 0), pv, yp, mw, q, p["dp_id"])
    # Calculamos las pérdidas de presión dentro del collar/BHA
    dp_col, v_col_int = _dp_pipe(p["collar_len"], pv, yp, mw, q, p["collar_id"])
    # Calculamos las pérdidas del equipo de superficie usando la longitud equivalente del caso API
    surf = _SURF_EQ.get(int(p["surface_case"]), 610)
    dp_surf = _dp_pipe(surf, pv, yp, mw, q, 3.826)[0]

    # --- bit ---
    # Calculamos el área total de flujo (TFA) de las boquillas de la broca
    tfa = p["nozzles"] * (math.pi / 4) * (p["nozzle_size"] / 32.0) ** 2
    # Calculamos la caída de presión en la broca, la velocidad de la boquilla, el HSI y el impacto del chorro
    dp_bit = mw * q * q / (12042 * tfa * tfa) if tfa else 0
    vn = 0.32086 * q / tfa if tfa else 0  # ft/s
    hole_bottom = ctx.hole[-1]["hole_size_in"] if ctx.hole else 8.5
    a_bit = math.pi / 4 * hole_bottom ** 2
    hsi = dp_bit * q / (1714 * a_bit) if a_bit else 0
    jet_impact = q * vn * mw / 1930.0  # lbf

    # --- annulus per hole section + ECD profile ---
    # Recorremos cada sección del hueco para acumular la caída de presión anular y el perfil de ECD
    ann_rows = []
    cum_ann = 0.0
    ecd_profile = []
    for h in ctx.hole:
        dh = h.get("hole_size_in"); top = h.get("top_md"); bot = h.get("bottom_md")
        # Saltamos secciones sin datos suficientes (tamaño de hueco o profundidades faltantes/ inválidas)
        if not dh or top is None or bot is None or bot <= top:
            continue
        # pipe OD present in this section (collar near bit, else DP)
        # Determinamos el OD de la tubería presente en esta sección (collar cerca de la broca, si no drill pipe)
        pipe_od = p["collar_od"] if top >= collar_top else p["dp_od"]
        dpr, v = _dp_annulus(bot - top, pv, yp, mw, q, dh, pipe_od)
        cum_ann += dpr
        tvd_bot = ctx.tvd_at(bot) or bot
        # Calculamos la densidad equivalente de circulación (ECD) al fondo de esta sección
        ecd = mw + cum_ann / (0.052 * tvd_bot) if tvd_bot else mw
        av = _v_annulus(q, dh, pipe_od)
        vslip = _slip_velocity(0.25, mw, p["cuttings_sg"])
        # Calculamos la razón de transporte de recortes (transport ratio)
        tr = max(0.0, 1 - vslip / av) if av else 0
        # cuttings concentration (%): Cconc ≈ ROP·... simplified
        # Calculamos la concentración de recortes en el anular (simplificada)
        conc = (p["rop"] / 60.0) * a_bit / (av * (math.pi / 4 * (dh * dh - pipe_od * pipe_od))) * 100 if av else 0
        ann_rows.append({"section": h.get("section"), "hole": dh, "pipe_od": pipe_od,
                         "interval": f"{int(top)}–{int(bot)}", "av": round(av), "dp": round(dpr),
                         "ecd": round(ecd, 2), "vslip": round(vslip), "tr": round(tr * 100), "conc": round(conc, 1)})
        # Guardamos el punto del perfil de ECD contra las ventanas de poro/frac en este TVD
        ecd_profile.append({"md": bot, "tvd": round(tvd_bot), "ecd": round(ecd, 2),
                            "pore": round(pore_emw_at(tvd_bot), 2), "frac": round(frac_emw_at(tvd_bot), 2)})

    # Sumamos todas las caídas de presión para obtener la SPP total en superficie
    spp = dp_surf + dp_dp + dp_col + dp_bit + cum_ann
    ecd_td = mw + cum_ann / (0.052 * td_tvd) if td_tvd else mw
    pct_bit = round(dp_bit / spp * 100, 1) if spp else 0

    # Verificamos que el ECD en TD se mantenga dentro de la ventana de poro/frac
    pore_td_emw, frac_td_emw = pore_emw_at(td_tvd), frac_emw_at(td_tvd)
    window_ok = ecd_td <= frac_td_emw and mw >= pore_td_emw
    # Devolvemos todos los resultados calculados para la vista de hidráulica
    return {
        "n": n, "K": round(K, 4),
        "spp": round(spp), "dp_surf": round(dp_surf), "dp_dp": round(dp_dp), "dp_col": round(dp_col),
        "dp_bit": round(dp_bit), "dp_ann": round(cum_ann), "pct_bit": pct_bit,
        "tfa": round(tfa, 3), "vn": round(vn), "hsi": round(hsi, 2), "jet_impact": round(jet_impact),
        "ecd_td": round(ecd_td, 2), "pore_emw": round(pore_td_emw, 2), "frac_emw": round(frac_td_emw, 2),
        "window_ok": window_ok, "annulus": ann_rows, "ecd_profile": ecd_profile,
        "min_tr": round(min([a["tr"] for a in ann_rows], default=100)),
    }


def mw_equiv(grad):
    # Convertimos un gradiente (psi/ft) a un peso de lodo equivalente (ppg)
    return grad / 0.052
