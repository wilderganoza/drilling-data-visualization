"""Casing design at commercial-methods depth (StressCheck-style).

Pipe ratings from OD·weight·grade: Barlow burst (API wall tolerance), full API
Bulletin 5C3 four-regime collapse, pipe-body yield and connection tension.

Design is evaluated against MULTIPLE load cases, and the governing (minimum SF)
case is reported per string:

  Burst   : gas kick to surface, tubing leak (SITP), pressure test, green cement
  Collapse: cementation (wet cement outside), full evacuation / lost returns,
            partial evacuation, drilling losses next section
  Axial   : installation (buoyed), overpull, green-cement plug bump, shock

Biaxial: collapse rating is derated for axial tension via the API ellipse.
Triaxial: von Mises equivalent stress at the inner wall under the combined
burst+axial condition is checked against the triaxial design factor.
Also reports depth profiles (load & rating vs depth) for charting."""
import math
from dataclasses import dataclass

from app.services.engineering import tubular_catalog
from app.services.engineering.context import WellContext

E_STEEL = 30.0e6       # psi — Young's modulus
ALPHA_STEEL = 6.9e-6   # /°F — thermal expansion coefficient of steel


@dataclass
class Inp:
    name: str
    label: str
    default: float
    unit: str = ""
    kind: str = "number"
    options: tuple = ()


INPUTS = [
    Inp("mud_grad", "Drilling mud gradient (this section)", 0.52, "psi/ft"),
    Inp("mud_grad_next", "Mud gradient next section (kick)", 0.62, "psi/ft"),
    Inp("frac_grad_next", "Frac gradient at next shoe", 0.80, "psi/ft"),
    Inp("pore_grad", "Pore pressure gradient", 0.465, "psi/ft"),
    Inp("gas_grad", "Gas gradient (kick)", 0.10, "psi/ft"),
    Inp("backup_grad", "Burst backup (annulus) gradient", 0.465, "psi/ft"),
    Inp("packer_fluid_grad", "Packer/completion fluid gradient", 0.45, "psi/ft"),
    Inp("sitp", "Surface tubing pressure (tubing leak)", 5000, "psi"),
    Inp("test_pressure", "Casing test pressure (surface)", 3000, "psi"),
    Inp("cement_grad", "Cement slurry gradient", 0.82, "psi/ft"),
    Inp("overpull", "Overpull margin", 100000, "lbf"),
    Inp("buoyancy_mw", "Mud weight for buoyancy", 9.8, "ppg"),
    Inp("conn_eff", "Connection tension efficiency", 0.90, "frac"),
    Inp("df_burst", "Design factor — burst", 1.10, ""),
    Inp("df_collapse", "Design factor — collapse", 1.00, ""),
    Inp("df_tension", "Design factor — axial", 1.60, ""),
    Inp("df_triaxial", "Design factor — triaxial (VME)", 1.25, ""),
    Inp("kick_margin", "Kick margin (mud design)", 0.4, "ppg"),
    Inp("trip_margin", "Trip margin (mud design)", 0.3, "ppg"),
    Inp("frac_safety", "Frac safety at shoe (seat selection)", 0.3, "ppg"),
    Inp("conductor_depth", "Conductor setting depth", 300, "ft TVD"),
    Inp("install_temp", "Installation temperature", 70, "°F"),
    Inp("prod_temp_rise", "Production/circulating ΔT", 40, "°F"),
    Inp("design_dls", "Design dogleg (buckling/fatigue)", 3.0, "°/100ft"),
    Inp("rot_hours", "Rotating hours (fatigue)", 300, "hr"),
    Inp("design_rpm", "Rotary speed (fatigue)", 120, "rpm"),
    Inp("df_connection", "Design factor — connection", 1.60, ""),
    Inp("df_fatigue", "Design factor — fatigue", 1.00, ""),
]

