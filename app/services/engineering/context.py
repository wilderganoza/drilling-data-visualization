"""WellContext — the well's Planning program grids + plan header, loaded once
and handed to every engineering calculator so they compute against the same
design basis (casing scheme, hole sections, mud program, planned trajectory,
formation prognosis). Also the get/save helpers for the params store."""
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.engineering import EngineeringDesign
from app.models.planning import WellPlan
from app.models.planning_capture import PLAN_CONFIG_BY_KEY
from app.repositories.capture_repository import GridRepository


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _rows(db: Session, event_id: str, key: str, order_attr: str = "sort_order") -> list:
    cfg = PLAN_CONFIG_BY_KEY[key]
    return GridRepository(db, cfg.model, parent_field="event_id").list_for_parent(event_id)


@dataclass
class WellContext:
    event_id: str
    plan: Optional[WellPlan] = None
    casing: list = field(default_factory=list)      # {string, od_in, weight_ppf, grade, connection, setting_md, setting_tvd}
    hole: list = field(default_factory=list)        # {section, hole_size_in, bit_type, top_md, bottom_md}
    mud: list = field(default_factory=list)         # {section, mud_type, top_md, bottom_md, weight_min, weight_max}
    cement: list = field(default_factory=list)      # {string, slurry_type, density_ppg, volume_bbl, top_md, bottom_md}
    directional: list = field(default_factory=list) # {md, inclination, azimuth, tvd, ns, ew, dls}
    formations: list = field(default_factory=list)  # {formation, md, tvd, lithology}
    geopressure: list = field(default_factory=list)  # {md, tvd, pore_ppg, frac_ppg, temp_f}
    time_depth: list = field(default_factory=list)   # {day, planned_md, phase}
    cost_estimate: list = field(default_factory=list)  # {category, description, qty, unit_cost, amount}
    offset_wells: list = field(default_factory=list)  # {name, directional:[...]} for anti-collision
    benchmark: list = field(default_factory=list)     # offset well cost/ft rows (AFE benchmarking)

    def td(self) -> Optional[float]:
        if self.plan and self.plan.authorized_md is not None:
            return float(self.plan.authorized_md)
        mds = [d["md"] for d in self.directional if d.get("md") is not None]
        return max(mds) if mds else None

    def td_tvd(self) -> Optional[float]:
        if self.plan and self.plan.authorized_tvd is not None:
            return float(self.plan.authorized_tvd)
        tvds = [d["tvd"] for d in self.directional if d.get("tvd") is not None]
        return max(tvds) if tvds else None

    def tvd_at(self, md: float) -> Optional[float]:
        """Interpolate planned TVD at a measured depth from the directional plan."""
        pts = [(d["md"], d["tvd"]) for d in self.directional if d.get("md") is not None and d.get("tvd") is not None]
        if not pts:
            return md  # assume vertical
        pts.sort()
        if md <= pts[0][0]:
            return pts[0][1]
        for (m1, t1), (m2, t2) in zip(pts, pts[1:]):
            if m1 <= md <= m2 and m2 != m1:
                return round(t1 + (t2 - t1) * (md - m1) / (m2 - m1), 2)
        return pts[-1][1]

    def md_at_tvd(self, tvd: float) -> Optional[float]:
        """Inverse of tvd_at — measured depth at a true vertical depth (from the
        directional plan). Returns tvd itself (vertical) when no survey exists."""
        pts = [(d["tvd"], d["md"]) for d in self.directional if d.get("md") is not None and d.get("tvd") is not None]
        if not pts:
            return tvd
        pts.sort()
        if tvd <= pts[0][0]:
            return pts[0][1]
        for (t1, m1), (t2, m2) in zip(pts, pts[1:]):
            if t1 <= tvd <= t2 and t2 != t1:
                return round(m1 + (m2 - m1) * (tvd - t1) / (t2 - t1), 2)
        return pts[-1][1]

    def mud_weight_at(self, md: float, default: float = 9.5) -> float:
        """Max planned mud weight for the interval containing md (ppg)."""
        for m in self.mud:
            top, bot = m.get("top_md"), m.get("bottom_md")
            if top is not None and bot is not None and top <= md <= bot:
                return float(m.get("weight_max") or m.get("weight_min") or default)
        # fall back to the deepest interval's max
        if self.mud:
            last = self.mud[-1]
            return float(last.get("weight_max") or last.get("weight_min") or default)
        return default

    # --- shared geopressure profile (the single design basis) ---
    def _gp_points(self, col: str) -> list[tuple]:
        """Sorted (tvd, value) pairs from the geopressure grid for interpolation.
        Points are keyed on TVD (equivalent mud weight is a TVD-based gradient)."""
        pts = []
        for g in self.geopressure:
            tvd = g.get("tvd")
            if tvd is None:
                tvd = self.tvd_at(g["md"]) if g.get("md") is not None else None
            val = g.get(col)
            if tvd is not None and val is not None:
                pts.append((float(tvd), float(val)))
        pts.sort()
        return pts

    @staticmethod
    def _interp(pts: list[tuple], x: float) -> Optional[float]:
        if not pts:
            return None
        if x <= pts[0][0]:
            return pts[0][1]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if x1 <= x <= x2 and x2 != x1:
                return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
        return pts[-1][1]

    def has_geopressure(self) -> bool:
        return bool(self._gp_points("pore_ppg"))

    def pore_at(self, tvd: float) -> Optional[float]:
        """Pore pressure (ppg EMW) interpolated at a true vertical depth."""
        v = self._interp(self._gp_points("pore_ppg"), tvd)
        return round(v, 2) if v is not None else None

    def frac_at(self, tvd: float) -> Optional[float]:
        """Fracture / LOT gradient (ppg EMW) interpolated at a true vertical depth."""
        v = self._interp(self._gp_points("frac_ppg"), tvd)
        return round(v, 2) if v is not None else None

    def temp_at(self, tvd: float) -> Optional[float]:
        v = self._interp(self._gp_points("temp_f"), tvd)
        return round(v, 1) if v is not None else None

    def pore_at_md(self, md: float) -> Optional[float]:
        t = self.tvd_at(md)
        return self.pore_at(t) if t is not None else None

    def frac_at_md(self, md: float) -> Optional[float]:
        t = self.tvd_at(md)
        return self.frac_at(t) if t is not None else None


