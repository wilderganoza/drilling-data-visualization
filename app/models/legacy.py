# Importamos los tipos de columna que usamos en las tablas legacy
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
# Importamos declarative_base para crear la Base legacy y relationship para las relaciones entre tablas
from sqlalchemy.orm import declarative_base, relationship
# Importamos JSONB para guardar configuraciones y métricas como JSON
from sqlalchemy.dialects.postgresql import JSONB
# Importamos datetime y timezone para sellar fechas en UTC
from datetime import datetime, timezone

# Creamos la Base declarativa legacy, de la que heredan todos los modelos originales de la app
Base = declarative_base()


# Definimos la función que nos da la fecha/hora actual en UTC, sin zona horaria
def utcnow() -> datetime:
    """UTC naive, para columnas DateTime sin zona horaria (reemplaza el deprecado datetime.utcnow)."""
    # Devolvemos la hora actual en UTC quitando la información de zona horaria
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Definimos el modelo de usuario de la aplicación
class User(Base):
    # Nombramos la tabla
    __tablename__ = "users"

    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos el username, único para cada usuario
    username = Column(String(100), unique=True, nullable=False, index=True)
    # Guardamos el nombre completo del usuario
    full_name = Column(String(200), nullable=True)
    # Guardamos el correo del usuario
    email = Column(String(200), nullable=True)
    # Guardamos el hash de la contraseña, nunca la contraseña en texto plano
    hashed_password = Column(String(255), nullable=False)
    # Guardamos si el usuario está activo
    is_active = Column(Boolean, default=True)
    # Guardamos si el usuario es administrador
    is_admin = Column(Boolean, default=False)
    # Guardamos cuándo se creó el usuario
    created_at = Column(DateTime, default=utcnow)
    # Guardamos cuándo se actualizó el usuario por última vez
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Definimos cómo se representa el usuario al imprimirlo (útil para debug)
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


# Definimos el modelo de pozo legacy (con datos de sensores ya importados)
class Well(Base):
    # Nombramos la tabla
    __tablename__ = "wells"

    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos el nombre del pozo
    well_name = Column(String, nullable=False, index=True)
    # Guardamos el nombre del archivo original importado
    filename = Column(String, nullable=True)
    # Guardamos el total de filas importadas
    total_rows = Column(Integer, nullable=True)
    # Guardamos el total de columnas importadas
    total_columns = Column(Integer, nullable=True)
    # Guardamos cuándo se importó el pozo
    date_imported = Column(DateTime, default=utcnow)
    # Guardamos el nombre del campo/yacimiento
    field_name = Column(String(100), nullable=True, index=True)

    # Definimos cómo se representa el pozo al imprimirlo
    def __repr__(self):
        return f"<Well(id={self.id}, well_name='{self.well_name}')>"


# Definimos la clase base con los campos comunes de las tablas de datos de sensores (well_data / well_data_time)
class WellDataBase:
    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos a qué pozo pertenece cada fila de datos
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)


# Definimos el modelo de un dataset procesado (resultado de un pipeline de limpieza de outliers)
class ProcessedDataset(Base):
    # Nombramos la tabla
    __tablename__ = "processed_datasets"

    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos a qué pozo pertenece el dataset
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    # Guardamos el dominio del dataset (profundidad o tiempo)
    domain = Column(String(20), nullable=False, default="depth", server_default="depth")  # depth | time
    # Guardamos el nombre del dataset
    name = Column(String(128), nullable=False)
    # Guardamos una descripción del dataset
    description = Column(String(500), nullable=True)
    # Guardamos la configuración del pipeline que generó el dataset
    pipeline_config = Column(JSONB, nullable=False)
    # Guardamos las métricas resultantes del pipeline
    metrics = Column(JSONB, nullable=True)
    # Guardamos el estado del dataset
    status = Column(String(50), default="completed")
    # Guardamos el número de registros del dataset
    record_count = Column(Integer, nullable=True)
    # Guardamos quién creó el dataset
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Guardamos cuándo se creó el dataset
    created_at = Column(DateTime, default=utcnow)
    # Guardamos cuándo se actualizó el dataset por última vez
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relacionamos el dataset con su pozo
    well = relationship("Well", backref="processed_datasets")
    # Relacionamos el dataset con el usuario que lo creó
    creator = relationship("User", backref="processed_datasets", foreign_keys=[created_by])
    # Relacionamos el dataset con sus registros procesados (se borran en cascada)
    records = relationship("ProcessedRecord", back_populates="dataset", cascade="all, delete-orphan")

    # Definimos cómo se representa el dataset al imprimirlo
    def __repr__(self):
        return f"<ProcessedDataset(id={self.id}, well_id={self.well_id}, name='{self.name}')>"