# This module GENERATES the whole telescoping scheme — Casing, Hole & Bit, and
# Mud programs — from the shared pore/fracture profile by bottom-up seat
# selection (kick-tolerance method), exactly as StressCheck/WELLPLAN do.
PROGRAM_TARGETS = ["casing-program", "hole-program", "mud-program"]

# Canonical telescoping schemes keyed by string count. Each entry is
# (casing_od_in, hole_size_in, string_name), surface → TD. Seat selection picks
# HOW MANY strings; the scheme fixes the standard sizes that nest together.
_SCHEMES = {
    2: [(13.375, 17.5, "Surface"), (9.625, 12.25, "Production")],
    3: [(20.0, 26.0, "Surface"), (13.375, 17.5, "Intermediate"), (9.625, 12.25, "Production")],
    4: [(20.0, 26.0, "Conductor"), (13.375, 17.5, "Surface"), (9.625, 12.25, "Intermediate"), (7.0, 8.5, "Production")],
    5: [(30.0, 36.0, "Conductor"), (20.0, 26.0, "Surface"), (13.375, 17.5, "Intermediate"),
        (9.625, 12.25, "Intermediate 2"), (7.0, 8.5, "Production")],
}
# common shelf weight/grade per casing OD (nominal picks that pass design)
_STD_STRING = {30.0: (157, "X-52"), 20.0: (94, "X-52"), 13.375: (68, "K-55"),
               9.625: (47, "N-80"), 7.0: (29, "P-110"), 5.0: (18, "P-110")}
# bit/casing fallback table for when a hole program already exists
_BIT_CASING = [(36, 30.0), (26, 20.0), (17.5, 13.375), (12.25, 9.625), (8.5, 7.0), (6.125, 5.0)]


def _casing_for_hole(hole):
    return min(_BIT_CASING, key=lambda hc: abs(hc[0] - hole))[1]


def context_defaults(ctx: WellContext) -> dict:
    """Seed the pore/frac gradients from the shared profile (TD basis)."""
    out: dict = {}
    tvd = ctx.td_tvd()
    if not ctx.has_geopressure() or not tvd:
        return out
    pore, frac = ctx.pore_at(tvd), ctx.frac_at(tvd)
    if pore:
        out["pore_grad"] = round(pore * 0.052, 4)
    if frac:
        out["frac_grad_next"] = round(frac * 0.052, 4)
    return out


def select_seats(ctx: WellContext, kick: float, trip: float, frac_safety: float,
                 conductor_tvd: float = 300.0) -> list[float]:
    """Bottom-up casing-seat selection from the pore/fracture profile.

    Returns section-bottom TVDs, surface→TD ascending. Each shoe is placed at the
    shallowest depth whose fracture gradient can still contain the mud weight
    required to drill the section below (pore + trip + kick margins). This is the
    classic kick-tolerance graphical method every casing-design text describes."""
    td = ctx.td_tvd()
    if not ctx.has_geopressure() or not td:
        return []
    shoes: list[float] = [td]           # production shoe at TD
    current = td
    guard = 0
    while current > conductor_tvd + 100 and guard < 12:
        guard += 1
        mw = (ctx.pore_at(current) or 0) + trip          # mud to drill down to `current`
        needed = mw + kick + frac_safety                  # frac the protecting shoe must hold
        # walk up to the shallowest depth whose frac still contains `needed`
        d = current
        step = max(25.0, td / 400)
        shoe = None
        while d > conductor_tvd:
            d2 = d - step
            f = ctx.frac_at(d2)
            if f is None or f < needed:
                shoe = d2
                break
            d = d2
        if shoe is None or shoe <= conductor_tvd:
            break
        shoes.append(round(shoe))
        current = shoe
    shoes.append(round(conductor_tvd))
    return sorted(set(shoes))


