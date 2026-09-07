"""Spec-driven capture subsections of the Daily Operations Report.

Every remaining subsection (Casing, Cementing, Surveys, Drillstring/BHA,
Daily Cost, Pipe Tally, Fluids, Personnel, Safety, Remarks) is the same
shape: an ordered list of rows attached to one daily report. Rather than
hand-write 10 near-identical models + routers + templates, each is declared
once as a `GridConfig` of `Field`s here; the SQLAlchemy model class, the
capture routes (app/web/capture.py) and the grid template all read from
that single declaration, so a column is added or renamed in exactly one place.

This is the "design the editable grid once, reuse everywhere" leverage point
from the build plan, generalized past Time Summary/NPT to every row-based
subsection that was left as a disabled tab."""
# Importamos math para calcular la energía específica mecánica (MSE)
import math
# Importamos dataclass y field para declarar Field/GridConfig como dataclasses
from dataclasses import dataclass, field
# Importamos Optional para tipar el retorno de get_config
from typing import Optional
# Importamos los tipos de columna que traduce _column_for
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String, Text
# Importamos UUID de Postgres para tipar el id del reporte diario
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para colgar cada subsección del DailyReport
from sqlalchemy.orm import relationship
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos DailyReport para colgarle la relación de cada subsección
from app.models.daily_report import DailyReport
# Importamos AuditMixin para heredar los campos de auditoría en cada modelo generado
from app.models.mixins import AuditMixin


# Definimos la dataclass que describe una columna de una subsección de captura
@dataclass
class Field:
    """One column of a capture subsection. `kind` drives the DB column type,
    the form widget and the value coercion all at once. `form=False` marks a
    server-computed column (shown in the table, never entered by hand)."""
    # Guardamos el nombre técnico del campo (nombre de columna)
    name: str

    # Guardamos la etiqueta visible del campo
    label: str

    # Guardamos el tipo de campo, que determina el widget y el tipo de columna
    kind: str = "text"  # text | textarea | number | int | select | time

    # Guardamos las opciones válidas cuando kind es "select"
    options: tuple = ()

    # Guardamos si el campo aparece como columna en la tabla
    table: bool = True   # appears as a table column

    # Guardamos si el campo aparece como input en el formulario
    form: bool = True    # appears as a form input

    # Guardamos cuántas columnas ocupa el campo en la grilla del formulario
    span: int = 1        # md:col-span-N in the form grid


# Definimos la dataclass que describe una subsección completa (una grilla)
@dataclass
class GridConfig:
    # Guardamos la clave de la subsección (segmento de URL + id de template)
    key: str             # URL segment + template id (e.g. "casing")

    # Guardamos el título visible de la subsección
    title: str

    # Guardamos el nombre de la tabla en la base de datos
    table_name: str

    # Guardamos el nombre de la clase de modelo generada
    model_name: str

    # Guardamos la lista de campos de la subsección
    fields: list

    # Guardamos la etiqueta del botón para agregar una fila
    add_label: str = "+ Add Row"

    # Guardamos el texto introductorio de la subsección
    intro: str = ""

    # Guardamos qué columnas derivadas se calculan por fila
    compute_kind: str = ""       # per-row derived cols: "" | "length" | "amount"

    # Guardamos si hay que recalcular toda la lista tras cualquier cambio
    recompute_kind: str = ""     # whole-list recompute after any change: "" | "survey"

    # Guardamos la clase de modelo generada, una vez construida
    model: type = field(default=None)


# Traducimos un Field a la Column de SQLAlchemy correspondiente según su kind
def _column_for(f: Field):
    # Usamos Numeric para campos numéricos
    if f.kind == "number":
        return Column(Numeric(16, 3), nullable=True)
    # Usamos Integer para campos enteros
    if f.kind == "int":
        return Column(Integer, nullable=True)
    # Usamos Text para campos de texto largo
    if f.kind == "textarea":
        return Column(Text, nullable=True)
    # Usamos String corto para campos de hora ("HH:MM")
    if f.kind == "time":
        return Column(String(5), nullable=True)
    # Usamos String corto para campos de selección
    if f.kind == "select":
        return Column(String(60), nullable=True)
    # Usamos String largo como tipo por defecto para el resto de los campos de texto
    return Column(String(300), nullable=True)