# Definimos el modelo de un registro individual dentro de un dataset procesado
class ProcessedRecord(Base):
    # Nombramos la tabla
    __tablename__ = "processed_records"

    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos a qué dataset pertenece el registro
    dataset_id = Column(Integer, ForeignKey("processed_datasets.id"), nullable=False, index=True)
    # Guardamos el id del registro original en la fuente de datos
    source_record_id = Column(Integer, nullable=True)
    # Guardamos los datos originales del registro
    data = Column(JSONB, nullable=False)
    # Guardamos los datos escalados del registro
    scaled_data = Column(JSONB, nullable=True)
    # Guardamos los puntajes de componentes (ej. PCA) del registro
    component_scores = Column(JSONB, nullable=True)
    # Guardamos si el registro fue marcado como outlier
    is_outlier = Column(Boolean, default=False)
    # Guardamos cuándo se creó el registro
    created_at = Column(DateTime, default=utcnow)

    # Relacionamos el registro con su dataset
    dataset = relationship("ProcessedDataset", back_populates="records")

    # Definimos cómo se representa el registro al imprimirlo
    def __repr__(self):
        return f"<ProcessedRecord(id={self.id}, dataset_id={self.dataset_id})>"


# Definimos el modelo de un experimento guardado de predicción de ROP
class RopExperiment(Base):
    """A saved ROP-Prediction experiment: its full wizard config, the validation
    metrics, and a joblib artifact holding the fitted pipeline (scaler + PCA + model
    + conformal interval) for later inference / what-if scoring."""

    # Nombramos la tabla
    __tablename__ = "rop_experiments"

    # Usamos un entero autoincremental como llave primaria
    id = Column(Integer, primary_key=True, index=True)
    # Guardamos el nombre del experimento
    name = Column(String(160), nullable=False)
    # Guardamos una descripción del experimento
    description = Column(String(500), nullable=True)
    # Guardamos la clave del modelo usado (XGBoost, LightGBM, etc.)
    model_key = Column(String(50), nullable=False)
    # Guardamos el estado del experimento
    status = Column(String(30), default="completed")
    # Guardamos la configuración completa del wizard (pozos, features, split, procesamiento, params)
    config = Column(JSONB, nullable=False)          # wells, features, split, processing, params
    # Guardamos las métricas de entrenamiento/prueba/blind + intervalo de predicción + drift
    metrics = Column(JSONB, nullable=True)          # train/test/blind metrics + PI + drift
    # Guardamos el detalle de preselección/HPO (comparación de modelos, historial de trials, tuned-vs-default)
    # cuando esté disponible — None por clave si ese job se saltó o ya se evictó del store en memoria al guardar.
    # Esto permite que un experimento cargado muestre más que solo las métricas finales de Validación cuando aplica.
    training_detail = Column(JSONB, nullable=True)
    # Guardamos la ruta del artefacto joblib con el pipeline entrenado
    artifact_path = Column(String(300), nullable=True)
    # Guardamos quién creó el experimento
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Guardamos cuándo se creó el experimento
    created_at = Column(DateTime, default=utcnow)
    # Guardamos cuándo se actualizó el experimento por última vez
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Definimos cómo se representa el experimento al imprimirlo
    def __repr__(self):
        return f"<RopExperiment(id={self.id}, name='{self.name}', model='{self.model_key}')>"


# Definimos el modelo de un job terminado del wizard de predicción de ROP
class RopWizardJob(Base):
    """A finished ROP-Prediction wizard job (pre-selection / HPO / validation),
    persisted as soon as it completes — not just when the user later clicks
    "Save". The in-process job store (app/ops/services/rop_jobs.py) is wiped on
    every server restart; this table is what lets a revisited step redisplay
    real results instead of "not run yet" after a restart, without re-running
    potentially minutes of Optuna trials."""

    # Nombramos la tabla
    __tablename__ = "rop_wizard_jobs"

    # Usamos el mismo id del job en memoria como llave primaria (basado en UUID, sobrevive a reinicios)
    job_id = Column(String(64), primary_key=True)   # matches rop_jobs' in-process id (UUID-based, restart-safe)
    # Guardamos el tipo de job
    kind = Column(String(20), nullable=False)        # "preselect" | "hpo" | "validation"
    # Guardamos el estado del wizard al momento de enviar el job, para comparar si quedó desactualizado
    state = Column(JSONB, nullable=False)             # wizard state at submission time, for staleness comparison
    # Guardamos el resultado en formato JSON (el pipeline entrenado de validación se excluye, ver pipeline_path)
    result = Column(JSONB, nullable=False)            # JSON-safe result (validation's fitted pipeline excluded — see pipeline_path)
    # Guardamos la ruta del artefacto joblib, solo para jobs de validación
    pipeline_path = Column(String(300), nullable=True)  # joblib artifact, validation jobs only
    # Guardamos cuándo se creó el job
    created_at = Column(DateTime, default=utcnow)

    # Definimos cómo se representa el job al imprimirlo
    def __repr__(self):
        return f"<RopWizardJob(job_id='{self.job_id}', kind='{self.kind}')>"
