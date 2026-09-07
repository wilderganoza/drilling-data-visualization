"""Tiny in-process job manager for the heavy ROP-Prediction steps.

Training / HPO / validation run in a thread pool instead of blocking the request,
so the UI can show progress and the event loop stays responsive. Good enough for a
single-process deployment; swap for Celery/RQ if this ever needs to scale out.
"""
from __future__ import annotations

# Importamos threading para el lock y los eventos de cancelación cooperativa
import threading
# Importamos time para medir cuánto lleva corriendo cada job
import time
# Importamos traceback para loguear errores no manejados dentro del hilo de trabajo
import traceback
# Importamos uuid para generar ids de job únicos entre reinicios del servidor
import uuid
# Importamos ThreadPoolExecutor para correr los jobs pesados fuera del event loop
from concurrent.futures import ThreadPoolExecutor
# Importamos los tipos que usamos para anotar callbacks y el diccionario de jobs
from typing import Any, Callable, Dict


class JobCancelled(Exception):
    """A job function can raise this at a cooperative checkpoint (after checking
    its own `cancel_event.is_set()`) to stop promptly instead of running every
    remaining stage to completion — expected control flow (the user hit Back/
    Cancel), not a bug. `_run()` below already no-ops the write-back for a
    cancelled job regardless of how it ends (cancel() pops it from `_JOBS`
    first), so this only changes whether the traceback gets logged."""


# Creamos el pool de hilos donde corren los jobs (máximo 2 a la vez)
_EXECUTOR = ThreadPoolExecutor(max_workers=2)
# Guardamos el estado de cada job (running/done/error) indexado por job_id
_JOBS: Dict[str, dict] = {}
# Guardamos el evento de cancelación de cada job, indexado por job_id
_CANCEL_EVENTS: Dict[str, threading.Event] = {}
# Definimos el lock que protege el acceso concurrente a _JOBS y _CANCEL_EVENTS
_LOCK = threading.Lock()
_MAX_JOBS = 60  # completed jobs beyond this are evicted oldest-first (never a running one)


def _evict_old_jobs_locked() -> None:
    """Caller must hold _LOCK. Drops the oldest finished (done/error) jobs once
    the store grows past _MAX_JOBS. Never touches a "running" job, so an
    in-flight run (and the `/save` endpoint's later read of a finished one) is
    never stranded by this — without it, _JOBS grew unbounded since nothing else
    ever removed a completed entry."""
    if len(_JOBS) <= _MAX_JOBS:
        # Todavía no superamos el límite, no hay nada que desalojar
        return
    for jid in list(_JOBS):
        if len(_JOBS) <= _MAX_JOBS:
            # Ya bajamos del límite, dejamos de desalojar
            break
        if _JOBS[jid]["status"] != "running":
            # Solo eliminamos jobs terminados (done/error), nunca uno en ejecución
            _JOBS.pop(jid, None)