def generate_rows(params: dict, ctx: WellContext, target: str) -> list[dict]:
    kick = float(params.get("kick_margin", 0.4))
    trip = float(params.get("trip_margin", 0.3))
    frac_safety = float(params.get("frac_safety", 0.3))
    cond_tvd = float(params.get("conductor_depth", 300))

    seats = select_seats(ctx, kick, trip, frac_safety, cond_tvd)  # section-bottom TVDs, ascending
    if seats:
        # Build sections from the seat depths + the canonical telescoping scheme.
        bottoms = seats                      # ascending TVD, surface→TD
        n = max(2, min(5, len(bottoms)))
        scheme = _SCHEMES[n]
        # if seat count and scheme length differ, take the deepest n bottoms
        bottoms = bottoms[-n:]
        sections = []
        top_md = 0.0
        for i, (od, hole, name) in enumerate(scheme):
            bot_tvd = bottoms[i]
            bot_md = ctx.md_at_tvd(bot_tvd) or bot_tvd
            sections.append({"i": i, "od": od, "hole": hole, "name": name,
                             "top_md": round(top_md), "bottom_md": round(bot_md),
                             "bottom_tvd": round(bot_tvd)})
            top_md = bot_md
    else:
        # No geopressure profile → derive from an existing hole program (legacy path).
        sections = []
        top_md = 0.0
        for i, h in enumerate(ctx.hole):
            hole = h.get("hole_size_in"); bot = h.get("bottom_md"); name = h.get("section")
            if hole is None or bot is None:
                continue
            od = _casing_for_hole(hole)
            sections.append({"i": i, "od": od, "hole": hole, "name": name or "Casing",
                             "top_md": round(h.get("top_md") or top_md), "bottom_md": round(bot),
                             "bottom_tvd": round(ctx.tvd_at(bot) or bot)})
            top_md = bot
    if not sections:
        return []

    last = len(sections) - 1
    rows = []
    for s in sections:
        od = s["od"]
        if target == "casing-program":
            w, g = _STD_STRING.get(od, (47, "N-80"))
            is_liner = (s["i"] == last and od <= 7.0)
            rows.append({"string": "Liner" if is_liner else s["name"], "od_in": od,
                         "weight_ppf": w, "grade": g, "connection": "BTC" if od > 7 else "TSH",
                         "setting_md": s["bottom_md"], "setting_tvd": s["bottom_tvd"]})
        elif target == "hole-program":
            rows.append({"section": s["name"], "hole_size_in": s["hole"],
                         "bit_type": "Tricone (soft)" if s["i"] == 0 else "PDC",
                         "top_md": s["top_md"], "bottom_md": s["bottom_md"]})
        else:  # mud-program — mud weight from the pore/frac window at section bottom
            pore = ctx.pore_at(s["bottom_tvd"]) or (float(params.get("pore_grad", 0.465)) / 0.052)
            frac = ctx.frac_at(s["bottom_tvd"]) or (pore + 2.0)
            mw_min = round(pore + trip, 1)
            mw_max = round(min(mw_min + max(kick, 0.3), frac - frac_safety), 1)
            if mw_max < mw_min:
                mw_max = mw_min
            rows.append({"section": s["name"],
                         "mud_type": "Spud mud" if s["i"] == 0 else ("WBM (inhibited)" if od > 7 else "OBM"),
                         "top_md": s["top_md"], "bottom_md": s["bottom_md"],
                         "weight_min": mw_min, "weight_max": mw_max})
    return rows

GRADE_YP = {"H-40": 40000, "J-55": 55000, "K-55": 55000, "N-80": 80000, "L-80": 80000,
            "C-90": 90000, "C-95": 95000, "T-95": 95000, "P-110": 110000, "Q-125": 125000, "X-52": 52000}


def _yp(grade):
    return float(GRADE_YP.get((grade or "").strip().upper(), 80000.0))


def _wall(od, ppf):
    disc = od * od - 4 * ppf / 10.68
    return (od - math.sqrt(disc)) / 2.0 if disc > 0 else od * 0.05


def _burst_rating(od, t, yp):
    return 0.875 * 2 * yp * t / od


