"""ROP Prediction — durable store for finished wizard jobs (pre-selection / HPO /
validation), so a revisited step shows real results instead of "not run yet"
after a server restart, without re-running potentially minutes of work.

The in-process job store (rop_jobs.py) stays the primary, fast path for a job
still within the same server process; this module is the fallback read path
(and the write-through on completion) for when it isn't — same relationship
`rop_experiments.py` has to a saved model, just triggered automatically on
every job completion instead of only when the user clicks "Save".
"""
from __future__ import annotations

# Importamos os para verificar/borrar los archivos joblib de artefactos en disco
import os
# Importamos Path para construir la ruta del directorio de artefactos
from pathlib import Path
# Importamos Optional para tipar el retorno de load()
from typing import Optional

# Importamos joblib para serializar/deserializar el pipeline sklearn (no es JSON-safe)
import joblib
# Importamos Session para tipar la sesión de base de datos recibida
from sqlalchemy.orm import Session

# Importamos el modelo RopWizardJob donde persistimos cada job del wizard
from app.models.legacy import RopWizardJob
# Importamos db_manager para acceder al engine y crear la tabla si no existe
from app.db.session import db_manager

# Definimos el directorio donde guardamos los artefactos joblib de cada job
ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "model_store" / "rop_runs"

# Retention cap: wizard-run rows/artifacts beyond this are pruned oldest-first
# on every save. Unlike saved experiments (explicitly user-managed, with their
# own Delete), these are working files — without a cap every validation run
# would leave a joblib on disk forever.
_MAX_ROWS = 40

# Bandera para no intentar crear la tabla en cada llamada
_TABLE_READY = False


def ensure_table() -> None:
    # Usamos la bandera global para crear la tabla una sola vez por proceso
    global _TABLE_READY
    # Si ya la creamos antes, no hacemos nada
    if _TABLE_READY:
        return
    # Creamos la tabla si todavía no existe en la base de datos
    RopWizardJob.__table__.create(bind=db_manager._engine, checkfirst=True)
    # Marcamos la tabla como lista para evitar chequeos repetidos
    _TABLE_READY = True


def save(db: Session, job_id: str, kind: str, state: dict, result: dict) -> None:
    """Persists a finished job. For "validation" jobs, `result["pipeline"]`
    (fitted sklearn objects — scaler/PCA/model) isn't JSON-safe, so it's
    joblib-dumped to disk separately and excluded from the stored JSON,
    matching rop_experiments.py's own artifact convention."""
    # Aseguramos que la tabla exista antes de escribir
    ensure_table()
    # Copiamos result para no mutar el diccionario que nos pasó el llamador
    result = dict(result)
    pipeline_path = None
    # Si es un job de validación con pipeline sklearn, lo separamos del JSON
    if kind == "validation" and "pipeline" in result:
        # Sacamos el pipeline del diccionario (no es serializable a JSON)
        pipeline = result.pop("pipeline")
        # Creamos el directorio de artefactos si todavía no existe
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        # Construimos la ruta del archivo joblib para este job
        path = ARTIFACT_DIR / f"{job_id}.joblib"
        # Guardamos el pipeline en disco
        joblib.dump(pipeline, path)
        # Guardamos la ruta para registrarla en la fila
        pipeline_path = str(path)

    # Buscamos si ya existe una fila para este job_id
    row = db.get(RopWizardJob, job_id)
    if row is None:
        # Creamos la fila si es la primera vez que se guarda este job
        row = RopWizardJob(job_id=job_id)
        db.add(row)
    # Actualizamos los campos de la fila con el estado y resultado actuales
    row.kind = kind
    row.state = state
    row.result = result
    row.pipeline_path = pipeline_path
    # Confirmamos la escritura en la base de datos
    db.commit()

    # Oldest-first retention pruning (never the row just written).
    # Buscamos las filas más antiguas que exceden el límite de retención
    stale = (db.query(RopWizardJob).order_by(RopWizardJob.created_at.desc())
               .offset(_MAX_ROWS).all())
    for old in stale:
        # Si la fila antigua tiene un artefacto en disco, lo borramos también
        if old.pipeline_path and os.path.exists(old.pipeline_path):
            try:
                os.remove(old.pipeline_path)
            except OSError:
                # Ignoramos errores de borrado (archivo ya no existe, permisos, etc.)
                pass
        # Borramos la fila antigua de la base de datos
        db.delete(old)
    # Confirmamos los borrados solo si hubo filas antiguas
    if stale:
        db.commit()


def load(db: Session, job_id: str) -> Optional[dict]:
    """Returns {"kind", "state", "result"} (with "pipeline" re-attached into
    result for validation jobs, loaded from its joblib artifact) or None if no
    persisted row exists / the artifact is missing on disk."""
    # Aseguramos que la tabla exista antes de leer
    ensure_table()
    # Buscamos la fila del job solicitado
    row = db.get(RopWizardJob, job_id)
    if row is None:
        # Si no hay fila persistida, devolvemos None
        return None
    # Copiamos el resultado guardado para no exponer el objeto interno del ORM
    result = dict(row.result or {})
    if row.kind == "validation":
        # Si es un job de validación, verificamos que el artefacto joblib exista en disco
        if not row.pipeline_path or not os.path.exists(row.pipeline_path):
            # Sin artefacto no podemos reconstruir el pipeline, así que devolvemos None
            return None
        # Cargamos el pipeline sklearn desde disco y lo reinsertamos en el resultado
        result["pipeline"] = joblib.load(row.pipeline_path)
    # Devolvemos el job reconstruido (kind, state, result)
    return {"kind": row.kind, "state": row.state, "result": result}