# Calculamos las columnas derivadas (form=False) a partir de los valores ingresados
def compute_values(cfg: GridConfig, values: dict) -> dict:
    """Fill server-computed columns (form=False fields) from entered values."""
    # Calculamos la longitud como bottom_md menos top_md
    if cfg.compute_kind == "length":
        top, bottom = values.get("top_md"), values.get("bottom_md")
        values["length_ft"] = round(bottom - top, 3) if top is not None and bottom is not None else None
    # Calculamos el monto como cantidad por costo unitario
    elif cfg.compute_kind == "amount":
        qty, unit = values.get("qty"), values.get("unit_cost")
        values["amount"] = round(qty * unit, 2) if qty is not None and unit is not None else None
    # Calculamos el stock disponible como recibido menos consumido
    elif cfg.compute_kind == "stock":
        recv, cons = values.get("received_qty"), values.get("consumed_qty")
        if recv is not None or cons is not None:
            values["on_hand"] = round((recv or 0) - (cons or 0), 3)
    # Calculamos la energía específica mecánica (MSE) con la fórmula de Teale
    elif cfg.compute_kind == "mse":
        # Teale mechanical specific energy (ksi): MSE = 4·WOB/(π·D²) + 480·RPM·T/(D²·ROP)
        d, rop = values.get("bit_size"), values.get("rop")
        wob, rpm, tq = values.get("wob"), values.get("rpm"), values.get("torque_ftlb")
        if d and d > 0 and rop and rop > 0:
            mse = (4.0 * (wob or 0) * 1000.0) / (math.pi * d * d) + (480.0 * (rpm or 0) * (tq or 0)) / (d * d * rop)
            values["mse_ksi"] = round(mse / 1000.0, 1)
    # Devolvemos los valores ya completados con las columnas calculadas
    return values

