"""Torque & Drag — soft-string model along the planned trajectory.

For each string element the normal (side) force is
   N = sqrt[ (Ft·Δinc + w·sinθ)² + (Ft·sinθ·Δazi)² ]
integrated bottom-up. Axial load is accumulated for four operations:
   POOH (pick-up)         : ΔFt = w·cosθ + μN
   RIH (slack-off)        : ΔFt = w·cosθ − μN
   Rotating off-bottom    : ΔFt = w·cosθ   (drag → torque, T += μ·N·r)
   Drilling (rot + WOB)   : rotating string minus WOB, torque = bit torque + Σμ·N·r
Friction factor switches cased→open at the deepest casing shoe. Effective
tension (buoyancy method) is checked against sinusoidal and helical buckling
limits. Outputs hookloads, surface torque, and tension/side-force profiles."""
# Importamos math para raíces, senos/cosenos y demás funciones usadas en el modelo
import math
# Importamos dataclass para describir cada input del formulario de T&D
from dataclasses import dataclass

# Importamos WellContext, el contexto con la trayectoria direccional y el programa de casing
from app.services.engineering.context import WellContext

E_STEEL = 30e6  # psi


# Definimos la estructura de cada input del formulario de torque & drag
@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


# Declaramos los inputs del modelo (pesos/OD/ID de tubería, BHA, factores de fricción, WOB, etc.)
INPUTS = [
    Inp("dp_weight", "Drill pipe weight (adj.)", 22.6, "ppf"),
    Inp("dp_od", "Drill pipe OD", 5.0, "in"),
    Inp("dp_id", "Drill pipe ID", 4.276, "in"),
    Inp("tooljoint_r", "Tool-joint contact radius", 3.25, "in"),
    Inp("bha_weight", "BHA weight", 90.0, "ppf"),
    Inp("bha_length", "BHA length", 900.0, "ft"),
    Inp("mud_weight", "Mud weight", 9.8, "ppg"),
    Inp("ff_cased", "Friction factor — cased", 0.24, ""),
    Inp("ff_open", "Friction factor — open hole", 0.32, ""),
    Inp("wob", "Weight on bit", 35.0, "klbf"),
    Inp("bit_torque", "Bit torque", 8000.0, "ft-lbf"),
    Inp("overpull_limit", "Available overpull / hook limit", 500.0, "klbf"),
]


def _resample(directional, step=100.0):
    # Convertimos la trayectoria a tuplas (md, inclinación, azimut) ordenadas por MD
    pts = sorted([(d["md"], d.get("inclination") or 0.0, d.get("azimuth") or 0.0)
                  for d in directional if d.get("md") is not None])
    if len(pts) < 2:
        # Sin al menos 2 puntos no hay trayectoria que remuestrear
        return []

    def interp(md):
        # Antes del primer punto, mantenemos la inclinación/azimut del primer punto
        if md <= pts[0][0]:
            return pts[0][1], pts[0][2]
        # Buscamos el segmento que contiene esta MD e interpolamos linealmente
        for (m1, i1, a1), (m2, i2, a2) in zip(pts, pts[1:]):
            if m1 <= md <= m2 and m2 != m1:
                f = (md - m1) / (m2 - m1)
                return i1 + (i2 - i1) * f, a1 + (a2 - a1) * f
        # Después del último punto, mantenemos su inclinación/azimut
        return pts[-1][1], pts[-1][2]

    md0, mdN = pts[0][0], pts[-1][0]
    out, md = [], md0
    # Remuestreamos la trayectoria a pasos regulares (step ft) para integrar el modelo
    while md < mdN:
        i, a = interp(md)
        out.append((md, i, a))
        md += step
    out.append((mdN, pts[-1][1], pts[-1][2]))
    return out


