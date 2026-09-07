"""Daily-cost carry-over: when a new daily report is created for an event that
already has an earlier report, the recurring cost lines (rig rate, mud
engineering, directional service, MWD rental...) almost always repeat. Rather
than re-key them each day, clone the previous report's cost lines into the new
one. The engineer then edits/adds the day's deltas. Mirrors OpenWells' daily
cost roll-forward."""
# Importamos select para consultar el reporte diario anterior
from sqlalchemy import select

# Importamos get_config para obtener la configuración (modelo y demás) del grid de costos
from app.models.capture import get_config
# Importamos DailyReport para ubicar el reporte diario previo del mismo evento
from app.models.daily_report import DailyReport
# Importamos GridRepository para leer/escribir filas de grids genéricos (aquí, líneas de costo)
from app.repositories.capture_repository import GridRepository


def carry_over_costs(db, new_report, created_by=None) -> int:
    """Copy the immediately-previous report's cost lines onto `new_report`.
    No-op (returns 0) if there's no earlier report or the new one already has
    cost rows. Returns the number of lines carried over."""
    # Obtenemos la configuración del grid "cost" (incluye el modelo ORM de las líneas de costo)
    cfg = get_config("cost")
    # Creamos el repositorio para leer/escribir sobre el nuevo reporte
    dest_repo = GridRepository(db, cfg.model)
    # Verificamos que el nuevo reporte no tenga ya líneas de costo, para no duplicarlas
    if dest_repo.list_for_report(new_report.id):
        return 0  # never duplicate onto a report that already has costs

    # Buscamos el reporte diario inmediatamente anterior del mismo evento
    prev = db.execute(
        select(DailyReport)
        .where(DailyReport.event_id == new_report.event_id, DailyReport.report_date < new_report.report_date)
        .order_by(DailyReport.report_date.desc())
    ).scalars().first()
    # Si no hay reporte previo, no hay nada que copiar
    if prev is None:
        return 0

    # Leemos las líneas de costo del reporte anterior para clonarlas
    src_rows = GridRepository(db, cfg.model).list_for_report(prev.id)
    Model = cfg.model
    # Creamos una copia de cada línea de costo apuntando al nuevo reporte, preservando el orden
    for i, row in enumerate(src_rows):
        db.add(Model(
            daily_report_id=new_report.id, sort_order=i,
            category=row.category, description=row.description, vendor=row.vendor,
            afe_code=row.afe_code, qty=row.qty, unit_cost=row.unit_cost, amount=row.amount,
            created_by=created_by,
        ))
    # Enviamos los inserts pendientes a la sesión (sin hacer commit todavía)
    db.flush()
    # Devolvemos la cantidad de líneas copiadas
    return len(src_rows)
