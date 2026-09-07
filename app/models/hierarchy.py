# Importamos los tipos de columna que usamos en las tablas de la jerarquía
from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String
# Importamos UUID de Postgres para tipar los ids
from sqlalchemy.dialects.postgresql import UUID
# Importamos relationship para declarar las relaciones entre niveles de la jerarquía
from sqlalchemy.orm import relationship
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin

# Definimos el modelo de empresa, el nivel más alto de la jerarquía
class Company(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "companies"

    # Guardamos el nombre de la empresa
    name = Column(String(200), nullable=False)

    # Relacionamos la empresa con sus proyectos (se borran en cascada)
    projects = relationship("Project", back_populates="company", cascade="all, delete-orphan")

# Definimos el modelo de proyecto, colgado de una empresa
class Project(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "projects"

    # Guardamos a qué empresa pertenece el proyecto
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Guardamos el nombre del proyecto
    name = Column(String(200), nullable=False)

    # Relacionamos el proyecto con su empresa
    company = relationship("Company", back_populates="projects")

    # Relacionamos el proyecto con sus sitios (se borran en cascada)
    sites = relationship("Site", back_populates="project", cascade="all, delete-orphan")

# Definimos el modelo de sitio, colgado de un proyecto
class Site(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "sites"

    # Guardamos a qué proyecto pertenece el sitio
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)

    # Guardamos el nombre del sitio
    name = Column(String(200), nullable=False)

    # Guardamos la ubicación del sitio
    location = Column(String(300), nullable=True)

    # Relacionamos el sitio con su proyecto
    project = relationship("Project", back_populates="sites")

    # Relacionamos el sitio con sus pozos (se borran en cascada)
    wells = relationship("Well", back_populates="site", cascade="all, delete-orphan")

# Definimos el modelo de pozo operacional/de planeación
class Well(OpsBase, AuditMixin):
    """Operational/planning well — distinct from app.models.legacy.Well, which
    represents a well that already has time-series log data imported. A
    single physical well may have both; legacy_well_id is an optional bridge
    for cross-linking into the visualization side, not a shared identity."""

    # Nombramos la tabla
    __tablename__ = "wells"

    # Guardamos a qué sitio pertenece el pozo
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False, index=True)

    # Guardamos el enlace opcional hacia el pozo legacy (datos de sensores ya importados)
    legacy_well_id = Column(Integer, ForeignKey("sensor_wells.id"), nullable=True)

    # Guardamos el nombre legal del pozo
    legal_well_name = Column(String(200), nullable=False)

    # Guardamos el nombre común del pozo
    common_well_name = Column(String(200), nullable=True)

    # Guardamos el identificador único de pozo (UWI)
    uwi = Column(String(100), nullable=True, index=True)

    # Guardamos el operador del pozo
    operator = Column(String(200), nullable=True)

    # Guardamos el número API del pozo
    api_no = Column(String(100), nullable=True)

    # Guardamos una descripción del pozo
    description = Column(String(200), nullable=True)

    # Guardamos la formación objetivo del pozo
    target_formation = Column(String(200), nullable=True)

    # Guardamos el propósito del pozo
    purpose = Column(String(200), nullable=True)

    # Guardamos la razón de perforación del pozo
    reason = Column(String(200), nullable=True)

    # Guardamos la fecha de spud del pozo
    spud_date = Column(Date, nullable=True)

    # Guardamos el país del pozo
    country = Column(String(100), nullable=True)

    # Guardamos la clasificación del pozo
    well_classification = Column(String(100), nullable=True)

    # Guardamos la referencia de profundidad (OpenWells: pestaña "Depth Reference") — Air Gap = datum_elevation - ground_elevation.
    # La matemática de profundidad de Hole Sections/NPT aguas abajo se referencia a esto, así que lo capturamos a nivel de pozo.
    # Guardamos el nombre del datum
    datum_name = Column(String(50), nullable=True, default="ORIGINAL KB")
    
    # Guardamos la elevación del datum
    datum_elevation = Column(Numeric(10, 2), nullable=True)
    
    # Guardamos la elevación del terreno
    ground_elevation = Column(Numeric(10, 2), nullable=True)

    # Relacionamos el pozo con su sitio
    site = relationship("Site", back_populates="wells")
    
    # Relacionamos el pozo con sus wellbores (se borran en cascada)
    wellbores = relationship("Wellbore", back_populates="well", cascade="all, delete-orphan")

# Definimos el modelo de wellbore (trayectoria/rama del pozo)
class Wellbore(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "wellbores"

    # Guardamos a qué pozo pertenece el wellbore
    well_id = Column(UUID(as_uuid=True), ForeignKey("wells.id"), nullable=False, index=True)

    # Guardamos el wellbore padre cuando este es un sidetrack
    parent_wellbore_id = Column(UUID(as_uuid=True), ForeignKey("wellbores.id"), nullable=True)

    # Guardamos el nombre del wellbore
    name = Column(String(100), nullable=False)

    # Guardamos el número de sidetrack
    sidetrack_no = Column(String(20), nullable=True)

    # Guardamos el tipo de trayectoria
    trajectory_type = Column(String(50), nullable=True)

    # Guardamos el API de 12 dígitos
    api12 = Column(String(20), nullable=True)

    # Guardamos el número de archivo
    arch_no = Column(String(50), nullable=True)

    # Guardamos la fecha de inicio
    start_date = Column(Date, nullable=True)

    # Guardamos la fecha de fin de perforación
    drilling_end_date = Column(Date, nullable=True)

    # Guardamos la fecha de fin de completación
    completion_end_date = Column(Date, nullable=True)

    # Guardamos el azimut de la sección vertical
    vs_azimuth = Column(Numeric(6, 2), nullable=True)

    # Guardamos el ángulo máximo estimado
    max_angle_est = Column(Numeric(6, 2), nullable=True)

    # Guardamos la profundidad medida del punto de desviación
    kick_off_top_md = Column(Numeric(10, 2), nullable=True)

    # Guardamos la profundidad vertical verdadera del punto de desviación
    kick_off_top_tvd = Column(Numeric(10, 2), nullable=True)

    # Relacionamos el wellbore con su pozo
    well = relationship("Well", back_populates="wellbores")

    # Relacionamos el wellbore con su wellbore padre (auto-referencia)
    parent_wellbore = relationship("Wellbore", remote_side="Wellbore.id")

    # Relacionamos el wellbore con sus eventos (se borran en cascada)
    events = relationship("Event", back_populates="wellbore", cascade="all, delete-orphan")

# Definimos el modelo de evento (una campaña de perforación/workover sobre un wellbore)
class Event(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "events"

    # Guardamos a qué wellbore pertenece el evento
    wellbore_id = Column(UUID(as_uuid=True), ForeignKey("wellbores.id"), nullable=False, index=True)

    # Guardamos el código del evento
    event_code = Column(String(50), nullable=True)

    # Guardamos el tipo de evento
    event_type = Column(String(50), nullable=True)

    # Guardamos el objetivo del evento
    objective = Column(String(200), nullable=True)

    # Guardamos el contratista del evento
    contractor = Column(String(200), nullable=True)

    # Guardamos el nombre del taladro
    rig_name = Column(String(200), nullable=True)

    # Guardamos la fecha de inicio del evento
    start_date = Column(Date, nullable=True)

    # Guardamos la fecha de fin del evento
    end_date = Column(Date, nullable=True)

    # Guardamos el costo autorizado del evento
    authorized_cost = Column(Integer, nullable=True)

    # Relacionamos el evento con su wellbore
    wellbore = relationship("Wellbore", back_populates="events")

    # Relacionamos el evento con su plan de pozo (uno a uno)
    well_plan = relationship("WellPlan", uselist=False, cascade="all, delete-orphan", passive_deletes=False)

    # Relacionamos el evento con sus reportes diarios (se borran en cascada)
    daily_reports = relationship("DailyReport", cascade="all, delete-orphan", passive_deletes=False)
