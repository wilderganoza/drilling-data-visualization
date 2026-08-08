"""Tests for the Analytics / ML submodules.

Pure-function tests (no DB) for the NPT taxonomy classifier and the learning-curve
power-law fit, plus DB-backed smoke tests that run each `analyze()` against the
seeded operational data and assert its contract + basic invariants. The DB tests
skip cleanly when no database is configured (e.g. bare CI)."""
import types

import pytest

from app.models.capture import CONFIG_BY_KEY, compute_values
from app.services.analytics_ml import learning, npt_analytics


# --------------------------------------------------------------------------- pure: NPT taxonomy
def _npt(npt_type="", cause="", title=""):
    return types.SimpleNamespace(npt_type=npt_type, cause=cause, title=title)


def test_npt_categorize():
    assert npt_analytics.categorize(_npt(cause="Stuck pipe while POOH")) == "Stuck Pipe"
    assert npt_analytics.categorize(_npt(cause="Well control — influx / kick")) == "Well Control"
    assert npt_analytics.categorize(_npt(cause="Squeeze cement job")) == "Cementing"
    assert npt_analytics.categorize(_npt()) == "Other"
    # every result is a member of the taxonomy
    assert npt_analytics.categorize(_npt(cause="anything")) in npt_analytics.NPT_CATEGORIES


# --------------------------------------------------------------------------- pure: learning curve
def test_power_fit_recovers_known_curve():
    # y = 100·n^b with b = log2(0.8) → rate (1−2^b) = 0.20
    pts = [(1, 100.0), (2, 80.0), (4, 64.0)]
    fit = learning._power_fit(pts)
    assert fit is not None
    assert fit["b"] == pytest.approx(-0.3219, abs=0.01)
    assert fit["rate"] == pytest.approx(0.20, abs=0.01)
    assert fit["r2"] >= 0.99


def test_power_fit_needs_three_points():
    assert learning._power_fit([(1, 100.0), (2, 80.0)]) is None


# --------------------------------------------------------------------------- pure: MSE (Teale)
def test_mse_compute():
    cfg = CONFIG_BY_KEY["drill-params"]
    v = compute_values(cfg, {"bit_size": 12.25, "wob": 35, "rpm": 120, "torque_ftlb": 12000, "rop": 60})
    assert v["mse_ksi"] == pytest.approx(77.1, abs=0.5)
    # no ROP → no MSE (guarded)
    assert "mse_ksi" not in compute_values(cfg, {"bit_size": 12.25, "wob": 35, "rop": 0})


# --------------------------------------------------------------------------- DB-backed smoke
@pytest.fixture(scope="module")
def db():
    try:
        from app.db.session import db_manager, get_db
        db_manager.initialize()
        return next(get_db())
    except Exception as exc:  # pragma: no cover - env without DB
        pytest.skip(f"no database available: {exc}")


@pytest.fixture(scope="module")
def event_id(db):
    from app.models.hierarchy import Event
    ev = db.query(Event).first()
    if ev is None:
        pytest.skip("no events in database")
    return str(ev.id)


def test_forecast_contract(db, event_id):
    from app.services.analytics_ml import forecast
    r = forecast.analyze(db, event_id)
    assert "ok" in r and "kpis" in r
    if r["ok"]:
        assert r["kpis"]["BAC"] is not None


def test_learning_contract(db):
    r = learning.analyze(db)
    for k in ("wells", "lessons_by_category", "n_wells"):
        assert k in r


def test_npt_contract(db):
    r = npt_analytics.analyze(db)
    for k in ("categories_stats", "anomalies", "total_events", "npt_risk_index"):
        assert k in r
    for c in r["categories_stats"]:
        assert c["category"] in npt_analytics.NPT_CATEGORIES


def test_rop_contract(db, event_id):
    from app.services.analytics_ml import rop
    r = rop.analyze(db, event_id)
    assert "ok" in r and "points" in r and "founder" in r


def test_dysfunction_contract_and_health(db, event_id):
    from app.services.analytics_ml import dysfunction
    r = dysfunction.analyze(db, event_id)
    assert "ok" in r
    if r["ok"]:
        assert 0 <= r["health_score"] <= 100
        # tuned heuristics: a normally-drilled well is not all-red
        assert r["summary"]["n_flags"] < r["summary"]["n_points"]


def test_cleaning_contract(db):
    from app.services.analytics_ml import cleaning
    r = cleaning.analyze(db)
    for k in ("params_stats", "outliers", "total_points", "has_data"):
        assert k in r