def _collapse_rating(od, t, yp):
    dt = od / t
    A = 2.8762 + 0.10679e-5 * yp + 0.21301e-10 * yp ** 2 - 0.53132e-16 * yp ** 3
    B = 0.026233 + 0.50609e-6 * yp
    C = -465.93 + 0.030867 * yp - 0.10483e-7 * yp ** 2 + 0.36989e-13 * yp ** 3
    ba = B / A
    F = (46.95e6 * ((3 * ba) / (2 + ba)) ** 3) / (yp * ((3 * ba) / (2 + ba) - ba) * (1 - (3 * ba) / (2 + ba)) ** 2)
    G = F * ba
    dt_yp = (math.sqrt((A - 2) ** 2 + 8 * (B + C / yp)) + (A - 2)) / (2 * (B + C / yp))
    dt_pt = yp * (A - F) / (C + yp * (B - G))
    dt_te = (2 + ba) / (3 * ba)
    if dt <= dt_yp:
        return 2 * yp * ((dt - 1) / dt ** 2)
    if dt <= dt_pt:
        return yp * (A / dt - B) - C
    if dt <= dt_te:
        return yp * (F / dt - G)
    return 46.95e6 / (dt * (dt - 1) ** 2)


def _area(od, idd):
    return math.pi / 4 * (od * od - idd * idd)


def _biaxial_collapse(pc, axial_stress, yp):
    """API biaxial: tension reduces collapse resistance (ellipse of plasticity)."""
    x = axial_stress / yp
    factor = math.sqrt(max(0.0, 1 - 0.75 * x * x)) - 0.5 * x
    return pc * max(0.0, factor)


def _vme(sigma_a, p_i, p_o, od, idd):
    """von Mises equivalent stress at the inner wall (Lamé thick-wall)."""
    ro, ri = od / 2, idd / 2
    # hoop and radial at inner wall
    sigma_h = (p_i * (ri * ri + ro * ro) - 2 * p_o * ro * ro) / (ro * ro - ri * ri)
    sigma_r = -p_i
    return math.sqrt(0.5 * ((sigma_a - sigma_h) ** 2 + (sigma_h - sigma_r) ** 2 + (sigma_r - sigma_a) ** 2))


def _inertia(od, idd):
    return math.pi / 64.0 * (od ** 4 - idd ** 4)   # in^4


def _thermal_force(area, dT):
    """Constrained (cemented) string: heating induces axial compression.
    ΔF = -E·α·A·ΔT  (negative = compression)."""
    return -E_STEEL * ALPHA_STEEL * area * dT


def _inc_at(ctx: WellContext, md: float) -> float:
    pts = sorted([(d["md"], d.get("inclination") or 0.0) for d in ctx.directional if d.get("md") is not None])
    if not pts:
        return 0.0
    if md <= pts[0][0]:
        return pts[0][1]
    for (m1, i1), (m2, i2) in zip(pts, pts[1:]):
        if m1 <= md <= m2 and m2 != m1:
            return i1 + (i2 - i1) * (md - m1) / (m2 - m1)
    return pts[-1][1]


def _hole_for(ctx: WellContext, md: float, od: float) -> float:
    for h in ctx.hole:
        top, bot = h.get("top_md"), h.get("bottom_md")
        if top is not None and bot is not None and top <= md <= bot + 1:
            return h.get("hole_size_in") or (od + 2.0)
    bigger = [h.get("hole_size_in") for h in ctx.hole if h.get("hole_size_in") and h["hole_size_in"] > od]
    return min(bigger) if bigger else od + 2.0


