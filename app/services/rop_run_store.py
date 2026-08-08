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

import os
from pathlib import Path
from typing import Optional

import joblib
from sqlalchemy.orm import Session

from app.models.legacy import RopWizardJob
from app.db.session import db_manager

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "model_store" / "rop_runs"

# Retention cap: wizard-run rows/artifacts beyond this are pruned oldest-first
# on every save. Unlike saved experiments (explicitly user-managed, with their
# own Delete), these are working files — without a cap every validation run
# would leave a joblib on disk forever.
_MAX_ROWS = 40

_TABLE_READY = False


def ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    RopWizardJob.__table__.create(bind=db_manager._engine, checkfirst=True)
    _TABLE_READY = True


def save(db: Session, job_id: str, kind: str, state: dict, result: dict) -> None:
    """Persists a finished job. For "validation" jobs, `result["pipeline"]`
    (fitted sklearn objects — scaler/PCA/model) isn't JSON-safe, so it's
    joblib-dumped to disk separately and excluded from the stored JSON,
    matching rop_experiments.py's own artifact convention."""
    ensure_table()
    result = dict(result)
    pipeline_path = None
    if kind == "validation" and "pipeline" in result:
        pipeline = result.pop("pipeline")
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"{job_id}.joblib"
        joblib.dump(pipeline, path)
        pipeline_path = str(path)

    row = db.get(RopWizardJob, job_id)
    if row is None:
        row = RopWizardJob(job_id=job_id)
        db.add(row)
    row.kind = kind
    row.state = state
    row.result = result
    row.pipeline_path = pipeline_path
    db.commit()

    # Oldest-first retention pruning (never the row just written).
    stale = (db.query(RopWizardJob).order_by(RopWizardJob.created_at.desc())
               .offset(_MAX_ROWS).all())
    for old in stale:
        if old.pipeline_path and os.path.exists(old.pipeline_path):
            try:
                os.remove(old.pipeline_path)
            except OSError:
                pass
        db.delete(old)
    if stale:
        db.commit()


def load(db: Session, job_id: str) -> Optional[dict]:
    """Returns {"kind", "state", "result"} (with "pipeline" re-attached into
    result for validation jobs, loaded from its joblib artifact) or None if no
    persisted row exists / the artifact is missing on disk."""
    ensure_table()
    row = db.get(RopWizardJob, job_id)
    if row is None:
        return None
    result = dict(row.result or {})
    if row.kind == "validation":
        if not row.pipeline_path or not os.path.exists(row.pipeline_path):
            return None
        result["pipeline"] = joblib.load(row.pipeline_path)
    return {"kind": row.kind, "state": row.state, "result": result}
