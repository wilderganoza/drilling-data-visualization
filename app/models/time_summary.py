# Importamos los tipos de columna que usamos en las tablas
from sqlalchemy import Column, ForeignKey, Integer, String, Text
# Importamos UUID de Postgres para tipar el id del reporte diario
from sqlalchemy.dialects.postgresql import UUID
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin


# Definimos el catálogo de referencia de combinaciones Fase/Paso/Operación
class StepCatalogEntry(OpsBase, AuditMixin):
    """Reference catalog of Fase/Step/Operation combinations used to
    auto-fill Phase in Time Summary rows, seeded per rig profile (horizontal
    vs. vertical) from the operator's own consolidated step tables. `version`
    lets a revised catalog be introduced without rewriting history on rows
    that already reference an older one."""

    # Nombramos la tabla
    __tablename__ = "step_catalog"

    # Guardamos el perfil del taladro al que aplica esta entrada
    profile = Column(String(50), nullable=False, index=True)  # "horizontal" | "vertical"

    # Guardamos la versión del catálogo
    version = Column(String(20), nullable=False, default="v1")

    # Guardamos el número de paso
    step_no = Column(Integer, nullable=False)

    # Guardamos la fase asociada al paso
    phase = Column(String(50), nullable=False)

    # Guardamos la descripción de la operación
    operation = Column(String(300), nullable=False)

# Definimos una fila del resumen de tiempo (bitácora de actividad de 24 horas)
class TimeSummaryRow(OpsBase, AuditMixin):
    """One row of the Daily Operations Report's Time Summary — the 24-hour
    (06:00-06:00) activity log. `sort_order` drives display order and is
    what the grid's move-up/move-down actions swap between adjacent rows."""

    # Nombramos la tabla
    __tablename__ = "time_summary_rows"

    # Guardamos a qué reporte diario pertenece esta fila
    daily_report_id = Column(UUID(as_uuid=True), ForeignKey("daily_reports.id"), nullable=False, index=True)

    # Guardamos el orden de la fila dentro del reporte
    sort_order = Column(Integer, nullable=False, default=0)

    # Guardamos la hora de inicio de la actividad
    time_from = Column(String(5), nullable=True)  # "HH:MM"

    # Guardamos la hora de fin de la actividad
    time_to = Column(String(5), nullable=True)

    # Guardamos el número de paso (del catálogo)
    step_no = Column(Integer, nullable=True)

    # Guardamos la fase de la actividad
    phase = Column(String(50), nullable=True)

    # Guardamos la clase de operación (Productiva / NPT / Standby-Contract)
    op_class = Column(String(10), nullable=True)  # P / NPT / SC

    # Guardamos el código de la operación
    op_code = Column(String(50), nullable=True)

    # Guardamos el detalle de la operación
    operation_detail = Column(Text, nullable=True)