def load_context(db: Session, event_id: str, with_offsets: bool = False, with_benchmark: bool = False) -> WellContext:
    plan = db.execute(select(WellPlan).where(WellPlan.event_id == event_id)).scalars().first()
    ctx = WellContext(
        event_id=event_id, plan=plan,
        casing=_grid_dicts(db, event_id, "casing-program", ["string", "od_in", "weight_ppf", "grade", "connection", "setting_md", "setting_tvd"]),
        hole=_grid_dicts(db, event_id, "hole-program", ["section", "hole_size_in", "bit_type", "top_md", "bottom_md", "length_ft"]),
        mud=_grid_dicts(db, event_id, "mud-program", ["section", "mud_type", "top_md", "bottom_md", "weight_min", "weight_max"]),
        cement=_grid_dicts(db, event_id, "cement-program", ["string", "slurry_type", "density_ppg", "volume_bbl", "top_md", "bottom_md"]),
        directional=_grid_dicts(db, event_id, "directional-plan", ["md", "inclination", "azimuth", "tvd", "ns", "ew", "dls"]),
        formations=_grid_dicts(db, event_id, "formation-tops", ["formation", "md", "tvd", "lithology"]),
        geopressure=_grid_dicts(db, event_id, "geopressure", ["md", "tvd", "pore_ppg", "frac_ppg", "temp_f"]),
        time_depth=_grid_dicts(db, event_id, "time-depth", ["day", "planned_md", "phase"]),
        cost_estimate=_grid_dicts(db, event_id, "cost-estimate", ["category", "description", "qty", "unit_cost", "amount"]),
    )
    if with_benchmark:
        from app.services.benchmarking import benchmark_field
        ctx.benchmark = [r for r in benchmark_field(db) if str(r.get("event_id")) != str(event_id)]
    if with_offsets:
        from app.models.hierarchy import Event, Well, Wellbore
        for ev in db.execute(select(Event).where(Event.id != event_id)).scalars().all():
            traj = _grid_dicts(db, str(ev.id), "directional-plan", ["md", "inclination", "azimuth", "tvd", "ns", "ew", "dls"])
            if not traj:
                continue
            wb = db.get(Wellbore, ev.wellbore_id)
            well = db.get(Well, wb.well_id) if wb else None
            ctx.offset_wells.append({"name": (well.legal_well_name if well else ev.event_code) or "Offset", "directional": traj})
    return ctx


