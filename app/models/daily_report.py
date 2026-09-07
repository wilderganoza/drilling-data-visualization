# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
# Importamos UUID de Postgres para tipar el id del evento
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para declarar las relaciones hacia time summary y NPT
from sqlalchemy.orm import relationship
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin


# Definimos el modelo del reporte diario de operaciones
class DailyReport(OpsBase, AuditMixin):
    """One report per Event per calendar day (06:00-06:00 per OpenWells
    convention). General subsection fields live directly on this model since
    it's a 1:1 relationship — once more subsections are active, a dedicated
    ops_report_section_status table (per the plan) is worth the extra join."""

    # Nombramos la tabla
    __tablename__ = "daily_reports"
    
    # Garantizamos un solo reporte por evento y fecha
    __table_args__ = (UniqueConstraint("event_id", "report_date", name="uq_daily_report_event_date"),)

    # Guardamos a qué evento pertenece el reporte
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    
    # Guardamos la fecha del reporte
    report_date = Column(Date, nullable=False)
    
    # Guardamos el número consecutivo del reporte
    report_no = Column(Integer, nullable=True)
    
    # Guardamos una descripción corta del reporte
    description = Column(String(300), nullable=True)

    # Guardamos los campos de la subsección General
    # Guardamos el nombre del supervisor
    supervisor = Column(String(200), nullable=True)
    
    # Guardamos el nombre del ingeniero
    engineer = Column(String(200), nullable=True)
    
    # Guardamos el nombre del geólogo
    geologist = Column(String(200), nullable=True)
    
    # Guardamos los días desde el inicio de la operación (DOL)
    dol = Column(Numeric(6, 2), nullable=True)
    
    # Guardamos los días desde el spud (DFS)
    dfs = Column(Numeric(6, 2), nullable=True)
    
    # Guardamos la profundidad medida del día anterior
    previous_md = Column(Numeric(10, 2), nullable=True)
    
    # Guardamos la profundidad medida actual
    md = Column(Numeric(10, 2), nullable=True)
    
    # Guardamos la profundidad vertical verdadera actual
    tvd = Column(Numeric(10, 2), nullable=True)
    
    # Guardamos el avance del día (progress)
    progress = Column(Numeric(10, 2), nullable=True)
    
    # Guardamos las horas rotando
    rotating_hrs = Column(Numeric(6, 2), nullable=True)
    
    # Guardamos las horas deslizando
    sliding_hrs = Column(Numeric(6, 2), nullable=True)
    
    # Guardamos el tamaño de hoyo actual
    hole_size = Column(Numeric(6, 3), nullable=True)
    
    # Guardamos la formación actual
    formation = Column(String(200), nullable=True)
    
    # Guardamos la litología actual
    lithology = Column(String(200), nullable=True)
    
    # Guardamos el estado actual de la operación
    current_status = Column(Text, nullable=True)
    
    # Guardamos el resumen de las últimas 24 horas
    summary_24hr = Column(Text, nullable=True)
    
    # Guardamos el pronóstico para las próximas 24 horas
    forecast_24hr = Column(Text, nullable=True)
    
    # Guardamos si la subsección General está completa
    general_complete = Column(Boolean, default=False, nullable=False)

    # Manejamos el flujo de aprobación: Draft -> Submitted -> Approved. Una vez aprobado el
    # reporte queda bloqueado (sin más ediciones) — es el registro de auditoría de lo reportado.
    # Guardamos el estado del flujo de aprobación
    workflow_status = Column(String(20), default="Draft", nullable=False)  # Draft | Submitted | Approved
    
    # Guardamos si el reporte está bloqueado para edición
    is_locked = Column(Boolean, default=False, nullable=False)
    
    # Guardamos cuándo se envió el reporte
    submitted_at = Column(DateTime, nullable=True)
    
    # Guardamos quién envió el reporte
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Guardamos cuándo se aprobó el reporte
    approved_at = Column(DateTime, nullable=True)
    
    # Guardamos quién aprobó el reporte
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relacionamos el reporte con sus filas de resumen de tiempo (se borran en cascada)
    time_summary_rows = relationship("TimeSummaryRow", cascade="all, delete-orphan")
    
    # Relacionamos el reporte con sus eventos de NPT (se borran en cascada)
    npt_events = relationship("NptEvent", cascade="all, delete-orphan")
