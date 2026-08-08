"""NPT (Non-Productive Time) subsection. Never hard-deleted — records close
in place (SoftCloseMixin) rather than being removed, since NPT is the
knowledge-management record failure metrics get built from."""
# Importamos datetime para parsear y operar con fechas/horas
from datetime import datetime
# Importamos Optional para tipar valores que pueden ser None
from typing import Optional

# Importamos las clases de FastAPI para el router, dependencias, forms y errores HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
# Importamos la respuesta HTML para los fragmentos renderizados
from fastapi.responses import HTMLResponse
# Importamos el tipo de sesión de SQLAlchemy
from sqlalchemy.orm import Session

# Importamos la dependencia que nos entrega el usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos el helper que exige un rol determinado
from app.core.permissions import require_ops_role
# Importamos el enum de roles operacionales
from app.core.ops_roles import OpsRole
# Importamos el repositorio de reportes diarios, para validar el reporte padre
from app.repositories.daily_report_repository import DailyReportRepository
# Importamos el repositorio de registros NPT
from app.repositories.npt_repository import NptRepository
# Importamos el objeto de templates Jinja de la app
from app.web.templating import templates

# Creamos el router y lo montamos bajo el prefijo /ops
router = APIRouter(prefix="/ops")

# Definimos la dependencia que exige alguno de estos roles para poder editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)


def _opt(value: Optional[str]) -> Optional[str]:
    # Devolvemos el valor recortado, o None si viene vacío/en blanco
    return value.strip() if value and value.strip() else None


def _opt_num(value: Optional[str]) -> Optional[float]:
    # Convertimos a float si hay valor, o None si viene vacío
    return float(value) if value and value.strip() else None


def _opt_datetime(value: Optional[str]) -> Optional[datetime]:
    # Si no hay valor, devolvemos None
    if not value:
        return None
    # Parseamos el datetime-local del formulario HTML (formato "YYYY-MM-DDTHH:MM")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def _gross_hours(start, end) -> Optional[float]:
    # Si falta el inicio o el fin, no podemos calcular la duración
    if not start or not end:
        return None
    # Calculamos la diferencia en horas
    delta = (end - start).total_seconds() / 3600
    # Redondeamos a 2 decimales; descartamos duraciones negativas (fin antes que inicio)
    return round(delta, 2) if delta >= 0 else None


def _ensure_report_unlocked(db: Session, report_id: str) -> None:
    # Buscamos el reporte diario padre
    rep = DailyReportRepository(db).get(report_id)
    # Si el reporte está aprobado/bloqueado, rechazamos la edición
    if rep is not None and getattr(rep, "is_locked", False):
        raise HTTPException(status_code=423, detail="Report is approved and locked; reopen it to edit.")


def _valid_parent_id(db: Session, parent_id: str, report_id: str) -> Optional[str]:
    """A nested NPT's parent must belong to the same report — else drop the link."""
    # Normalizamos el id del padre (vacío -> None)
    pid = _opt(parent_id)
    if pid is None:
        return None
    # Buscamos el NPT padre propuesto
    parent = NptRepository(db).get(pid)
    # Solo aceptamos el vínculo si el padre existe y pertenece al mismo reporte
    return pid if parent is not None and str(parent.daily_report_id) == report_id else None


def _npt_response(request: Request, db: Session, report_id: str) -> HTMLResponse:
    # Buscamos el reporte diario padre; si no existe, respondemos 404
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Obtenemos todos los registros NPT del reporte
    items = NptRepository(db).list_for_report(report_id)
    # Renderizamos el fragmento de la pestaña NPT
    return templates.TemplateResponse(
        request, "ops/partials/daily_report_npt.html",
        {"request": request, "report": report, "items": items},
    )