_NUM_COLS = {"od_in", "weight_ppf", "setting_md", "setting_tvd", "hole_size_in", "top_md", "bottom_md",
             "length_ft", "weight_min", "weight_max", "md", "inclination", "azimuth", "tvd", "ns", "ew", "dls",
             "day", "planned_md", "qty", "unit_cost", "amount", "pore_ppg", "frac_ppg", "temp_f",
             "density_ppg", "volume_bbl"}


def _grid_dicts(db: Session, event_id: str, key: str, cols: list[str]) -> list[dict]:
    rows = _rows(db, event_id, key)
    out = []
    for r in rows:
        d = {}
        for c in cols:
            v = getattr(r, c, None)
            d[c] = (_f(v) if c in _NUM_COLS else v)
        out.append(d)
    # directional / casing / hole benefit from MD ordering
    if any(c in cols for c in ("md", "top_md", "setting_md")):
        keyname = "md" if "md" in cols else ("top_md" if "top_md" in cols else "setting_md")
        out.sort(key=lambda x: (x.get(keyname) is None, x.get(keyname) or 0))
    return out


# --- params store (scenario-aware: base vs alternative design cases) ---
DEFAULT_SCENARIO = "Base"


def get_params(db: Session, event_id: str, module: str, scenario: str = DEFAULT_SCENARIO) -> dict:
    row = db.execute(
        select(EngineeringDesign).where(
            EngineeringDesign.event_id == event_id,
            EngineeringDesign.module == module,
            EngineeringDesign.scenario == scenario,
        )
    ).scalars().first()
    return dict(row.params) if row and row.params else {}


def save_params(db: Session, event_id: str, module: str, params: dict, user_id=None,
                scenario: str = DEFAULT_SCENARIO) -> None:
    row = db.execute(
        select(EngineeringDesign).where(
            EngineeringDesign.event_id == event_id,
            EngineeringDesign.module == module,
            EngineeringDesign.scenario == scenario,
        )
    ).scalars().first()
    if row is None:
        db.add(EngineeringDesign(event_id=event_id, module=module, scenario=scenario,
                                 params=params, created_by=user_id))
    else:
        row.params = params
        row.updated_by = user_id
    db.commit()


def list_scenarios(db: Session, event_id: str, module: str) -> list[str]:
    """All saved scenario names for a module, Base first."""
    rows = db.execute(
        select(EngineeringDesign.scenario).where(
            EngineeringDesign.event_id == event_id, EngineeringDesign.module == module
        )
    ).scalars().all()
    names = sorted(set(rows) | {DEFAULT_SCENARIO}, key=lambda s: (s != DEFAULT_SCENARIO, s.lower()))
    return names


def delete_scenario(db: Session, event_id: str, module: str, scenario: str) -> None:
    if scenario == DEFAULT_SCENARIO:
        return
    row = db.execute(
        select(EngineeringDesign).where(
            EngineeringDesign.event_id == event_id,
            EngineeringDesign.module == module,
            EngineeringDesign.scenario == scenario,
        )
    ).scalars().first()
    if row is not None:
        db.delete(row)
        db.commit()
