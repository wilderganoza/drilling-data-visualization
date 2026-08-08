"""Pre-spud engineering designs — Torque & Drag, Hydraulics, Well Control,
Casing Design, Cementing, Directional/anti-collision, BHA, Bit selection and
the AFE builder. Each is a calculator: it stores its input parameters (as a
JSON blob, one row per event+module) and computes results on the fly from those
inputs plus the well's existing Planning program grids (casing/hole/mud/
directional). Keeping inputs in one flexible table avoids a migration per
module while the calc engines live in app/ops/services/engineering/."""
# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
# Importamos JSONB para guardar los parámetros del calculador y UUID para el id del evento
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin

# Listamos las claves válidas de módulo de ingeniería
MODULES = (
    "casing_design", "torque_drag", "hydraulics", "well_control",
    "cementing", "directional", "bha", "bit", "afe",
)


# Definimos el modelo que guarda los parámetros de un diseño de ingeniería
class EngineeringDesign(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "ops_engineering_designs"
    # Garantizamos que solo exista un diseño por evento+módulo+escenario
    __table_args__ = (UniqueConstraint("event_id", "module", "scenario", name="uq_eng_design_event_module_scenario"),)

    # Guardamos a qué evento pertenece este diseño
    event_id = Column(UUID(as_uuid=True), ForeignKey("ops_events.id"), nullable=False, index=True)
    # Guardamos a qué módulo de ingeniería pertenece (una de las claves en MODULES)
    module = Column(String(40), nullable=False, index=True)
    # Guardamos el nombre del escenario/caso de diseño
    scenario = Column(String(60), nullable=False, default="Base", server_default="Base")  # design case (base vs alternative)
    # Guardamos los parámetros de entrada del calculador como JSON
    params = Column(JSONB, nullable=False, default=dict)