# Declaramos el catálogo de subsecciones de captura, una por GridConfig
CONFIGS: list[GridConfig] = [
    # Definimos la subsección de hoyo/casing
    GridConfig(
        key="casing", title="Hole / Casing", table_name="casing_components",
        model_name="CasingComponent", add_label="+ Add Section", compute_kind="length",
        intro="Hole sections and the casing/liner/tubing run in them. Length is computed from Top/Bottom MD.",
        fields=[
            Field("section_type", "Type", "select", ("Hole", "Casing", "Liner", "Tubing", "Conductor")),
            Field("od_in", "OD (in)", "number"),
            Field("id_in", "ID (in)", "number"),
            Field("weight_ppf", "Weight (ppf)", "number"),
            Field("grade", "Grade"),
            Field("connection", "Connection"),
            Field("top_md", "Top MD (ft)", "number"),
            Field("bottom_md", "Bottom MD (ft)", "number"),
            Field("length_ft", "Length (ft)", "number", table=True, form=False),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de corrida de casing
    GridConfig(
        key="casing-running", title="Casing Running", table_name="casing_running",
        model_name="CasingRunning", add_label="+ Add String",
        intro="Casing/liner running record for the day — planned vs actual shoe, joints run, "
              "float fill and cement returns. Checked against the planned Casing Program.",
        fields=[
            Field("string", "String", "select", ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("od_in", "OD (in)", "number"),
            Field("planned_shoe_md", "Planned shoe MD (ft)", "number"),
            Field("actual_shoe_md", "Actual shoe MD (ft)", "number"),
            Field("joints_run", "Joints run", "int"),
            Field("running_hours", "Running (hr)", "number"),
            Field("mud_displaced_bbl", "Mud displaced (bbl)", "number"),
            Field("returns_pct", "Cement returns (%)", "number"),
            Field("landed", "Landed / hung", "select", ("Yes", "No", "Partial")),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de cementación
    GridConfig(
        key="cementing", title="Cementing", table_name="cement_jobs",
        model_name="CementJob", add_label="+ Add Cement Job",
        intro="Cement jobs pumped this day, referenced against the casing/liner run in Hole / Casing.",
        fields=[
            Field("stage", "Stage", "select", ("Primary", "Secondary", "Squeeze", "Plug", "Top-up")),
            Field("casing_size", "Casing size"),
            Field("slurry_type", "Slurry"),
            Field("cement_class", "Class", "select", ("A", "C", "G", "H", "Other")),
            Field("density_ppg", "Density (ppg)", "number"),
            Field("volume_bbl", "Volume (bbl)", "number"),
            Field("top_md", "Top MD (ft)", "number"),
            Field("bottom_md", "Bottom MD (ft)", "number"),
            Field("returns_pct", "Returns (%)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de cabezal de pozo
    GridConfig(
        key="wellhead", title="Wellhead", table_name="wellhead_components",
        model_name="WellheadComponent", add_label="+ Add Component",
        intro="Wellhead equipment installed as each casing string is run (casing heads, spools, hangers, valves) and its pressure test.",
        fields=[
            Field("component", "Component", "select",
                  ("Conductor Housing", "Casing Head", "Casing Spool", "Tubing Head", "Adapter Flange",
                   "Casing Hanger", "Gate Valve", "Cross / Tee", "Companion Flange", "BOP Adapter")),
            Field("size", "Size"),
            Field("pressure_rating", "Rating"),
            Field("manufacturer", "Manufacturer"),
            Field("serial_no", "Serial No."),
            Field("associated_string", "Casing string", "select",
                  ("Conductor", "Surface", "Intermediate", "Production", "Liner")),
            Field("test_pressure_psi", "Test press. (psi)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de surveys direccionales
    GridConfig(
        key="surveys", title="Surveys", table_name="survey_stations",
        model_name="SurveyStation", add_label="+ Add Station", recompute_kind="survey",
        intro="Directional survey stations. Enter MD / Inclination / Azimuth — TVD, N/S, E/W and DLS are computed automatically (minimum-curvature) and stay continuous with earlier reports.",
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
    # Definimos la subsección de sarta de perforación / BHA
    GridConfig(
        key="drillstring", title="Drillstring / BHA", table_name="bha_components",
        model_name="BhaComponent", add_label="+ Add Component",
        intro="Bottom-hole assembly, listed top-down from the drill pipe to the bit.",
        fields=[
            Field("component", "Component", "select",
                  ("Bit", "Motor", "RSS", "MWD", "LWD", "Stabilizer", "Drill Collar",
                   "HWDP", "Drill Pipe", "Jar", "Crossover", "Reamer", "Float Sub", "Other")),
            Field("od_in", "OD (in)", "number"),
            Field("id_in", "ID (in)", "number"),
            Field("length_ft", "Length (ft)", "number"),
            Field("serial_no", "Serial No."),
            Field("description", "Description", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de costo diario
    GridConfig(
        key="cost", title="Daily Cost", table_name="cost_items",
        model_name="CostItem", add_label="+ Add Cost Line", compute_kind="amount",
        intro="Daily cost lines charged against the AFE. Amount is computed from Qty × Unit Cost.",
        fields=[
            Field("category", "Category", "select",
                  ("Rig", "Tangibles", "Services", "Fluids", "Bits", "Cementing", "Logistics", "Other")),
            Field("description", "Description", table=True, span=2),
            Field("vendor", "Vendor"),
            Field("afe_code", "AFE code"),
            Field("qty", "Qty", "number"),
            Field("unit_cost", "Unit cost", "number"),
            Field("amount", "Amount", "number", table=True, form=False),
        ],
    ),
    # Definimos la subsección de tally de tubulares
    GridConfig(
        key="pipe-tally", title="Pipe Tally", table_name="pipe_tally_joints",
        model_name="PipeTallyJoint", add_label="+ Add Joint",
        intro="Measured tally of tubulars run in the hole, joint by joint.",
        fields=[
            Field("joint_no", "Joint No.", "int"),
            Field("length_ft", "Length (ft)", "number"),
            Field("cumulative_ft", "Cumulative (ft)", "number"),
            Field("od_in", "OD (in)", "number"),
            Field("serial_no", "Serial No."),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de parámetros de perforación
    GridConfig(
        key="drill-params", title="Drilling Parameters", table_name="drill_params",
        model_name="DrillParam", add_label="+ Add Reading", compute_kind="mse",
        intro="Drilling-parameter readings by depth — WOB, RPM, flow, torque, SPP and ROP. "
              "Mechanical Specific Energy (MSE) is computed. Feeds ROP optimisation and dysfunction detection.",
        fields=[
            Field("depth_md", "Depth MD (ft)", "number"),
            Field("formation", "Formation", span=2),
            Field("bit_size", "Bit size (in)", "number"),
            Field("wob", "WOB (klbf)", "number"),
            Field("rpm", "RPM", "number"),
            Field("flow_gpm", "Flow (gpm)", "number"),
            Field("torque_ftlb", "Torque (ft-lbf)", "number"),
            Field("spp_psi", "SPP (psi)", "number"),
            Field("rop", "ROP (ft/hr)", "number"),
            Field("mse_ksi", "MSE (ksi)", "number", form=False),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de fluidos (lodo)
    GridConfig(
        key="fluids", title="Fluids (Mud)", table_name="fluid_readings",
        model_name="FluidReading", add_label="+ Add Reading",
        intro="Drilling-fluid property checks taken during the day.",
        fields=[
            Field("time", "Time", "time"),
            Field("mud_type", "Mud type"),
            Field("weight_ppg", "Weight (ppg)", "number"),
            Field("funnel_vis", "Funnel vis (s)", "number"),
            Field("pv", "PV", "number"),
            Field("yp", "YP", "number"),
            Field("ph", "pH", "number"),
            Field("chlorides", "Chlorides (mg/L)", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de bombas y control de sólidos
    GridConfig(
        key="pumps", title="Pumps & Solids Control", table_name="pump_operations",
        model_name="PumpOperation", add_label="+ Add Equipment",
        intro="Mud-pump and solids-control equipment operation — rig pumps (liner/SPM/pressure/flow) and shakers, desanders, desilters, centrifuges.",
        fields=[
            Field("equipment", "Equipment", "select",
                  ("Mud Pump #1", "Mud Pump #2", "Mud Pump #3", "Shale Shaker", "Desander",
                   "Desilter", "Mud Cleaner", "Centrifuge", "Hydrocyclone", "Agitator")),
            Field("model", "Model / Type"),
            Field("liner_size_in", "Liner (in)", "number"),
            Field("spm", "SPM / RPM", "number"),
            Field("pressure_psi", "Pressure (psi)", "number"),
            Field("flow_rate_gpm", "Flow (gpm)", "number"),
            Field("hours_run", "Hours run", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de personal
    GridConfig(
        key="personnel", title="Personnel", table_name="personnel_entries",
        model_name="PersonnelEntry", add_label="+ Add Personnel",
        intro="People on board (POB) by company and position.",
        fields=[
            Field("company", "Company"),
            Field("name", "Name"),
            Field("position", "Position"),
            Field("persons", "Persons", "int"),
            Field("hours", "Hours", "number"),
            Field("comments", "Comments", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de seguridad
    GridConfig(
        key="safety", title="Safety", table_name="safety_events",
        model_name="SafetyEvent", add_label="+ Add Safety Entry",
        intro="Safety meetings, observations, drills and any HSE incidents.",
        fields=[
            Field("time", "Time", "time"),
            Field("event_type", "Type", "select",
                  ("Safety Meeting", "JSA", "Observation", "Drill", "Near Miss", "Incident")),
            Field("severity", "Severity", "select", ("Low", "Medium", "High")),
            Field("description", "Description", "textarea", table=True, span=3),
            Field("action", "Action taken", "textarea", table=False, span=3),
        ],
    ),
    # Definimos la subsección de observaciones libres
    GridConfig(
        key="remarks", title="Remarks", table_name="remarks",
        model_name="Remark", add_label="+ Add Remark",
        intro="Free-form notes not captured elsewhere.",
        fields=[
            Field("time", "Time", "time"),
            Field("category", "Category", "select",
                  ("Operations", "Geology", "HSE", "Logistics", "Equipment", "Other")),
            Field("remark", "Remark", "textarea", table=True, span=3),
        ],
    ),
]

# Construimos un modelo de SQLAlchemy por config, y conectamos una relación con borrado en
# cascada desde DailyReport para que al borrar un reporte (o su Event) se borren también sus
# filas de captura — el mismo contrato de cascada que ya tienen Time Summary / NPT.
def _build_model(cfg: GridConfig) -> type:
    # Armamos los atributos base de la tabla: nombre, docstring, FK al reporte diario y orden
    attrs = {
        "__tablename__": cfg.table_name,
        "__doc__": f"Spec-driven capture rows for the '{cfg.title}' subsection. See app/models/capture.py.",
        "daily_report_id": Column(UUID(as_uuid=True), ForeignKey("daily_reports.id"), nullable=False, index=True),
        "sort_order": Column(Integer, nullable=False, default=0)}

    # Recorremos los campos de la config y traducimos cada uno a su Column de SQLAlchemy
    for f in cfg.fields:
        # Guardamos la columna traducida bajo el nombre del campo
        attrs[f.name] = _column_for(f)

    # Creamos la clase de modelo dinámicamente con type(), heredando de OpsBase y AuditMixin
    return type(cfg.model_name, (OpsBase, AuditMixin), attrs)

# Indexamos cada config de subsección por su key para poder resolverla en las rutas
CONFIG_BY_KEY: dict[str, GridConfig] = {}

# Recorremos todas las configs para construir su modelo y su relación
for _cfg in CONFIGS:
    # Construimos y guardamos el modelo SQLAlchemy generado para esta config
    _cfg.model = _build_model(_cfg)

    # Registramos la config en el diccionario indexado por key
    CONFIG_BY_KEY[_cfg.key] = _cfg

    # Agregamos dinámicamente la relación de la subsección sobre el modelo DailyReport
    setattr(DailyReport, f"{_cfg.key.replace('-', '_')}_rows", relationship(_cfg.model, cascade="all, delete-orphan"))

# Buscamos la config de una subsección por su key
def get_config(key: str) -> Optional[GridConfig]:
    # Devolvemos la config si existe, o None si no
    return CONFIG_BY_KEY.get(key)
