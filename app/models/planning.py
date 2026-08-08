# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
# Importamos UUID de Postgres para tipar el id del evento
from sqlalchemy.dialects.postgresql import UUID

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin


# Definimos el modelo del plan de pozo (cabecera del programa de perforación)
class WellPlan(OpsBase, AuditMixin):
    """Well Planning / AFE — one per Event. The header of the well program:
    objectives, targets, trajectory design intent, rig, schedule and the AFE
    cost summary. The detailed technical programs (casing, hole, mud, cement,
    directional, time-depth, cost estimate, risks) live in their own program
    tables (app/ops/models/planning_capture.py), each hanging off the Event."""

    # Nombramos la tabla
    __tablename__ = "ops_well_plans"

    # Guardamos a qué evento pertenece el plan (uno por evento)
    event_id = Column(UUID(as_uuid=True), ForeignKey("ops_events.id"), nullable=False, unique=True, index=True)

    # Guardamos los datos de AFE / aprobación
    # Guardamos el número de AFE
    afe_number = Column(String(100), nullable=True)
    # Guardamos la descripción del plan
    description = Column(String(500), nullable=True)
    # Guardamos el nombre de quien aprobó (texto libre, histórico)
    approved_by = Column(String(200), nullable=True)
    # Guardamos el nombre del ingeniero responsable
    engineer = Column(String(200), nullable=True)
    # Guardamos el estado del plan
    status = Column(String(50), nullable=True)  # Draft | Submitted | Approved | Superseded
    # Guardamos la fecha de autorización
    authorized_date = Column(Date, nullable=True)

    # Manejamos el flujo de aprobación (Draft -> Submitted -> Approved). Aprobar bloquea el plan.
    # Guardamos si el plan está bloqueado
    is_locked = Column(Boolean, default=False, nullable=False, server_default="false")
    # Guardamos cuándo se envió el plan
    submitted_at = Column(DateTime, nullable=True)
    # Guardamos quién envió el plan
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Guardamos cuándo se aprobó el plan
    approved_at = Column(DateTime, nullable=True)
    # Guardamos quién aprobó el plan (usuario real, no texto libre)
    approved_by_user = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Guardamos los objetivos y la geología
    # Guardamos el objetivo primario
    objective_primary = Column(Text, nullable=True)
    # Guardamos el objetivo secundario
    objective_secondary = Column(Text, nullable=True)
    # Guardamos la formación objetivo
    target_formation = Column(String(200), nullable=True)
    # Guardamos el pronóstico geológico
    geology_prognosis = Column(Text, nullable=True)

    # Guardamos los objetivos de diseño
    # Guardamos la profundidad medida autorizada
    authorized_md = Column(Numeric(10, 2), nullable=True)
    # Guardamos la profundidad vertical verdadera autorizada
    authorized_tvd = Column(Numeric(10, 2), nullable=True)
    # Guardamos el punto de desviación (kick-off point)
    kop_md = Column(Numeric(10, 2), nullable=True)          # kick-off point
    # Guardamos la inclinación máxima
    max_inclination = Column(Numeric(6, 2), nullable=True)
    # Guardamos el azimut objetivo
    target_azimuth = Column(Numeric(6, 2), nullable=True)

    # Guardamos los datos del taladro y el cronograma
    # Guardamos el nombre del taladro
    rig_name = Column(String(200), nullable=True)
    # Guardamos el tipo de taladro
    rig_type = Column(String(100), nullable=True)
    # Guardamos la fecha planeada de spud
    planned_spud_date = Column(Date, nullable=True)
    # Guardamos los días estimados de operación
    est_days = Column(Numeric(6, 2), nullable=True)

    # Guardamos la ubicación de superficie
    # Guardamos la descripción de la ubicación de superficie
    surface_location = Column(String(300), nullable=True)
    # Guardamos el norting de superficie
    surface_northing = Column(Numeric(14, 2), nullable=True)
    # Guardamos el easting de superficie
    surface_easting = Column(Numeric(14, 2), nullable=True)

    # Guardamos el resumen de costos (roll-up del AFE)
    # Guardamos la moneda del presupuesto
    currency = Column(String(10), nullable=True)            # USD, etc.
    # Guardamos el costo de pozo seco
    dry_hole_cost = Column(Numeric(16, 2), nullable=True)
    # Guardamos el costo de completación
    completion_cost = Column(Numeric(16, 2), nullable=True)
    # Guardamos el porcentaje de contingencia
    contingency_pct = Column(Numeric(6, 2), nullable=True)
    # Guardamos el presupuesto total
    budget_total = Column(Numeric(16, 2), nullable=True)
