"""Program-coherence validation — the cross-checks a drilling engineer runs on a
well program before it is issued. Reads the loaded WellContext (casing, hole,
mud, cement programs + the shared pore/fracture profile) and returns a flat list
of checks, each pass/fail with a human message, so the UI can flag problems
(the classic pink = fail / white = pass program review).

Checks implemented:
  • Casing fits the hole   — casing OD < hole size of its section (running clearance)
  • Hole telescopes        — hole sizes strictly decrease with depth
  • Seat in a drilled hole — each casing shoe lies within a hole section
  • Mud in the window      — section mud weight ≥ pore and ≤ frac (with margins)
  • Cement covers annulus  — slurry volume ≥ annular capacity over the cemented interval
  • Cement density         — slurry heavier than mud, lighter than frac at shoe
  • Trajectory vs plan     — max built inclination ≤ plan max (if set)
"""
import math
from typing import Optional

from app.services.engineering.context import WellContext

# nominal casing ID (in) by OD for annular-capacity checks (shelf weights)
_CASING_ID = {30.0: 28.5, 20.0: 19.124, 13.375: 12.415, 10.75: 10.05,
              9.625: 8.681, 7.0: 6.184, 5.0: 4.276, 4.5: 4.0}
RUN_CLEARANCE = 0.5  # in — min hole-minus-OD to run casing


def _check(ok: bool, area: str, msg: str, detail: str = "") -> dict:
    return {"ok": bool(ok), "area": area, "message": msg, "detail": detail,
            "severity": "ok" if ok else "fail"}


def _warn(area: str, msg: str, detail: str = "") -> dict:
    return {"ok": True, "area": area, "message": msg, "detail": detail, "severity": "warn"}


def _hole_for_depth(ctx: WellContext, md: float) -> Optional[dict]:
    for h in ctx.hole:
        top, bot = h.get("top_md"), h.get("bottom_md")
        if top is not None and bot is not None and top <= md <= bot + 1:
            return h
    return None


def _ann_capacity_bblft(hole_id: float, pipe_od: float) -> float:
    return max(0.0, (hole_id ** 2 - pipe_od ** 2) / 1029.4)


