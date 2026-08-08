"""Unit tests for the pre-spud engineering calculators.

Pure-function tests over a synthetic WellContext (no DB) so the physics is
pinned against known values and invariants: real API tubular geometry, Barlow /
API-5C3 casing ratings, biaxial/thermal/buckling/fatigue, seat selection inside
the pore-fracture window, kill-sheet, stiff-string T&D, transient surge and
program validation."""
import math

import pytest

from app.services.engineering import (
    casing_design, swab_surge, torque_drag, tubular_catalog, well_control, hydraulics,
)
from app.services.engineering.context import WellContext
from app.services.planning_validation import validate_program


def make_ctx(mud_prod_min=9.8):
    ctx = WellContext(event_id="test")
    ctx.directional = [
        {"md": 0, "tvd": 0, "inclination": 0, "azimuth": 0},
        {"md": 3000, "tvd": 3000, "inclination": 0, "azimuth": 0},
        {"md": 12000, "tvd": 11000, "inclination": 22, "azimuth": 142},
    ]
    ctx.geopressure = [
        {"md": 0, "tvd": 0, "pore_ppg": 8.5, "frac_ppg": 11.0, "temp_f": 60},
        {"md": 6000, "tvd": 5800, "pore_ppg": 8.8, "frac_ppg": 14.5, "temp_f": 160},
        {"md": 12000, "tvd": 11000, "pore_ppg": 9.4, "frac_ppg": 17.0, "temp_f": 250},
    ]
    ctx.casing = [
        {"string": "Surface", "od_in": 13.375, "weight_ppf": 68, "grade": "K-55",
         "connection": "BTC", "setting_md": 3000, "setting_tvd": 3000},
        {"string": "Production", "od_in": 9.625, "weight_ppf": 47, "grade": "N-80",
         "connection": "VAM", "setting_md": 12000, "setting_tvd": 11000},
    ]
    ctx.hole = [
        {"section": "Surface", "hole_size_in": 17.5, "top_md": 0, "bottom_md": 3000},
        {"section": "Production", "hole_size_in": 12.25, "top_md": 3000, "bottom_md": 12000},
    ]
    ctx.mud = [
        {"section": "Surface", "mud_type": "WBM", "top_md": 0, "bottom_md": 3000, "weight_min": 9.0, "weight_max": 9.5},
        {"section": "Production", "mud_type": "OBM", "top_md": 3000, "bottom_md": 12000, "weight_min": mud_prod_min, "weight_max": 10.8},
    ]
    ctx.cement = [
        {"string": "Production", "slurry_type": "G", "density_ppg": 15.8, "volume_bbl": 300, "top_md": 3000, "bottom_md": 12000},
    ]
    return ctx


# --------------------------------------------------------------------------- catalog
def test_catalog_geometry():
    t = tubular_catalog.lookup(9.625, 47)
    assert t is not None
    assert t.wall == pytest.approx(0.472, abs=0.001)
    assert t.id_in == pytest.approx(8.681, abs=0.001)
    assert t.drift == pytest.approx(8.525, abs=0.001)


def test_grade_yield_and_ultimate():
    assert tubular_catalog.grade_yield("P-110") == 110000
    assert tubular_catalog.grade_yield("N-80") == 80000
    assert tubular_catalog.grade_ultimate("P-110") >= tubular_catalog.grade_yield("P-110")
    assert tubular_catalog.grade_yield("nonsense") == 80000  # sane default


def test_connection_resolution():
    assert tubular_catalog.connection("BTC").gas_tight is False
    assert tubular_catalog.connection("BTC").eff_tension == pytest.approx(0.95)
    assert tubular_catalog.connection("VAM TOP").gas_tight is True
    assert tubular_catalog.connection("TenarisHydril Blue").gas_tight is True


# --------------------------------------------------------------------------- casing physics
def test_barlow_burst():
    # 0.875·2·Yp·t/OD
    r = casing_design._burst_rating(9.625, 0.472, 80000)
    assert r == pytest.approx(0.875 * 2 * 80000 * 0.472 / 9.625, rel=1e-6)


def test_collapse_thinner_is_weaker():
    thick = casing_design._collapse_rating(9.625, 0.545, 80000)
    thin = casing_design._collapse_rating(9.625, 0.352, 80000)
    assert thick > thin > 0


def test_biaxial_reduces_collapse_under_tension():
    pc = 5000.0
    assert casing_design._biaxial_collapse(pc, 0.0, 80000) == pytest.approx(pc)
    assert casing_design._biaxial_collapse(pc, 40000.0, 80000) < pc


def test_thermal_force_is_compression_on_heating():
    area = casing_design._area(9.625, 8.681)
    f = casing_design._thermal_force(area, 50)   # heating
    assert f < 0
    assert f == pytest.approx(-casing_design.E_STEEL * casing_design.ALPHA_STEEL * area * 50, rel=1e-9)