def compute(params: dict, ctx: WellContext) -> dict:
    # Completamos cada input con su valor por defecto si no vino en params
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    # Calculamos el factor de flotación (buoyancy) según el peso del lodo
    bf = 1.0 - p["mud_weight"] / 65.4
    # Remuestreamos la trayectoria a pasos regulares para integrar el modelo bottom-up
    path = _resample(ctx.directional)
    if len(path) < 2:
        # Sin trayectoria direccional cargada no podemos correr el modelo de T&D
        return {"error": "No directional plan — add a Directional Plan in Planning first.", "profile": [], "summary": {}}

    td = path[-1][0]
    # Ubicamos la última zapata de casing (excluyendo liner/TD) para el cambio de factor de fricción
    shoe = max([c.get("setting_md") for c in ctx.casing[:-1] if c.get("setting_md")] or [0])  # last casing shoe (exclude liner/TD)
    # moment of inertia of the pipe (in^4) for buckling + stiff-string correction
    # Calculamos el momento de inercia de la tubería (in^4) para el pandeo y la corrección stiff-string
    I = math.pi / 64 * (p["dp_od"] ** 4 - p["dp_id"] ** 4)
    I_bha = math.pi / 64 * (6.75 ** 4 - 3.0 ** 4)  # typical collar OD 6.75, ID 3.0 — this module has no collar OD/ID input
    L_span = 30.0 * 12.0  # tool-joint span (in) over which stiffness reacts
    r_contact = p["tooljoint_r"]

    # bottom-up accumulation (soft-string + stiff-string in parallel)
    # Inicializamos los acumuladores de tensión axial para cada operación (POOH/RIH/rotando/perforando)
    ft_pooh = ft_rih = ft_rot = ft_drill = 0.0
    ft_pooh_stiff = ft_rih_stiff = 0.0
    torque_rot = p["bit_torque"]
    torque_drill = p["bit_torque"]
    torque_rot_stiff = p["bit_torque"]
    torque_drill_stiff = p["bit_torque"]
    profile = []
    # start drill from bit with -WOB (compression on bit)
    # Arrancamos la tensión de perforación desde el fondo con -WOB (compresión en la broca)
    ft_drill = -p["wob"] * 1000.0
    # Integramos de fondo hacia superficie (bottom-up), elemento por elemento de la trayectoria
    for k in range(len(path) - 1, 0, -1):
        md_hi, inc_hi, azi_hi = path[k]
        md_lo, inc_lo, azi_lo = path[k - 1]
        dmd = md_hi - md_lo
        theta = math.radians((inc_hi + inc_lo) / 2)
        dinc = math.radians(inc_hi - inc_lo)
        dazi = math.radians(azi_hi - azi_lo)
        mid_md = (md_hi + md_lo) / 2
        # Usamos peso de BHA si el elemento cae dentro del tramo de BHA, si no, peso de drill pipe
        w_ppf = p["bha_weight"] if mid_md > (td - p["bha_length"]) else p["dp_weight"]
        w = w_ppf * dmd * bf  # buoyed element weight (lbf)
        # Cambiamos el factor de fricción según si el elemento está entubado (cased) u hueco abierto
        mu = p["ff_cased"] if mid_md < shoe else p["ff_open"]

        # side force using the rotating tension as representative
        # Usamos la tensión rotando como tensión representativa para calcular la fuerza lateral
        ft_ref = max(ft_rot, 0)
        N = math.sqrt((ft_ref * dinc + w * math.sin(theta)) ** 2 + (ft_ref * math.sin(theta) * dazi) ** 2)
        N = max(N, w * math.sin(theta))  # floor at gravity component

        # --- stiff-string correction: bending-stiffness contact force in a dogleg ---
        # A stiff tubular forced around a dogleg of curvature κ reacts an extra wall
        # contact force ≈ 2·E·I·κ / L_span (beam reaction over a tool-joint span).
        # Concentrated where curvature is high, negligible in tangent/vertical hole.
        # Elegimos el momento de inercia del BHA o del drill pipe según en qué tramo estamos
        I_el = I_bha if mid_md > (td - p["bha_length"]) else I
        kappa = math.sqrt(dinc ** 2 + (math.sin(theta) * dazi) ** 2) / max(dmd * 12.0, 1e-6)  # rad/in
        # Calculamos la fuerza de contacto extra por rigidez a flexión (corrección stiff-string)
        n_extra = 2.0 * E_STEEL * I_el * kappa / L_span
        N_stiff = N + n_extra

        cos = w * math.cos(theta)
        # Acumulamos la tensión para cada operación: subiendo (+fricción), bajando (-fricción), rotando
        ft_pooh += cos + mu * N
        ft_rih += cos - mu * N
        ft_rot += cos
        ft_drill += cos
        torque_rot += mu * N * (r_contact / 12.0)      # ft-lbf
        torque_drill += mu * N * (r_contact / 12.0)
        # stiff-string variants (same axial weight, larger side force in doglegs)
        # Acumulamos las variantes stiff-string (mismo peso axial, mayor fuerza lateral en dogleg)
        ft_pooh_stiff += cos + mu * N_stiff
        ft_rih_stiff += cos - mu * N_stiff
        torque_rot_stiff += mu * N_stiff * (r_contact / 12.0)
        torque_drill_stiff += mu * N_stiff * (r_contact / 12.0)

        # effective tension & buckling (compression negative)
        # Calculamos la tensión efectiva (método de flotación) y los límites de pandeo sinusoidal/helicoidal
        feff = ft_rot  # approx (buoyancy method already applied via bf)
        f_sin = 2 * math.sqrt(E_STEEL * I * (w_ppf / 12.0) * max(math.sin(theta), 1e-3) / max(r_contact, 0.1))
        f_hel = 2.828 * math.sqrt(E_STEEL * I * (w_ppf / 12.0) * max(math.sin(theta), 1e-3) / max(r_contact, 0.1))
        # Clasificamos el estado de pandeo comparando la tensión efectiva contra ambos límites
        buckled = "helical" if (feff < -f_hel) else ("sinusoidal" if feff < -f_sin else "none")

        # Guardamos el punto del perfil (hookloads parciales y estado de pandeo en esta MD)
        profile.append({"md": round(md_hi), "inc": round((inc_hi + inc_lo) / 2, 1),
                        "pooh": round(max(ft_pooh, 0) / 1000, 1), "rih": round(ft_rih / 1000, 1),
                        "rot": round(ft_rot / 1000, 1), "side": round(N / dmd if dmd else 0, 1),
                        "pooh_stiff": round(max(ft_pooh_stiff, 0) / 1000, 1), "buckle": buckled})
    # Invertimos el perfil para que quede ordenado de superficie a fondo (coherente con la integración bottom-up)
    profile.reverse()

    rot_wt = ft_rot / 1000.0  # rotating weight (string weight in mud) klbf
    # Calculamos el porcentaje de incremento de torque y drag que aporta la corrección stiff-string
    pct_torque = round((torque_drill_stiff - torque_drill) / torque_drill * 100, 1) if torque_drill else 0.0
    pct_drag = round((ft_pooh_stiff - ft_pooh) / ft_pooh * 100, 1) if ft_pooh else 0.0
    summary = {
        "hookload_pooh": round(ft_pooh / 1000, 1),
        "hookload_rih": round(ft_rih / 1000, 1),
        "hookload_rot": round(rot_wt, 1),
        "surface_torque_rot": round(torque_rot),
        "surface_torque_drill": round(torque_drill),
        "max_side_force": round(max((e["side"] for e in profile), default=0), 1),
        "pickup_margin": round(p["overpull_limit"] - ft_pooh / 1000, 1),
        "buckling": next((e["buckle"] for e in profile if e["buckle"] != "none"), "none"),
        "slackoff_ok": ft_rih > 0,  # positive means string still in tension when RIH
        "td": round(td), "shoe": round(shoe),
        # --- stiff-string ---
        "hookload_pooh_stiff": round(ft_pooh_stiff / 1000, 1),
        "hookload_rih_stiff": round(ft_rih_stiff / 1000, 1),
        "surface_torque_drill_stiff": round(torque_drill_stiff),
        "surface_torque_rot_stiff": round(torque_rot_stiff),
        "pct_torque_stiff": pct_torque, "pct_drag_stiff": pct_drag,
    }
    # Devolvemos el perfil completo, el resumen y notas explicativas de fricción y corrección stiff-string
    return {"profile": profile, "summary": summary,
            "df_note": "μ cased {:.2f} / open {:.2f}".format(p["ff_cased"], p["ff_open"]),
            "stiff_note": "Stiff-string adds +{:.1f}% torque / +{:.1f}% pick-up drag vs soft-string (bending-stiffness contact in doglegs).".format(pct_torque, pct_drag)}