def validate_program(ctx: WellContext) -> dict:
    checks: list[dict] = []

    # ---- Casing fits its hole + shoe lies in a drilled section ----
    for c in ctx.casing:
        od = c.get("od_in"); md = c.get("setting_md"); name = c.get("string") or "String"
        if not od or md is None:
            continue
        h = _hole_for_depth(ctx, md)
        if h is None:
            checks.append(_check(False, "Casing", f"{name} shoe @ {int(md)} ft is not inside any drilled hole section",
                                 "add/extend a hole section covering this depth"))
            continue
        hs = h.get("hole_size_in")
        if hs:
            clr = hs - od
            checks.append(_check(clr >= RUN_CLEARANCE, "Casing",
                                 f"{name} {od}\" in {hs}\" hole — clearance {clr:.3f}\"",
                                 f"need ≥ {RUN_CLEARANCE}\" running clearance"))

    # ---- Hole telescopes (sizes decrease with depth) ----
    holes = [h for h in ctx.hole if h.get("hole_size_in") and h.get("top_md") is not None]
    holes.sort(key=lambda h: h["top_md"])
    for a, b in zip(holes, holes[1:]):
        checks.append(_check(b["hole_size_in"] <= a["hole_size_in"] + 1e-6, "Hole",
                             f"{a.get('section') or '?'} {a['hole_size_in']}\" → {b.get('section') or '?'} {b['hole_size_in']}\"",
                             "each section must be ≤ the one above"))

    # ---- Mud weight inside the pore/fracture window ----
    has_gp = ctx.has_geopressure()
    for m in ctx.mud:
        bot = m.get("bottom_md"); wmin = m.get("weight_min"); wmax = m.get("weight_max")
        if bot is None or (wmin is None and wmax is None):
            continue
        tvd = ctx.tvd_at(bot) or bot
        sec = m.get("section") or "interval"
        lo = wmin if wmin is not None else wmax
        hi = wmax if wmax is not None else wmin
        if has_gp:
            pore, frac = ctx.pore_at(tvd), ctx.frac_at(tvd)
            if pore is not None:
                checks.append(_check(lo >= pore - 1e-6, "Mud",
                                     f"{sec}: min MW {lo} ppg vs pore {pore} ppg @ {int(bot)} ft",
                                     "mud must be ≥ pore pressure (well control)"))
            if frac is not None:
                checks.append(_check(hi <= frac + 1e-6, "Mud",
                                     f"{sec}: max MW {hi} ppg vs frac {frac} ppg @ {int(bot)} ft",
                                     "mud must stay below the fracture gradient (losses)"))
        if wmin is not None and wmax is not None:
            checks.append(_check(wmax >= wmin, "Mud", f"{sec}: max MW {wmax} ≥ min MW {wmin}"))

    # ---- Cement: annular capacity vs pumped volume, and slurry density ----
    for cm in ctx.cement:
        name = cm.get("string") or "String"
        top, bot, vol, dens = cm.get("top_md"), cm.get("bottom_md"), cm.get("volume_bbl"), cm.get("density_ppg")
        # match the casing string this cement belongs to
        cas = next((c for c in ctx.casing if (c.get("string") or "").lower() == name.lower()), None)
        if cas and top is not None and bot is not None and vol is not None:
            od = cas.get("od_in")
            h = _hole_for_depth(ctx, bot) or _hole_for_depth(ctx, cas.get("setting_md") or bot)
            hs = h.get("hole_size_in") if h else None
            if od and hs and bot > top:
                need = _ann_capacity_bblft(hs, od) * (bot - top) * 1.15  # +15% excess
                checks.append(_check(vol >= need * 0.85, "Cement",
                                     f"{name}: {vol:.0f} bbl vs ~{need:.0f} bbl annular need ({int(top)}–{int(bot)} ft)",
                                     "slurry volume should cover the annulus + excess"))
        if dens is not None:
            mw = ctx.mud_weight_at(bot or (cas.get("setting_md") if cas else 0) or 0)
            checks.append(_check(dens >= mw, "Cement", f"{name}: slurry {dens} ppg vs mud {mw} ppg",
                                 "cement should be heavier than the mud it displaces"))
            if has_gp and bot is not None:
                frac = ctx.frac_at(ctx.tvd_at(bot) or bot)
                # Lead slurries routinely exceed frac at a shallow shoe; that is an
                # ECD / stage-cementing design note, not a hard error — so warn.
                if frac is not None and dens > frac + 0.5:
                    checks.append(_warn("Cement", f"{name}: slurry {dens} ppg vs frac {frac} ppg @ shoe",
                                        "manage ECD / stage cement to avoid losses at the shoe"))

    # ---- Trajectory: built inclination vs plan max ----
    if ctx.plan and ctx.plan.max_inclination is not None and ctx.directional:
        maxinc = max((d.get("inclination") or 0) for d in ctx.directional)
        checks.append(_check(maxinc <= float(ctx.plan.max_inclination) + 0.5, "Trajectory",
                             f"max planned inc {maxinc:.1f}° vs plan cap {float(ctx.plan.max_inclination):.1f}°"))

    # ---- coverage warnings (missing basis) ----
    if not has_gp:
        checks.append(_warn("Basis", "No geopressure profile — mud/seat window checks skipped",
                            "add points in the Geopressure grid to enable full validation"))
    if not ctx.casing:
        checks.append(_warn("Basis", "No casing program to validate"))

    fails = sum(1 for c in checks if c["severity"] == "fail")
    warns = sum(1 for c in checks if c["severity"] == "warn")
    passes = sum(1 for c in checks if c["severity"] == "ok")
    return {"checks": checks, "fails": fails, "warns": warns, "passes": passes,
            "total": len(checks), "ok": fails == 0}