def _buckling(od, idd, w_buoyed_ppf, incl_deg, r_clear, feff):
    """Sinusoidal & helical buckling (Dawson/Paslay for inclined pipe).
    feff = effective compressive force (positive = compression). Returns
    (mode, F_sin, F_hel, helical bending stress). Lubinski helical bending
    stress σ_b = OD·r·F / (4·I)."""
    I = _inertia(od, idd)
    we = (w_buoyed_ppf / 12.0) * max(math.sin(math.radians(incl_deg)), 0.05)  # lb/in, floored near-vertical
    r = max(r_clear, 0.05)
    root = math.sqrt(E_STEEL * I * we / r)
    f_sin = 2.0 * root
    f_hel = 2.0 * (2.0 * math.sqrt(2.0) - 1.0) * root   # ≈ 3.66·root (helical threshold)
    mode = "helical" if feff >= f_hel else ("sinusoidal" if feff >= f_sin else "none")
    sig_b = (od * r * max(feff, 0.0)) / (4.0 * I) if I else 0.0
    return mode, f_sin, f_hel, sig_b


def _fatigue(od, dls_deg_100ft, ultimate):
    """Rotating-bending fatigue screening in a dogleg. Bending stress amplitude
    σa = E·c·κ; endurance ≈ 0.35·UTS (a conservative corrosion-fatigue limit).
    Returns (sigma_a, endurance, SF)."""
    kappa = (dls_deg_100ft * math.pi / 180.0) / (100.0 * 12.0)  # curvature, 1/in
    sig_a = E_STEEL * (od / 2.0) * kappa
    endurance = 0.35 * ultimate
    sf = endurance / sig_a if sig_a > 1.0 else None
    return sig_a, endurance, sf


