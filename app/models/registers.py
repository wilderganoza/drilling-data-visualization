"""Event-level operations registers — the running logs that span a whole event
rather than a single daily report: HSE incidents, BOP tests, equipment/personnel
certifications, the lessons-learned knowledge base, and the materials/inventory
stock. Same spec-driven grid engine as the daily-capture and well-plan program
subsections (Field/GridConfig + `_column_for`), but rows hang off the Event.

Reusing the one engine means a register is declared once here and gets its
SQLAlchemy model, its CRUD routes (app/ops/web/registers.py) and its grid
template for free — a column is added or renamed in exactly one place."""
# Importamos los tipos de columna que usamos para construir los modelos de registro
from sqlalchemy import Column, ForeignKey, Integer
# Importamos UUID de Postgres para tipar el id del evento
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para colgar cada registro del Event
from sqlalchemy.orm import relationship

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos Field/GridConfig (la spec de columnas) y _column_for (que las traduce a Column de SQLAlchemy)
from app.models.capture import Field, GridConfig, _column_for
# Importamos Event para colgarle la relación de cada registro
from app.models.hierarchy import Event
# Importamos AuditMixin para heredar los campos de auditoría en cada modelo generado
from app.models.mixins import AuditMixin

# Declaramos la lista de registros disponibles, uno por GridConfig
REGISTER_CONFIGS: list[GridConfig] = [
    # Definimos el registro de incidentes de HSE
    GridConfig(
        key="hse-incidents", title="HSE Incidents", table_name="ops_reg_hse_incidents",
        model_name="RegHseIncident", add_label="+ Add Incident",
        intro="Health, Safety & Environment register — near-misses, incidents, LTIs and spills, "
              "with immediate actions and root-cause follow-up.",
        fields=[
            Field("date", "Date"),
            Field("category", "Category", "select",
                  ("Near Miss", "First Aid", "Recordable", "LTI", "Spill", "Environmental", "Property Damage", "Fire")),
            Field("severity", "Severity", "select", ("Low", "Medium", "High", "Critical")),
            Field("title", "Title", table=True, span=2),
            Field("description", "What happened", "textarea", table=False, span=3),
            Field("immediate_action", "Immediate action", "textarea", table=False, span=3),
            Field("root_cause", "Root cause", "textarea", table=False, span=3),
            Field("status", "Status", "select", ("Open", "Investigating", "Closed")),
        ],
    ),
    # Definimos el registro de pruebas de BOP
    GridConfig(
        key="bop-tests", title="BOP Tests", table_name="ops_reg_bop_tests",
        model_name="RegBopTest", add_label="+ Add BOP Test",
        intro="Blowout-preventer function and pressure tests — the safety-critical record "
              "every regulator and operator audits.",
        fields=[
            Field("date", "Date"),
            Field("test_type", "Test type", "select", ("Function", "Pressure", "Function + Pressure")),
            Field("component", "Component", "select",
                  ("Annular", "Upper Rams", "Lower Rams", "Blind/Shear Rams", "Pipe Rams",
                   "Choke Line", "Kill Line", "HCR Valve", "Full Stack")),
            Field("low_psi", "Low (psi)", "number"),
            Field("high_psi", "High (psi)", "number"),
            Field("hold_min", "Hold (min)", "number"),
            Field("result", "Result", "select", ("Pass", "Fail", "Retest")),
            Field("next_due", "Next due"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el registro de certificaciones
    GridConfig(
        key="certifications", title="Certifications", table_name="ops_reg_certifications",
        model_name="RegCertification", add_label="+ Add Certificate",
        intro="Equipment and personnel certifications with expiry tracking — lifting gear, "
              "BOP, wireline, competencies. Flags what is due or expired.",
        fields=[
            Field("item", "Item / Equipment", table=True, span=2),
            Field("cert_type", "Type", "select", ("Equipment", "Personnel", "Inspection", "Competency", "Calibration")),
            Field("holder", "Holder / Owner"),
            Field("authority", "Issuing authority"),
            Field("issued", "Issued date"),
            Field("expires", "Expiry date"),
            Field("status", "Status", "select", ("Valid", "Due Soon", "Expired")),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el registro de lecciones aprendidas
    GridConfig(
        key="lessons-learned", title="Lessons Learned", table_name="ops_reg_lessons",
        model_name="RegLesson", add_label="+ Add Lesson",
        intro="Knowledge base of what worked and what did not — tie NPT and incidents back to "
              "concrete recommendations for the next well.",
        fields=[
            Field("date", "Date"),
            Field("category", "Category", "select",
                  ("Drilling", "Casing/Cementing", "Directional", "Fluids", "Well Control",
                   "Logistics", "HSE", "Equipment", "Planning", "Other")),
            Field("phase", "Phase"),
            Field("event_description", "What happened", "textarea", table=True, span=3),
            Field("lesson", "Lesson learned", "textarea", table=False, span=3),
            Field("recommendation", "Recommendation", "textarea", table=False, span=3),
            Field("npt_hours", "NPT impact (hr)", "number"),
            Field("impact", "Impact", "select", ("Low", "Medium", "High")),
        ],
    ),
    # Definimos el registro de materiales/inventario
    GridConfig(
        key="materials", title="Materials / Inventory", table_name="ops_reg_materials",
        model_name="RegMaterial", add_label="+ Add Material", compute_kind="stock",
        intro="Consumables and tubulars stock — planned vs received vs consumed. On-hand is "
              "computed (received − consumed).",
        fields=[
            Field("category", "Category", "select",
                  ("Mud / Chemicals", "Cement", "Bits", "Casing / Tubulars", "Fuel", "Water", "Wellhead", "Other")),
            Field("item", "Item", table=True, span=2),
            Field("unit", "Unit", "select", ("sx", "bbl", "gal", "ton", "ea", "jt", "ft", "L", "kg", "m³")),
            Field("planned_qty", "Planned", "number"),
            Field("received_qty", "Received", "number"),
            Field("consumed_qty", "Consumed", "number"),
            Field("on_hand", "On hand", "number", form=False),
            Field("unit_cost", "Unit cost", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
]


# Construimos dinámicamente la clase de modelo SQLAlchemy correspondiente a un GridConfig de registro
def _build_register_model(cfg: GridConfig) -> type:
    # Armamos los atributos base de la tabla: nombre, docstring, FK al evento y orden
    attrs = {
        "__tablename__": cfg.table_name,
        "__doc__": f"Event-level register rows for '{cfg.title}'. See app/ops/models/registers.py.",
        "event_id": Column(UUID(as_uuid=True), ForeignKey("ops_events.id"), nullable=False, index=True),
        "sort_order": Column(Integer, nullable=False, default=0),
    }
    # Recorremos los campos de la config y traducimos cada uno a su Column de SQLAlchemy
    for f in cfg.fields:
        attrs[f.name] = _column_for(f)
    # Creamos la clase de modelo dinámicamente con type(), heredando de OpsBase y AuditMixin
    return type(cfg.model_name, (OpsBase, AuditMixin), attrs)


# Indexamos cada config de registro por su key para poder resolverla en las rutas
REGISTER_CONFIG_BY_KEY: dict[str, GridConfig] = {}
# Recorremos todas las configs de registro para construir su modelo y su relación
for _cfg in REGISTER_CONFIGS:
    # Construimos y guardamos el modelo SQLAlchemy generado para esta config
    _cfg.model = _build_register_model(_cfg)
    # Registramos la config en el diccionario indexado por key
    REGISTER_CONFIG_BY_KEY[_cfg.key] = _cfg
    # Agregamos dinámicamente la relación del registro sobre el modelo Event
    setattr(Event, f"reg_{_cfg.key.replace('-', '_')}_rows",
            relationship(_cfg.model, cascade="all, delete-orphan"))


# Buscamos la config de un registro por su key
def get_register_config(key: str):
    # Devolvemos la config si existe, o None si no
    return REGISTER_CONFIG_BY_KEY.get(key)
