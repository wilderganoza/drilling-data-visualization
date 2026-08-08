"""Spec-driven Well-Plan *program* subsections — the technical program a
drilling engineer builds before spud: formation prognosis, casing/hole/mud/
cement programs, the planned directional trajectory, the time–depth (AFE)
curve, the cost estimate and the risk register.

Same generic grid engine as the daily-report capture subsections, but these
rows hang off the Event (the thing being planned) rather than a daily report.
Reuses the `Field`/`GridConfig` dataclasses and `_column_for` from
app/ops/models/capture.py so a program column is declared in exactly one place."""
# Importamos los tipos de columna que usamos para construir los modelos de programa
from sqlalchemy import Column, ForeignKey, Integer
# Importamos UUID de Postgres para tipar el id del evento
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para colgar cada programa del Event
from sqlalchemy.orm import relationship

# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos Field/GridConfig (la spec de columnas) y _column_for (que las traduce a Column de SQLAlchemy)
from app.models.capture import Field, GridConfig, _column_for
# Importamos Event para colgarle la relación de cada programa
from app.models.hierarchy import Event
# Importamos AuditMixin para heredar los campos de auditoría en cada modelo generado
from app.models.mixins import AuditMixin

# Declaramos la lista de programas del plan de pozo, uno por GridConfig
PLAN_CONFIGS: list[GridConfig] = [
    # Definimos el programa de topes formacionales
    GridConfig(
        key="formation-tops", title="Formation Tops", table_name="ops_plan_formation_tops",
        model_name="PlanFormationTop", add_label="+ Add Formation",
        intro="Predicted geological prognosis — formation tops the well is expected to penetrate.",
        fields=[
            Field("formation", "Formation", table=True, span=2),
            Field("md", "Prognosed MD (ft)", "number"),
            Field("tvd", "Prognosed TVD (ft)", "number"),
            Field("lithology", "Lithology", span=2),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el programa de geopresión
    GridConfig(
        key="geopressure", title="Geopressure", table_name="ops_plan_geopressure",
        model_name="PlanGeopressure", add_label="+ Add Point",
        intro="Pore-pressure / fracture-gradient profile (equivalent mud weight). The single shared basis every engineering module reads for the operating window, casing seat selection, mud program and well control.",
        fields=[
            Field("md", "MD (ft)", "number"),
            Field("tvd", "TVD (ft)", "number"),
            Field("pore_ppg", "Pore (ppg EMW)", "number"),
            Field("frac_ppg", "Frac / LOT (ppg EMW)", "number"),
            Field("temp_f", "Temp (°F)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el programa de casing
    GridConfig(
        key="casing-program", title="Casing Program", table_name="ops_plan_casing",
        model_name="PlanCasing", add_label="+ Add String",
        intro="Planned casing scheme — the string sizes and setting depths the well design calls for.",
        fields=[
            Field("string", "String", "select", ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("od_in", "OD (in)", "number"),
            Field("weight_ppf", "Weight (ppf)", "number"),
            Field("grade", "Grade"),
            Field("connection", "Connection"),
            Field("setting_md", "Setting MD (ft)", "number"),
            Field("setting_tvd", "Setting TVD (ft)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el programa de hoyo y broca
    GridConfig(
        key="hole-program", title="Hole & Bit Program", table_name="ops_plan_hole",
        model_name="PlanHoleSection", add_label="+ Add Section", compute_kind="length",
        intro="Planned hole sections and the bit type for each. Length is computed from Top/Bottom MD.",
        fields=[
            Field("section", "Section", "select", ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("hole_size_in", "Hole size (in)", "number"),
            Field("bit_type", "Bit type", span=2),
            Field("top_md", "Top MD (ft)", "number"),
            Field("bottom_md", "Bottom MD (ft)", "number"),
            Field("length_ft", "Length (ft)", "number", form=False),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el programa de lodo
    GridConfig(
        key="mud-program", title="Mud Program", table_name="ops_plan_mud",
        model_name="PlanMud", add_label="+ Add Interval",
        intro="Planned drilling-fluid program by hole interval.",
        fields=[
            Field("section", "Section", "select", ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("mud_type", "Mud type", span=2),
            Field("top_md", "From MD (ft)", "number"),
            Field("bottom_md", "To MD (ft)", "number"),
            Field("weight_min", "Min weight (ppg)", "number"),
            Field("weight_max", "Max weight (ppg)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el programa de cementación
    GridConfig(
        key="cement-program", title="Cement Program", table_name="ops_plan_cement",
        model_name="PlanCement", add_label="+ Add Cement Stage",
        intro="Planned cementing program per casing string.",
        fields=[
            Field("string", "String", "select", ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("slurry_type", "Slurry", span=2),
            Field("density_ppg", "Density (ppg)", "number"),
            Field("volume_bbl", "Volume (bbl)", "number"),
            Field("top_md", "Top MD (ft)", "number"),
            Field("bottom_md", "Bottom MD (ft)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el plan direccional
    GridConfig(
        key="directional-plan", title="Directional Plan", table_name="ops_plan_directional",
        model_name="PlanDirectional", add_label="+ Add Point", recompute_kind="survey",
        intro="Planned well trajectory. Enter MD / Inclination / Azimuth — TVD, N/S, E/W and DLS are computed (minimum-curvature).",
        fields=[
            Field("md", "MD (ft)", "number"),
            Field("inclination", "Inc (°)", "number"),
            Field("azimuth", "Azi (°)", "number"),
            Field("tvd", "TVD (ft)", "number", form=False),
            Field("ns", "N/S (ft)", "number", form=False),
            Field("ew", "E/W (ft)", "number", form=False),
            Field("dls", "DLS (°/100ft)", "number", form=False),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos el plan tiempo-profundidad
    GridConfig(
        key="time-depth", title="Time–Depth Plan", table_name="ops_plan_time_depth",
        model_name="PlanTimeDepth", add_label="+ Add Day",
        intro="Planned days-vs-depth curve (the AFE / drilling-progress curve operations are measured against).",
        fields=[
            Field("day", "Day", "int"),
            Field("planned_md", "Planned MD (ft)", "number"),
            Field("phase", "Phase", span=2),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la estimación de costos del AFE
    GridConfig(
        key="cost-estimate", title="AFE Cost Estimate", table_name="ops_plan_costs",
        model_name="PlanCostItem", add_label="+ Add Cost Line", compute_kind="amount",
        intro="Detailed AFE estimate. Amount is computed from Qty × Unit Cost; the total feeds the plan budget.",
        fields=[
            Field("category", "Category", "select",
                  ("Rig", "Tangibles", "Services", "Fluids", "Bits", "Cementing", "Casing", "Logging", "Logistics", "Contingency", "Other")),
            Field("description", "Description", table=True, span=2),
            Field("qty", "Qty", "number"),
            Field("unit_cost", "Unit cost", "number"),
            Field("amount", "Amount", "number", form=False),
        ],
    ),
    # Definimos el registro de riesgos y peligros
    GridConfig(
        key="risks", title="Risks & Hazards", table_name="ops_plan_risks",
        model_name="PlanRisk", add_label="+ Add Risk",
        intro="Drilling hazard register — anticipated risks and their planned mitigations.",
        fields=[
            Field("category", "Category", "select",
                  ("Lost Circulation", "Wellbore Instability", "Overpressure", "H2S", "Stuck Pipe",
                   "Kick / Well Control", "Shallow Gas", "Equipment", "Logistics", "HSE", "Other")),
            Field("description", "Hazard", "textarea", table=True, span=3),
            Field("severity", "Severity", "select", ("Low", "Medium", "High")),
            Field("likelihood", "Likelihood", "select", ("Low", "Medium", "High")),
            Field("mitigation", "Mitigation", "textarea", table=False, span=3),
        ],
    ),
]


# Construimos dinámicamente la clase de modelo SQLAlchemy correspondiente a un GridConfig de programa
def _build_plan_model(cfg: GridConfig) -> type:
    # Armamos los atributos base de la tabla: nombre, docstring, FK al evento y orden
    attrs = {
        "__tablename__": cfg.table_name,
        "__doc__": f"Well-plan program rows for '{cfg.title}'. See app/ops/models/planning_capture.py.",
        "event_id": Column(UUID(as_uuid=True), ForeignKey("ops_events.id"), nullable=False, index=True),
        "sort_order": Column(Integer, nullable=False, default=0),
    }
    # Recorremos los campos de la config y traducimos cada uno a su Column de SQLAlchemy
    for f in cfg.fields:
        attrs[f.name] = _column_for(f)
    # Creamos la clase de modelo dinámicamente con type(), heredando de OpsBase y AuditMixin
    return type(cfg.model_name, (OpsBase, AuditMixin), attrs)


# Indexamos cada config de programa por su key para poder resolverla en las rutas
PLAN_CONFIG_BY_KEY: dict[str, GridConfig] = {}
# Recorremos todas las configs de programa para construir su modelo y su relación
for _cfg in PLAN_CONFIGS:
    # Construimos y guardamos el modelo SQLAlchemy generado para esta config
    _cfg.model = _build_plan_model(_cfg)
    # Registramos la config en el diccionario indexado por key
    PLAN_CONFIG_BY_KEY[_cfg.key] = _cfg
    # Agregamos dinámicamente la relación del programa sobre el modelo Event
    setattr(Event, f"plan_{_cfg.key.replace('-', '_')}_rows",
            relationship(_cfg.model, cascade="all, delete-orphan"))


# Buscamos la config de un programa por su key
def get_plan_config(key: str):
    # Devolvemos la config si existe, o None si no
    return PLAN_CONFIG_BY_KEY.get(key)
