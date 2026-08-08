"""Per-report-type field validation, mirroring OpenWells' mandatory-vs-notify
distinction: mandatory violations block saving the subsection, notify
violations are surfaced but don't.

The field-level rules are now DB-backed and admin-editable (ops_validation_rules,
seeded from DEFAULT_GENERAL_RULES). On top of them the engine runs a few
report-level cross-field checks that need more than the submitted form
(MD monotonic vs the previous day, TVD ≤ MD, Time-Summary hours ≈ 24)."""
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.validation import ValidationRule


@dataclass
class Violation:
    field: str
    level: str  # "mandatory" | "notify"
    message: str


# Seed defaults for a fresh ops_validation_rules table (report_type="general").
# (field_name, level, check, param1, param2, field_name2, message)
DEFAULT_GENERAL_RULES = [
    ("dol", "mandatory", "required", None, None, None, "DOL (Days on Location) is required."),
    ("dfs", "mandatory", "required", None, None, None, "DFS (Days From Spud) is required."),
    ("md", "mandatory", "nonzero", None, None, None, "MD is required and must never be 0."),
    ("rotating_hrs", "notify", "both_blank_notify", None, None, "sliding_hrs", "No rotating or sliding hours have been entered."),
    ("current_status", "notify", "required", None, None, None, "Current Status of the operation is missing."),
]


def _blank(v) -> bool:
    return v in (None, "")


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _rule_violated(rule: ValidationRule, data: dict[str, Any]) -> bool:
    v = data.get(rule.field_name)
    check = rule.check
    if check == "required":
        return _blank(v)
    if check == "nonzero":
        n = _num(v)
        return n is None or n == 0
    if check == "both_blank_notify":
        return _blank(v) and _blank(data.get(rule.field_name2))
    n = _num(v)
    if check == "gt":
        return n is not None and rule.param1 is not None and n <= float(rule.param1)
    if check == "lt":
        return n is not None and rule.param1 is not None and n >= float(rule.param1)
    if check == "range":
        if n is None:
            return False
        lo = float(rule.param1) if rule.param1 is not None else None
        hi = float(rule.param2) if rule.param2 is not None else None
        return (lo is not None and n < lo) or (hi is not None and n > hi)
    return False


def validate_general(db: Session, data: dict[str, Any], report=None) -> list[Violation]:
    rules = db.execute(
        select(ValidationRule).where(ValidationRule.report_type == "general", ValidationRule.is_active == True)  # noqa: E712
        .order_by(ValidationRule.sort_order)
    ).scalars().all()
    violations = [Violation(r.field_name, r.level, r.message) for r in rules if _rule_violated(r, data)]

    # --- cross-field / report-level checks ---
    md = _num(data.get("md"))
    tvd = _num(data.get("tvd"))
    prev_md = _num(data.get("previous_md"))
    if md is not None and tvd is not None and tvd > md + 0.01:
        violations.append(Violation("tvd", "notify", "TVD should not be greater than MD."))
    if md is not None and prev_md is not None and md < prev_md - 0.01:
        violations.append(Violation("md", "notify", "MD is less than the previous day's depth (previous MD)."))

    if report is not None:
        ts_total = _time_summary_hours(db, report.id)
        if ts_total is not None and abs(ts_total - 24.0) > 0.5:
            violations.append(Violation("md", "notify", f"Time Summary hours add up to {ts_total:.1f} h (~24 h expected)."))
    return violations


def _time_summary_hours(db: Session, report_id) -> Optional[float]:
    from app.repositories.time_summary_repository import TimeSummaryRowRepository
    rows = TimeSummaryRowRepository(db).list_for_report(report_id)
    if not rows:
        return None
    total = 0.0
    for r in rows:
        if not r.time_from or not r.time_to:
            continue
        try:
            h1, m1 = (int(x) for x in r.time_from.split(":"))
            h2, m2 = (int(x) for x in r.time_to.split(":"))
        except ValueError:
            continue
        mins = (h2 * 60 + m2) - (h1 * 60 + m1)
        if mins < 0:
            mins += 24 * 60
        total += mins / 60.0
    return total


def has_mandatory(violations: list[Violation]) -> bool:
    return any(v.level == "mandatory" for v in violations)
