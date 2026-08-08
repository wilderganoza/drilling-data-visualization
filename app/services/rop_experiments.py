"""ROP Prediction — experiment persistence (a lightweight model registry).

Each saved experiment stores its wizard config + validation metrics in the
``rop_experiments`` table and its fitted pipeline (scaler + PCA + model + conformal
interval) as a joblib artifact on disk, so it can be reloaded for inference / what-if.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import joblib
from sqlalchemy.orm import Session

from app.models.legacy import RopExperiment
from app.db.session import db_manager

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "model_store" / "rop"

_TABLE_READY = False


def ensure_table() -> None:
    """Create the rop_experiments table if it doesn't exist (it's outside Alembic
    autogenerate, which is unsafe here due to the reflected legacy tables)."""
    global _TABLE_READY
    if _TABLE_READY:
        return
    RopExperiment.__table__.create(bind=db_manager._engine, checkfirst=True)
    # Same not-Alembic-managed convention as the initial create() above — plain
    # idempotent ALTER for a column added after the table already existed in
    # some deployments.
    with db_manager._engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE rop_experiments ADD COLUMN IF NOT EXISTS training_detail JSONB"))
    _TABLE_READY = True


def save(db: Session, *, name: str, description: Optional[str], model_key: str,
         config: dict, metrics: dict, pipeline: dict, training_detail: Optional[dict] = None,
         created_by: Optional[int] = None) -> RopExperiment:
    ensure_table()
    exp = RopExperiment(name=name, description=description, model_key=model_key,
                        config=config, metrics=metrics, training_detail=training_detail,
                        status="completed", created_by=created_by)
    db.add(exp)
    db.flush()  # get id

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"experiment_{exp.id}.joblib"
    joblib.dump(pipeline, path)
    exp.artifact_path = str(path)
    db.commit()
    db.refresh(exp)
    return exp


def list_experiments(db: Session) -> List[RopExperiment]:
    ensure_table()
    return db.query(RopExperiment).order_by(RopExperiment.created_at.desc()).all()


def get(db: Session, exp_id: int) -> Optional[RopExperiment]:
    ensure_table()
    return db.query(RopExperiment).filter(RopExperiment.id == exp_id).first()


def load_pipeline(exp: RopExperiment) -> Optional[dict]:
    if not exp.artifact_path or not os.path.exists(exp.artifact_path):
        return None
    return joblib.load(exp.artifact_path)


def delete(db: Session, exp_id: int) -> bool:
    exp = get(db, exp_id)
    if exp is None:
        return False
    if exp.artifact_path and os.path.exists(exp.artifact_path):
        try:
            os.remove(exp.artifact_path)
        except OSError:
            pass
    db.delete(exp)
    db.commit()
    return True