@router.get("/reports/{report_id}/npt", response_class=HTMLResponse)
async def npt_tab(request: Request, report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Devolvemos el fragmento de la pestaña NPT para este reporte
    return _npt_response(request, db, report_id)


@router.post("/reports/{report_id}/npt", response_class=HTMLResponse)
async def create_npt(
    request: Request, report_id: str,
    npt_type: str = Form(""), title: str = Form(""), description: str = Form(""), cause: str = Form(""),
    start_time: str = Form(""), end_time: str = Form(""), failure_md: str = Form(""),
    contractor_name: str = Form(""), contractual_link: str = Form(""), contractual_no: str = Form(""),
    type_cost: str = Form(""), equip_cost: str = Form(""), other_cost: str = Form(""), parent_id: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Buscamos el reporte diario padre; si no existe, respondemos 404
    report = DailyReportRepository(db).get(report_id)
    if report is None:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de crear
    _ensure_report_unlocked(db, report_id)
    # Parseamos las fechas de inicio y fin
    start = _opt_datetime(start_time)
    end = _opt_datetime(end_time)
    # Calculamos las horas brutas de NPT a partir del rango
    gross = _gross_hours(start, end)
    # Creamos el registro NPT; net_hours arranca igual a gross_hours (se ajusta luego si aplica)
    NptRepository(db).create(
        daily_report_id=report_id, parent_id=_valid_parent_id(db, parent_id, report_id), npt_type=_opt(npt_type), title=_opt(title),
        description=_opt(description), cause=_opt(cause), start_time=start, end_time=end, gross_hours=gross, net_hours=gross,
        failure_md=_opt_num(failure_md), contractor_name=_opt(contractor_name),
        contractual_link=_opt(contractual_link), contractual_no=_opt(contractual_no),
        type_cost=_opt_num(type_cost), equip_cost=_opt_num(equip_cost), other_cost=_opt_num(other_cost),
        created_by=current_user.id,
    )
    db.commit()
    return _npt_response(request, db, report_id)


@router.put("/reports/{report_id}/npt/{npt_id}", response_class=HTMLResponse)
async def update_npt(
    request: Request, report_id: str, npt_id: str,
    npt_type: str = Form(""), title: str = Form(""), description: str = Form(""), cause: str = Form(""),
    start_time: str = Form(""), end_time: str = Form(""), failure_md: str = Form(""),
    contractor_name: str = Form(""), contractual_link: str = Form(""), contractual_no: str = Form(""),
    type_cost: str = Form(""), equip_cost: str = Form(""), other_cost: str = Form(""), parent_id: str = Form(""),
    reviewer_name: str = Form(""), preventive_actions: str = Form(""), lessons_learned: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    repo = NptRepository(db)
    # Buscamos el registro NPT a actualizar
    npt = repo.get(npt_id)
    # Verificamos que exista y pertenezca al reporte indicado en la URL
    if npt is None or str(npt.daily_report_id) != report_id:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de editar
    _ensure_report_unlocked(db, report_id)
    if getattr(npt, "is_closed", False):
        # The UI promises "Closed records can't be reopened" on the close
        # confirm, but nothing enforced it server-side — the "View" modal for
        # a closed record rendered the same editable form with a working Save,
        # silently rewriting a closed failure-history record.
        # Rechazamos la edición si el registro ya está cerrado
        raise HTTPException(423, "This NPT record is closed and can't be edited.")
    if parent_id and parent_id == npt_id:
        # Evitamos que un registro se referencie a sí mismo como padre
        raise HTTPException(400, "An NPT record can't be its own parent.")
    # Parseamos las fechas de inicio y fin
    start = _opt_datetime(start_time)
    end = _opt_datetime(end_time)
    # Recalculamos las horas brutas de NPT a partir del rango
    gross = _gross_hours(start, end)
    # Actualizamos el registro con los nuevos valores
    repo.update(
        npt, parent_id=_valid_parent_id(db, parent_id, report_id), npt_type=_opt(npt_type), title=_opt(title), description=_opt(description), cause=_opt(cause),
        start_time=start, end_time=end, gross_hours=gross, net_hours=gross, failure_md=_opt_num(failure_md),
        contractor_name=_opt(contractor_name), contractual_link=_opt(contractual_link), contractual_no=_opt(contractual_no),
        type_cost=_opt_num(type_cost), equip_cost=_opt_num(equip_cost), other_cost=_opt_num(other_cost),
        reviewer_name=_opt(reviewer_name), preventive_actions=_opt(preventive_actions), lessons_learned=_opt(lessons_learned),
        updated_by=current_user.id,
    )
    db.commit()
    return _npt_response(request, db, report_id)


@router.post("/reports/{report_id}/npt/{npt_id}/close", response_class=HTMLResponse)
async def close_npt(request: Request, report_id: str, npt_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = NptRepository(db)
    # Buscamos el registro NPT a cerrar
    npt = repo.get(npt_id)
    # Verificamos que exista y pertenezca al reporte indicado en la URL
    if npt is None or str(npt.daily_report_id) != report_id:
        raise HTTPException(404)
    # Verificamos que el reporte no esté bloqueado antes de cerrar
    _ensure_report_unlocked(db, report_id)
    # Cerramos el registro en lugar de eliminarlo (soft close)
    repo.close(npt, closed_by=current_user.id)
    db.commit()
    return _npt_response(request, db, report_id)
