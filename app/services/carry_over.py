"""Daily-cost carry-over: when a new daily report is created for an event that
already has an earlier report, the recurring cost lines (rig rate, mud
engineering, directional service, MWD rental...) almost always repeat. Rather
than re-key them each day, clone the previous report's cost lines into the new
one. The engineer then edits/adds the day's deltas. Mirrors OpenWells' daily
cost roll-forward."""
from sqlalchemy import select

from app.models.capture import get_config
from app.models.daily_report import DailyReport
from app.repositories.capture_repository import GridRepository


def carry_over_costs(db, new_report, created_by=None) -> int:
    """Copy the immediately-previous report's cost lines onto `new_report`.
    No-op (returns 0) if there's no earlier report or the new one already has
    cost rows. Returns the number of lines carried over."""
    cfg = get_config("cost")
    dest_repo = GridRepository(db, cfg.model)
    if dest_repo.list_for_report(new_report.id):
        return 0  # never duplicate onto a report that already has costs

    prev = db.execute(
        select(DailyReport)
        .where(DailyReport.event_id == new_report.event_id, DailyReport.report_date < new_report.report_date)
        .order_by(DailyReport.report_date.desc())
    ).scalars().first()
    if prev is None:
        return 0

    src_rows = GridRepository(db, cfg.model).list_for_report(prev.id)
    Model = cfg.model
    for i, row in enumerate(src_rows):
        db.add(Model(
            daily_report_id=new_report.id, sort_order=i,
            category=row.category, description=row.description, vendor=row.vendor,
            afe_code=row.afe_code, qty=row.qty, unit_cost=row.unit_cost, amount=row.amount,
            created_by=created_by,
        ))
    db.flush()
    return len(src_rows)
