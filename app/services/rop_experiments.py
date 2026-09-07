"""ROP Prediction — experiment persistence (a lightweight model registry).

Each saved experiment stores its wizard config + validation metrics in the
``rop_experiments`` table and its fitted pipeline (scaler + PCA + model + conformal
interval) as a joblib artifact on disk, so it can be reloaded for inference / what-if.
"""
from __future__ import annotations

# Importamos os para verificar/borrar el archivo de artefacto en disco
import os
# Importamos Path para construir la ruta del directorio de artefactos de forma portable
from pathlib import Path
# Importamos List y Optional para tipar los retornos de las funciones públicas
from typing import List, Optional

# Importamos joblib para serializar/deserializar el pipeline entrenado (scaler + PCA + modelo + intervalo conforme)
import joblib
# Importamos text para armar el ALTER TABLE idempotente en ensure_table
from sqlalchemy import text
# Importamos Session para tipar la sesión de base de datos recibida
from sqlalchemy.orm import Session

# Importamos RopExperiment, el modelo ORM que registra cada experimento guardado
from app.models.legacy import RopExperiment
# Importamos db_manager para acceder al engine y crear/alterar la tabla en caliente
from app.db.session import db_manager

# Definimos el directorio donde se guardan los artefactos joblib de cada experimento
ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "model_store" / "rop"

# Guardamos una bandera para no repetir la creación/alteración de la tabla en cada llamada
_TABLE_READY = False


def ensure_table() -> None:
    """Create the rop_experiments table if it doesn't exist (created in-process
    rather than by migration, to stay safe alongside the reflected legacy tables)."""
    global _TABLE_READY
    # Si ya verificamos la tabla en este proceso, no repetimos el trabajo
    if _TABLE_READY:
        return
    # Creamos la tabla si aún no existe (checkfirst evita error si ya está creada)
    RopExperiment.__table__.create(bind=db_manager._engine, checkfirst=True)
    # Same in-process convention as the initial create() above — plain
    # idempotent ALTER for a column added after the table already existed in
    # some deployments.
    with db_manager._engine.begin() as conn:
        # Agregamos la columna training_detail si falta (idempotente, no rompe despliegues antiguos)
        conn.execute(text("ALTER TABLE rop_experiments ADD COLUMN IF NOT EXISTS training_detail JSONB"))
    _TABLE_READY = True


def save(db: Session, *, name: str, description: Optional[str], model_key: str,
         config: dict, metrics: dict, pipeline: dict, training_detail: Optional[dict] = None,
         created_by: Optional[int] = None) -> RopExperiment:
    # Nos aseguramos de que la tabla exista antes de insertar
    ensure_table()
    # Creamos el registro del experimento con su configuración y métricas de validación
    exp = RopExperiment(name=name, description=description, model_key=model_key,
                        config=config, metrics=metrics, training_detail=training_detail,
                        status="completed", created_by=created_by)
    db.add(exp)
    db.flush()  # get id

    # Guardamos el pipeline entrenado como artefacto joblib en disco, nombrado con el id del experimento
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"experiment_{exp.id}.joblib"
    joblib.dump(pipeline, path)
    # Registramos la ruta del artefacto en el experimento y confirmamos la transacción
    exp.artifact_path = str(path)
    db.commit()
    db.refresh(exp)
    # Devolvemos el experimento ya guardado, con su id y artifact_path definitivos
    return exp


def list_experiments(db: Session) -> List[RopExperiment]:
    # Nos aseguramos de que la tabla exista antes de consultar
    ensure_table()
    # Devolvemos todos los experimentos guardados, del más reciente al más antiguo
    return db.query(RopExperiment).order_by(RopExperiment.created_at.desc()).all()


def get(db: Session, exp_id: int) -> Optional[RopExperiment]:
    # Nos aseguramos de que la tabla exista antes de consultar
    ensure_table()
    # Buscamos el experimento por id (None si no existe)
    return db.query(RopExperiment).filter(RopExperiment.id == exp_id).first()


def load_pipeline(exp: RopExperiment) -> Optional[dict]:
    # Verificamos que el experimento tenga artefacto y que el archivo siga existiendo en disco
    if not exp.artifact_path or not os.path.exists(exp.artifact_path):
        return None
    # Cargamos y devolvemos el pipeline serializado (scaler + PCA + modelo + intervalo conforme)
    return joblib.load(exp.artifact_path)


def delete(db: Session, exp_id: int) -> bool:
    # Buscamos el experimento; si no existe, no hay nada que borrar
    exp = get(db, exp_id)
    if exp is None:
        return False
    # Borramos el artefacto en disco si existe, sin fallar si ya no está (por ejemplo, borrado manual)
    if exp.artifact_path and os.path.exists(exp.artifact_path):
        try:
            os.remove(exp.artifact_path)
        except OSError:
            pass
    # Borramos el registro del experimento y confirmamos la transacción
    db.delete(exp)
    db.commit()
    return True