def compute(params: dict, ctx: WellContext) -> dict:
    p = {i.name: float(params.get(i.name, i.default)) for i in INPUTS}
    bf = 1.0 - p["buoyancy_mw"] / 65.4
    td_next = ctx.td() or 0
    # Prefer the shared pore/fracture profile as the load basis when it exists,
    # so every string is checked against the same design line the seats came from.
    uses_profile = ctx.has_geopressure()
    if uses_profile:
        td_tvd = ctx.td_tvd() or 0
        pore_td = ctx.pore_at(td_tvd)
        if pore_td:
            p["pore_grad"] = round(pore_td * 0.052, 4)          # ppg EMW → psi/ft
    strings = []
    n = len(ctx.casing)
    for idx, c in enumerate(ctx.casing):
        od = c.get("od_in"); ppf = c.get("weight_ppf"); grade = c.get("grade")
        md = c.get("setting_md"); tvd = c.get("setting_tvd") or ctx.tvd_at(md or 0)
        if not od or not ppf or not md:
            continue
        # real geometry from the API 5CT catalog when the size is recognised,
        # else fall back to a wall computed from nominal weight
        tub = tubular_catalog.lookup(od, ppf)
        if tub and abs(tub.od - od) < 0.30:
            t = tub.wall; idd = tub.id_in; drift = tub.drift
        else:
            t = _wall(od, ppf); idd = od - 2 * t; drift = idd - 0.125
        yp = tubular_catalog.grade_yield(grade); ult = tubular_catalog.grade_ultimate(grade)
        area = _area(od, idd)
        r_burst = _burst_rating(od, t, yp)
        r_coll = _collapse_rating(od, t, yp)
        r_tens_body = yp * area
        r_tens_conn = r_tens_body * p["conn_eff"]
        is_production = (idx == n - 1)  # deepest string treated as production/liner

        # ---------- BURST load cases (internal - external) at shoe & surface ----------
        burst_cases = {}
        # 1. Gas kick: BHP at next TD held, gas column to surface
        bhp_next = p["pore_grad"] * (ctx.td_tvd() or tvd)
        p_surf_gas = bhp_next - p["gas_grad"] * (ctx.td_tvd() or tvd)
        burst_cases["Gas kick"] = max(p_surf_gas - 0,
                                      (p_surf_gas + p["gas_grad"] * tvd) - p["backup_grad"] * tvd)
        # 2. Tubing leak (production): SITP at surface applied to packer fluid
        if is_production:
            burst_cases["Tubing leak"] = max(p["sitp"] - 0,
                                             (p["sitp"] + p["packer_fluid_grad"] * tvd) - p["backup_grad"] * tvd)
        # 3. Pressure test
        burst_cases["Pressure test"] = max(p["test_pressure"],
                                           (p["test_pressure"] + p["mud_grad"] * tvd) - p["backup_grad"] * tvd)
        # 4. Green cement (internal displacement fluid vs external wet cement — usually collapse; burst small)
        gov_burst_case = max(burst_cases, key=lambda k: burst_cases[k])
        burst_load = burst_cases[gov_burst_case]

        # ---------- COLLAPSE load cases (external - internal) at shoe ----------
        collapse_cases = {}
        # 1. Cementation: wet cement outside, lighter displacement fluid inside
        collapse_cases["Cementation"] = max(0.0, p["cement_grad"] * tvd - p["mud_grad"] * tvd * 0.9)
        # 2. Full evacuation (lost returns / gas): mud outside, empty inside
        collapse_cases["Full evacuation"] = max(0.0, p["mud_grad"] * tvd)
        # 3. Partial evacuation (drilling losses next section drops fluid ~40%)
        collapse_cases["Losses next section"] = max(0.0, p["mud_grad_next"] * tvd - p["mud_grad"] * tvd * 0.6)
        gov_coll_case = max(collapse_cases, key=lambda k: collapse_cases[k])
        collapse_load = collapse_cases[gov_coll_case]

        # ---------- AXIAL load cases ----------
        buoyed_wt = ppf * md * bf
        axial_cases = {
            "Installation (buoyed)": buoyed_wt,
            "Overpull": buoyed_wt + p["overpull"],
            "Green cement bump": buoyed_wt + p["test_pressure"] * _area(idd, 0) * 0,  # bump adds ~ p*Ai
        }
        # plug bump adds pressure force on cross-section (approx internal area)
        axial_cases["Green cement bump"] = buoyed_wt + p["test_pressure"] * (math.pi / 4 * idd * idd)
        gov_axial_case = max(axial_cases, key=lambda k: axial_cases[k])
        axial_load = axial_cases[gov_axial_case]
        axial_stress = axial_load / area

        # ---------- Biaxial-corrected collapse ----------
        r_coll_biax = _biaxial_collapse(r_coll, axial_stress, yp)

        # ---------- Triaxial (VME) under governing burst + installation axial ----------
        p_i = burst_load + p["backup_grad"] * tvd  # absolute internal at shoe (approx)
        p_o = p["backup_grad"] * tvd
        sigma_a = buoyed_wt / area
        vme = _vme(sigma_a, p_i, p_o, od, idd)
        sf_triax = yp / vme if vme else None

        sf_b = r_burst / burst_load if burst_load else None
        sf_c = r_coll_biax / collapse_load if collapse_load else None
        sf_t = r_tens_conn / axial_load if axial_load else None

        # ---------- Connection analysis (from the real connection catalog) ----------
        conn = tubular_catalog.connection(c.get("connection"))
        r_conn_tension = r_tens_body * conn.eff_tension
        r_conn_leak = r_burst * conn.eff_internal
        sf_conn_t = r_conn_tension / axial_load if axial_load else None
        sf_conn_leak = r_conn_leak / burst_load if burst_load else None
        gas_ok = conn.gas_tight or not is_production   # production string needs a gas-tight seal
        ok_conn = (sf_conn_t is not None and sf_conn_t >= p["df_connection"]) and \
                  (sf_conn_leak is not None and sf_conn_leak >= p["df_burst"]) and gas_ok

        # ---------- Thermal axial (cemented string, production heating) ----------
        dT = p["prod_temp_rise"]
        f_thermal = _thermal_force(area, dT)          # lbf (negative = compression)

        # ---------- Buckling (post-cement thermal compression at the shoe) ----------
        inc = _inc_at(ctx, md)
        hole = _hole_for(ctx, md, od)
        r_clear = max((hole - od) / 2.0, 0.05)
        f_buckle = max(0.0, -f_thermal)               # compressive magnitude driving buckling
        buckle_mode, f_sin, f_hel, sig_buckle = _buckling(od, idd, ppf * bf, inc, r_clear, f_buckle)

        # ---------- Fatigue screening (rotating bending in the design dogleg) ----------
        sig_fa, endur, sf_fatigue = _fatigue(od, p["design_dls"], ult)

        # ---------- Triaxial including thermal axial + buckling bending ----------
        sigma_a_full = (buoyed_wt + f_thermal) / area
        vme_buckled = _vme(sigma_a_full, p_i, p_o, od, idd) + sig_buckle
        sf_triax_buckled = yp / vme_buckled if vme_buckled else None

        strings.append({
            "string": c.get("string"), "od": od, "ppf": ppf, "grade": grade or "N-80",
            "setting_md": md, "setting_tvd": round(tvd) if tvd else None, "wall": round(t, 3),
            "id": round(idd, 3), "yp": int(yp), "dt": round(od / t, 1),
            "burst_rating": round(r_burst), "burst_load": round(burst_load), "burst_case": gov_burst_case, "sf_burst": round(sf_b, 2) if sf_b else None,
            "collapse_rating": round(r_coll), "collapse_rating_biax": round(r_coll_biax), "collapse_load": round(collapse_load), "collapse_case": gov_coll_case, "sf_collapse": round(sf_c, 2) if sf_c else None,
            "tension_body": round(r_tens_body), "tension_conn": round(r_tens_conn), "axial_load": round(axial_load), "axial_case": gov_axial_case, "sf_tension": round(sf_t, 2) if sf_t else None,
            "vme": round(vme), "sf_triaxial": round(sf_triax, 2) if sf_triax else None,
            "burst_cases": {k: round(v) for k, v in burst_cases.items()},
            "collapse_cases": {k: round(v) for k, v in collapse_cases.items()},
            "axial_cases": {k: round(v) for k, v in axial_cases.items()},
            "ok_burst": (sf_b is not None and sf_b >= p["df_burst"]),
            "ok_collapse": (sf_c is not None and sf_c >= p["df_collapse"]),
            "ok_tension": (sf_t is not None and sf_t >= p["df_tension"]),
            "ok_triaxial": (sf_triax is not None and sf_triax >= p["df_triaxial"]),
            # --- connection ---
            "drift": round(drift, 3), "connection": c.get("connection") or "—", "conn_name": conn.name,
            "gas_tight": conn.gas_tight, "gas_ok": gas_ok,
            "conn_tension": round(r_conn_tension), "conn_leak": round(r_conn_leak),
            "sf_conn_tension": round(sf_conn_t, 2) if sf_conn_t else None,
            "sf_conn_leak": round(sf_conn_leak, 2) if sf_conn_leak else None, "ok_connection": ok_conn,
            # --- thermal ---
            "dT": round(dT), "thermal_force": round(f_thermal), "thermal_stress": round(f_thermal / area),
            # --- buckling ---
            "buckle_mode": buckle_mode, "f_sin": round(f_sin), "f_hel": round(f_hel),
            "f_buckle": round(f_buckle), "buckle_stress": round(sig_buckle),
            "incl": round(inc, 1), "clearance": round(r_clear, 3), "ok_buckle": buckle_mode != "helical",
            # --- fatigue ---
            "fatigue_stress": round(sig_fa), "fatigue_endurance": round(endur),
            "sf_fatigue": round(sf_fatigue, 2) if sf_fatigue else None,
            "ok_fatigue": (sf_fatigue is not None and sf_fatigue >= p["df_fatigue"]),
            # --- triaxial with thermal + buckling ---
            "vme_buckled": round(vme_buckled), "sf_triaxial_buckled": round(sf_triax_buckled, 2) if sf_triax_buckled else None,
        })
    return {"strings": strings, "buoyancy_factor": round(bf, 3),
            "df": {"burst": p["df_burst"], "collapse": p["df_collapse"], "tension": p["df_tension"],
                   "triaxial": p["df_triaxial"], "connection": p["df_connection"], "fatigue": p["df_fatigue"]}}