def submit(fn: Callable[..., Any], *args, on_done: Callable[[str, Any], None] | None = None, **kwargs) -> str:
    """Runs ``fn(*args, progress_cb=<callable>, cancel_event=<threading.Event>, **kwargs)``
    in the thread pool.
    ``fn`` may call ``progress_cb(data)`` any number of times while running to
    publish incremental status (e.g. per-model results) — the latest value is
    readable via ``get(job_id)["progress"]`` while status is still "running".
    ``fn`` may also check ``cancel_event.is_set()`` between units of work (e.g.
    before starting the next model / HPO trial) to stop early once ``cancel()``
    is called — cooperative only, a unit of work already in progress still runs
    to completion, but its result is discarded (see ``cancel()``).
    ``on_done(job_id, result)`` (optional) runs in the worker thread right after
    a successful, non-cancelled completion — the hook for durable persistence,
    guaranteed to fire even if no browser ever polls the finished job. Its
    exceptions are logged-and-swallowed so a persistence hiccup can't turn a
    successful run into an error."""
    # UUID-based, not a per-process counter: a persisted job (see
    # rop_run_store.py) must never collide with an unrelated job created after
    # a server restart, which a recycled "job1, job2, ..." counter would risk.
    # Generamos un id de job único (uuid, no contador) para evitar colisiones tras un reinicio
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    # Creamos el evento de cancelación propio de este job
    cancel_event = threading.Event()
    # Registramos el instante de inicio para poder calcular el tiempo transcurrido después
    started_at = time.monotonic()
    with _LOCK:
        # Desalojamos jobs viejos antes de registrar uno nuevo, si hace falta
        _evict_old_jobs_locked()
        # Registramos el job como "running" antes de lanzarlo al pool
        _JOBS[job_id] = {"status": "running", "result": None, "error": None, "progress": None, "started_at": started_at}
        _CANCEL_EVENTS[job_id] = cancel_event

    def _progress_cb(data):
        # Actualizamos el progreso del job solo si sigue corriendo (evita pisar un resultado ya final)
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is not None and job["status"] == "running":
                job["progress"] = data

    def _run():
        try:
            # Ejecutamos la función del job pasándole los hooks de progreso y cancelación
            result = fn(*args, progress_cb=_progress_cb, cancel_event=cancel_event, **kwargs)
            with _LOCK:
                cancelled = job_id not in _JOBS  # absent => cancel() already discarded this job
                if not cancelled:
                    # Guardamos el resultado final solo si el job no fue cancelado mientras corría
                    _JOBS[job_id] = {"status": "done", "result": result, "error": None, "progress": None}
            if not cancelled and on_done is not None:
                try:
                    # Disparamos el hook de persistencia (por ejemplo, guardar el experimento)
                    on_done(job_id, result)
                except Exception:  # noqa: BLE001 — persistence must never fail the run
                    # Una falla al persistir no debe convertir una corrida exitosa en un error
                    traceback.print_exc()
        except JobCancelled:
            # Cancelación esperada: el job ya fue removido de _JOBS por cancel(), no hay nada que escribir
            pass
        except Exception as exc:  # noqa: BLE001
            # Cualquier otro error inesperado lo logueamos y lo guardamos como estado "error"
            traceback.print_exc()
            with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id] = {"status": "error", "result": None, "error": str(exc)[:400], "progress": None}
        finally:
            # Limpiamos el evento de cancelación al terminar, corra como corra el job
            with _LOCK:
                _CANCEL_EVENTS.pop(job_id, None)

    # Enviamos la corrida al pool de hilos y devolvemos el id para que el cliente haga polling
    _EXECUTOR.submit(_run)
    return job_id


def cancel(job_id: str) -> None:
    """Signals the job's cancel_event and immediately drops it from the store —
    a unit of work already running finishes in the background but its result is
    discarded (``_run`` checks ``job_id in _JOBS`` before writing back)."""
    with _LOCK:
        # Recuperamos el evento de cancelación y removemos el job del store de inmediato
        ev = _CANCEL_EVENTS.get(job_id)
        _JOBS.pop(job_id, None)
    if ev is not None:
        # Señalamos el evento para que el job en curso se detenga en su próximo checkpoint
        ev.set()


def request_stop(job_id: str) -> None:
    """Signals the job's cancel_event WITHOUT discarding it — "stop early, keep
    what you have" (unlike ``cancel()``, whose result is thrown away). ``fn``
    completes normally and writes its real result as usual; for optimize(), that
    means the study stops after the current trial and returns the best trial
    found so far, not an empty/partial result."""
    with _LOCK:
        # A diferencia de cancel(), no borramos el job: solo pedimos que pare antes
        ev = _CANCEL_EVENTS.get(job_id)
    if ev is not None:
        ev.set()


def get(job_id: str) -> dict:
    with _LOCK:
        # Devolvemos una copia del estado del job (o un estado "missing" si no existe)
        job = dict(_JOBS.get(job_id, {"status": "missing", "result": None, "error": "unknown job", "progress": None}))
        ev = _CANCEL_EVENTS.get(job_id)
        # Indicamos si ya se pidió detener el job (para que la UI lo refleje)
        job["stop_requested"] = bool(ev is not None and ev.is_set())
        # Calculamos el tiempo transcurrido desde que arrancó, si tenemos el instante de inicio
        job["elapsed"] = (time.monotonic() - job["started_at"]) if job.get("started_at") is not None else None
        return job


def seed_done(job_id: str, result: Any) -> None:
    """Register an already-known result as a completed job under `job_id`,
    without ever running anything — used to adopt a saved experiment's
    persisted result into the SAME redisplay path a live job uses (rop_jobs.get()
    + the caller's own _RUN_CTX-style state record), so no separate rendering
    code is needed for "loaded from history" vs "just finished"."""
    with _LOCK:
        # Registramos directamente el resultado ya conocido como si el job hubiera terminado ahora
        _JOBS[job_id] = {"status": "done", "result": result, "error": None, "progress": None}


def pop(job_id: str) -> dict:
    """Fetch a finished job's payload and drop it from the store."""
    with _LOCK:
        # Devolvemos el job y lo removemos del store en la misma operación
        return _JOBS.pop(job_id, {"status": "missing", "result": None, "error": "unknown job"})
