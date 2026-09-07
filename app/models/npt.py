# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
# Importamos UUID de Postgres para tipar los ids
from sqlalchemy.dialects.postgresql import UUID
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin y SoftCloseMixin para heredar auditoría y cierre suave (sin borrado físico)
from app.models.mixins import AuditMixin, SoftCloseMixin


# Definimos el modelo de un evento de tiempo no productivo (NPT)
class NptEvent(OpsBase, AuditMixin, SoftCloseMixin):
    """Non-Productive Time. Never hard-deleted (SoftCloseMixin) — NPT is the
    knowledge-management record OpenWells builds failure-analysis metrics
    from, so history has to stay intact. `parent_id` supports the case where
    a single failure needs to be broken into related NPT entries."""

    # Nombramos la tabla
    __tablename__ = "npt_events"

    # Guardamos a qué reporte diario pertenece este evento
    daily_report_id = Column(UUID(as_uuid=True), ForeignKey("daily_reports.id"), nullable=False, index=True)

    # Guardamos a qué fila del resumen de tiempo está ligado (opcional)
    time_summary_row_id = Column(UUID(as_uuid=True), ForeignKey("time_summary_rows.id"), nullable=True)

    # Guardamos el evento padre cuando una falla se divide en varios eventos relacionados
    parent_id = Column(UUID(as_uuid=True), ForeignKey("npt_events.id"), nullable=True)

    # Guardamos el tipo de NPT
    npt_type = Column(String(100), nullable=True)  # Equipment Failure | Equipment Failure With NPT | NPT (No Failure)

    # Guardamos el título del evento
    title = Column(String(300), nullable=True)

    # Guardamos la descripción del evento
    description = Column(Text, nullable=True)

    # Guardamos la causa del evento
    cause = Column(String(300), nullable=True)

    # Guardamos cuándo empezó el evento
    start_time = Column(DateTime, nullable=True)

    # Guardamos cuándo terminó el evento
    end_time = Column(DateTime, nullable=True)

    # Guardamos las horas brutas de NPT
    gross_hours = Column(Numeric(6, 2), nullable=True)

    # Guardamos las horas netas de NPT
    net_hours = Column(Numeric(6, 2), nullable=True)

    # Guardamos la profundidad medida a la que ocurrió la falla
    failure_md = Column(Numeric(10, 2), nullable=True)

    # Guardamos el nombre del contratista involucrado
    contractor_name = Column(String(200), nullable=True)

    # Guardamos el tipo de documento contractual asociado
    contractual_link = Column(String(50), nullable=True)
    
    # Guardamos el número de ese documento contractual
    contractual_no = Column(String(50), nullable=True)

    # Guardamos el costo por tipo
    type_cost = Column(Numeric(12, 2), nullable=True)
    
    # Guardamos el costo de equipo
    equip_cost = Column(Numeric(12, 2), nullable=True)
    
    # Guardamos otros costos asociados
    other_cost = Column(Numeric(12, 2), nullable=True)

    # Guardamos el nombre de quien revisó el evento
    reviewer_name = Column(String(200), nullable=True)
    
    # Guardamos las acciones preventivas propuestas
    preventive_actions = Column(Text, nullable=True)
    
    # Guardamos las lecciones aprendidas del evento
    lessons_learned = Column(Text, nullable=True)