def test_buckling_thresholds_ordered():
    mode, f_sin, f_hel, sig = casing_design._buckling(9.625, 8.681, 47, 30, 1.3, 0.0)
    assert f_hel > f_sin > 0
    assert mode == "none"                      # no compression → no buckling
    mode2, *_ = casing_design._buckling(9.625, 8.681, 47, 30, 1.3, f_hel * 1.1)
    assert mode2 == "helical"


def test_fatigue_higher_dogleg_lower_sf():
    _, _, sf_low = casing_design._fatigue(9.625, 2.0, 100000)
    _, _, sf_high = casing_design._fatigue(9.625, 8.0, 100000)
    assert sf_low > sf_high > 0


def test_casing_compute_has_all_criteria():
    ctx = make_ctx()
    res = casing_design.compute({}, ctx)
    assert len(res["strings"]) == 2
    s = res["strings"][-1]
    for k in ("sf_burst", "sf_collapse", "sf_triaxial", "sf_conn_tension", "sf_conn_leak",
              "buckle_mode", "thermal_force", "sf_fatigue", "sf_triaxial_buckled"):
        assert k in s
    assert s["sf_burst"] > 0
    # production string uses a gas-tight premium connection → gas_ok True
    assert s["gas_ok"] is True


# --------------------------------------------------------------------------- seat selection
def test_seat_selection_telescopes_and_in_window():
    ctx = make_ctx()
    seats = casing_design.select_seats(ctx, 0.4, 0.3, 0.3, 300)
    assert seats == sorted(seats)                 # ascending, surface → TD
    assert seats[-1] == pytest.approx(ctx.td_tvd(), abs=1)
    mud = casing_design.generate_rows({}, ctx, "mud-program")
    for row in mud:
        tvd = ctx.tvd_at(row["bottom_md"])
        pore = ctx.pore_at(tvd)
        assert row["weight_min"] >= pore - 0.15   # mud ≥ pore (well control)


def test_hole_program_telescopes():
    ctx = make_ctx()
    holes = casing_design.generate_rows({}, ctx, "hole-program")
    sizes = [h["hole_size_in"] for h in holes]
    assert sizes == sorted(sizes, reverse=True)   # each section ≤ the one above


# --------------------------------------------------------------------------- context interpolation
def test_pore_frac_interpolation_and_inverse():
    ctx = make_ctx()
    assert 8.5 <= ctx.pore_at(5800) <= 9.4
    assert ctx.frac_at(11000) == pytest.approx(17.0, abs=0.1)
    md = ctx.md_at_tvd(3000)
    assert ctx.tvd_at(md) == pytest.approx(3000, abs=50)


# --------------------------------------------------------------------------- well control
def test_kill_sheet_kmw_and_maasp():
    ctx = make_ctx()
    res = well_control.compute({"mw": 9.9, "sidpp": 350}, ctx)
    assert res["kmw"] > 9.9                        # SIDPP raises kill mud weight
    assert res["maasp"] > 0


# --------------------------------------------------------------------------- T&D stiff-string
def test_td_stiff_ge_soft():
    ctx = make_ctx()
    s = torque_drag.compute({}, ctx)["summary"]
    assert s["pct_drag_stiff"] >= 0
    assert s["pct_torque_stiff"] >= 0
    assert s["hookload_pooh_stiff"] >= s["hookload_pooh"]
    assert s["surface_torque_drill_stiff"] >= s["surface_torque_drill"]
    # pick-up > rotating > slack-off tension ordering
    assert s["hookload_pooh"] >= s["hookload_rot"] >= s["hookload_rih"]


# --------------------------------------------------------------------------- surge (steady-state)
def test_surge_steady_state():
    ctx = make_ctx()
    r = swab_surge.compute({}, ctx)
    assert r["surge_dp"] >= 0
    assert r["surge_emw"] >= r["swab_emw"]          # surge adds, swab subtracts
    assert r["max_safe_speed"] >= 0
    assert "surge_dp_trans" not in r                # no transient outputs remain


# --------------------------------------------------------------------------- hydraulics
def test_hydraulics_basic():
    ctx = make_ctx()
    r = hydraulics.compute({}, ctx)
    assert r["spp"] > 0
    assert 0 < r["n"] <= 1.2
    assert r["ecd_td"] >= r.get("pore_emw", 0)


# --------------------------------------------------------------------------- validation
def test_validation_flags_mud_below_pore():
    bad = make_ctx(mud_prod_min=8.0)     # production mud below pore at TD (9.4)
    report = validate_program(bad)
    assert report["fails"] >= 1
    assert any(c["area"] == "Mud" and c["severity"] == "fail" for c in report["checks"])


def test_validation_passes_coherent_program():
    good = make_ctx(mud_prod_min=9.8)
    report = validate_program(good)
    mud_fails = [c for c in report["checks"] if c["area"] == "Mud" and c["severity"] == "fail"]
    assert not mud_fails
