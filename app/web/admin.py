"""Ops administration surfaces (global-admin only): assign ops roles to
users, curate the Time-Summary Step Catalog, and review the active validation
rules. Gated by get_current_admin_web — these configure the module rather than
capture field data."""
# Importamos Optional para tipar campos de formulario opcionales
from typing import Optional

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias, leer forms y lanzar/responder HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
# Importamos select para armar consultas explícitas con SQLAlchemy
from sqlalchemy import select
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que exige un usuario administrador
from app.core.deps import get_current_admin_web
# Importamos el modelo User para tipar y consultar usuarios
from app.models.legacy import User
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos el enum de roles operativos disponibles
from app.core.ops_roles import OpsRole
# Importamos el modelo que asocia un usuario con su rol operativo
from app.models.roles import OpsUserRole
# Importamos el modelo del catálogo de pasos del Time Summary
from app.models.time_summary import StepCatalogEntry
# Importamos el modelo de reglas de validación
from app.models.validation import ValidationRule
# Importamos los modelos que solo necesita la vista de auditoría (reportes, planes, eventos)
from app.models.daily_report import DailyReport
from app.models.planning import WellPlan
from app.models.hierarchy import Event
# Importamos el repositorio base genérico para construir repos específicos
from app.repositories.base import BaseRepository
# Importamos las reglas generales por defecto del motor de validación
from app.services.validation_engine import DEFAULT_GENERAL_RULES
# Importamos el motor de templates compartido
from app.web.templating import templates

# Creamos el router de administración, montado bajo /admin/ops
router = APIRouter(prefix="/admin/ops")


# Definimos el repositorio del catálogo de pasos, reutilizando el CRUD genérico
class StepCatalogRepo(BaseRepository[StepCatalogEntry]):
    model = StepCatalogEntry


# Definimos el repositorio de reglas de validación, reutilizando el CRUD genérico
class ValidationRuleRepo(BaseRepository[ValidationRule]):
    model = ValidationRule


def _opt(value: Optional[str]) -> Optional[str]:
    # Normalizamos un string de formulario: recortamos espacios y devolvemos None si queda vacío
    return value.strip() if value and value.strip() else None


def _shell(request: Request, current_user: User, active: str, **ctx) -> HTMLResponse:
    # Renderizamos la página de administración correspondiente a la pestaña activa
    return templates.TemplateResponse(
        request, f"ops/pages/admin_{active}.html",
        {"request": request, "current_user": current_user, "active": active, **ctx},
    )


@router.get("", response_class=HTMLResponse)
async def admin_home(current_user: User = Depends(get_current_admin_web)):
    # Redirigimos la raíz de administración a la pestaña de roles
    return RedirectResponse(url="/admin/ops/roles", status_code=302)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles", response_class=HTMLResponse)
async def roles_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Obtenemos todos los usuarios ordenados por username
    users = db.execute(select(User).order_by(User.username)).scalars().all()
    # Armamos un diccionario user_id -> rol operativo asignado
    roles = {r.user_id: r.role for r in db.execute(select(OpsUserRole)).scalars().all()}
    # Renderizamos la pestaña de roles con la lista de usuarios, sus roles y los roles disponibles
    return _shell(request, current_user, "roles", users=users, roles=roles, all_roles=list(OpsRole))


# ---------------------------------------------------------------------------
# Users — account management (relocated from the legacy Dashboard workspace).
# The create/toggle/delete/password actions still POST to /users/* (unchanged).
# ---------------------------------------------------------------------------
@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Obtenemos todos los usuarios ordenados por id
    users = db.query(User).order_by(User.id).all()
    # Renderizamos la pestaña de usuarios (sin error de formulario inicial)
    return _shell(request, current_user, "users", users=users, form_error=None)


@router.post("/roles", response_class=HTMLResponse)
async def set_role(request: Request, user_id: int = Form(...), role: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Calculamos el conjunto de valores de rol válidos
    valid = {r.value for r in OpsRole}
    # Buscamos si el usuario ya tiene un rol asignado
    existing = db.get(OpsUserRole, user_id)
    if not role:  # clear the role
        # Si no viene rol, limpiamos la asignación existente (si la había)
        if existing:
            db.delete(existing)
    elif role in valid:
        # Si el rol es válido, actualizamos la asignación existente o creamos una nueva
        if existing:
            existing.role = role
        else:
            db.add(OpsUserRole(user_id=user_id, role=role))
    db.commit()
    # Releemos usuarios y roles actualizados para refrescar la tabla
    users = db.execute(select(User).order_by(User.username)).scalars().all()
    roles = {r.user_id: r.role for r in db.execute(select(OpsUserRole)).scalars().all()}
    # Devolvemos el partial de la tabla de roles actualizada
    return templates.TemplateResponse(
        request, "ops/partials/admin_roles_table.html",
        {"request": request, "users": users, "roles": roles, "all_roles": list(OpsRole)},
    )


# ---------------------------------------------------------------------------
# Step Catalog (feeds the Time Summary "Step" dropdown / phase auto-fill)
# ---------------------------------------------------------------------------

def _steps_response(request: Request, db: Session) -> HTMLResponse:
    # Obtenemos todas las entradas del catálogo de pasos, ordenadas por perfil
    entries = StepCatalogRepo(db).list(order_by=StepCatalogEntry.profile, limit=1000)
    # Reordenamos en memoria por (perfil, número de paso) para una presentación consistente
    entries = sorted(entries, key=lambda e: (e.profile, e.step_no))
    # Devolvemos el partial de la tabla del catálogo de pasos
    return templates.TemplateResponse(
        request, "ops/partials/admin_steps_table.html",
        {"request": request, "entries": entries},
    )


@router.get("/step-catalog", response_class=HTMLResponse)
async def steps_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Obtenemos todas las entradas del catálogo de pasos, ordenadas por perfil
    entries = StepCatalogRepo(db).list(order_by=StepCatalogEntry.profile, limit=1000)
    # Reordenamos en memoria por (perfil, número de paso)
    entries = sorted(entries, key=lambda e: (e.profile, e.step_no))
    # Renderizamos la pestaña del catálogo de pasos
    return _shell(request, current_user, "steps", entries=entries)


@router.post("/step-catalog", response_class=HTMLResponse)
async def create_step(
    request: Request, profile: str = Form(...), step_no: str = Form(...), phase: str = Form(...),
    operation: str = Form(...), version: str = Form("v1"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web),
):
    # Creamos una nueva entrada del catálogo, normalizando los campos opcionales y aplicando defaults
    StepCatalogRepo(db).create(
        profile=_opt(profile) or "horizontal", version=_opt(version) or "v1",
        step_no=int(step_no) if step_no.strip() else 0, phase=_opt(phase) or "", operation=_opt(operation) or "",
        created_by=current_user.id,
    )
    db.commit()
    # Devolvemos la tabla del catálogo ya actualizada
    return _steps_response(request, db)


@router.put("/step-catalog/{entry_id}", response_class=HTMLResponse)
async def update_step(
    request: Request, entry_id: str, profile: str = Form(...), step_no: str = Form(...), phase: str = Form(...),
    operation: str = Form(...), version: str = Form("v1"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web),
):
    repo = StepCatalogRepo(db)
    # Buscamos la entrada a actualizar
    entry = repo.get(entry_id)
    # Verificamos que la entrada exista
    if entry is None:
        raise HTTPException(404)
    # Actualizamos la entrada con los valores normalizados del formulario
    repo.update(entry, profile=_opt(profile) or "horizontal", version=_opt(version) or "v1",
                step_no=int(step_no) if step_no.strip() else 0, phase=_opt(phase) or "", operation=_opt(operation) or "",
                updated_by=current_user.id)
    db.commit()
    # Devolvemos la tabla del catálogo ya actualizada
    return _steps_response(request, db)


@router.delete("/step-catalog/{entry_id}", response_class=HTMLResponse)
async def delete_step(request: Request, entry_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    repo = StepCatalogRepo(db)
    # Buscamos la entrada a borrar
    entry = repo.get(entry_id)
    # Verificamos que la entrada exista
    if entry is None:
        raise HTTPException(404)
    # Borramos la entrada del catálogo
    repo.delete(entry)
    db.commit()
    # Devolvemos la tabla del catálogo ya actualizada
    return _steps_response(request, db)


# ---------------------------------------------------------------------------
# Validation rules (read-only transparency view of the active engine)
# ---------------------------------------------------------------------------

def _rules_response(request: Request, db: Session) -> HTMLResponse:
    # Obtenemos todas las reglas de validación, ordenadas por su orden de presentación
    rules = ValidationRuleRepo(db).list(order_by=ValidationRule.sort_order, limit=500)
    # Devolvemos el partial de la tabla de reglas
    return templates.TemplateResponse(request, "ops/partials/admin_rules_table.html", {"request": request, "rules": rules})


@router.get("/validation-rules", response_class=HTMLResponse)
async def validation_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Obtenemos todas las reglas de validación, ordenadas por su orden de presentación
    rules = ValidationRuleRepo(db).list(order_by=ValidationRule.sort_order, limit=500)
    # Renderizamos la pestaña de reglas de validación
    return _shell(request, current_user, "validation", rules=rules)


@router.post("/validation-rules/restore-defaults", response_class=HTMLResponse)
async def restore_default_rules(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    repo = ValidationRuleRepo(db)
    # Borramos todas las reglas generales existentes para reemplazarlas por las de fábrica
    for r in repo.list(filters={"report_type": "general"}, limit=500):
        db.delete(r)
    db.flush()
    # Recreamos cada regla general por defecto, preservando su orden original
    for i, (fn, lvl, chk, p1, p2, fn2, msg) in enumerate(DEFAULT_GENERAL_RULES):
        repo.create(report_type="general", field_name=fn, level=lvl, check=chk, param1=p1, param2=p2,
                    field_name2=fn2, message=msg, is_active=True, sort_order=i, created_by=current_user.id)
    db.commit()
    # Devolvemos la tabla de reglas ya restaurada
    return _rules_response(request, db)


@router.post("/validation-rules", response_class=HTMLResponse)
async def create_rule(
    request: Request, report_type: str = Form("general"), field_name: str = Form(...), level: str = Form("mandatory"),
    check: str = Form("required"), param1: str = Form(""), param2: str = Form(""), field_name2: str = Form(""),
    message: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web),
):
    # Creamos una nueva regla de validación, normalizando texto y parseando los parámetros numéricos
    ValidationRuleRepo(db).create(
        report_type=_opt(report_type) or "general", field_name=_opt(field_name) or "", level=_opt(level) or "mandatory",
        check=_opt(check) or "required", param1=_num(param1), param2=_num(param2), field_name2=_opt(field_name2),
        message=_opt(message) or "", is_active=True, sort_order=999, created_by=current_user.id,
    )
    db.commit()
    # Devolvemos la tabla de reglas ya actualizada
    return _rules_response(request, db)


@router.put("/validation-rules/{rule_id}", response_class=HTMLResponse)
async def update_rule(
    request: Request, rule_id: str, field_name: str = Form(...), level: str = Form("mandatory"),
    check: str = Form("required"), param1: str = Form(""), param2: str = Form(""), field_name2: str = Form(""),
    message: str = Form(...), is_active: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web),
):
    repo = ValidationRuleRepo(db)
    # Buscamos la regla a actualizar
    rule = repo.get(rule_id)
    # Verificamos que la regla exista
    if rule is None:
        raise HTTPException(404)
    # Actualizamos la regla con los valores normalizados del formulario
    repo.update(rule, field_name=_opt(field_name) or "", level=_opt(level) or "mandatory", check=_opt(check) or "required",
                param1=_num(param1), param2=_num(param2), field_name2=_opt(field_name2), message=_opt(message) or "",
                is_active=bool(is_active), updated_by=current_user.id)
    db.commit()
    # Devolvemos la tabla de reglas ya actualizada
    return _rules_response(request, db)


@router.delete("/validation-rules/{rule_id}", response_class=HTMLResponse)
async def delete_rule(request: Request, rule_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    repo = ValidationRuleRepo(db)
    # Buscamos la regla a borrar
    rule = repo.get(rule_id)
    # Verificamos que la regla exista
    if rule is None:
        raise HTTPException(404)
    # Borramos la regla
    repo.delete(rule)
    db.commit()
    # Devolvemos la tabla de reglas ya actualizada
    return _rules_response(request, db)


def _num(value):
    # Intentamos convertir el valor de formulario a float, devolviendo None si viene vacío o no es convertible
    try:
        return float(value) if value and value.strip() else None
    except (TypeError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Audit / Activity — the approval trail across Daily Reports and Well Plans
# (who created / submitted / approved what, and when). Reads the AuditMixin and
# workflow timestamps already stored on those records.
# ---------------------------------------------------------------------------

@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_web)):
    # Armamos un diccionario user_id -> nombre a mostrar (nombre completo o username)
    names = {u.id: (u.full_name or u.username) for u in db.execute(select(User)).scalars().all()}
    # Armamos un diccionario event_id -> código de evento, para las referencias de cada entrada
    ev_code = {str(e.id): (e.event_code or "Event") for e in db.execute(select(Event)).scalars().all()}
    entries = []

    def add(when, actor_id, action, entity, ref, status):
        # Si no hay fecha del evento, no lo registramos (esa acción nunca ocurrió)
        if when is None:
            return
        # Agregamos una entrada de auditoría resolviendo el nombre del actor
        entries.append({"when": when, "actor": names.get(actor_id, "—"), "action": action,
                        "entity": entity, "ref": ref, "status": status})

    # Recorremos todos los Daily Reports registrando creación, envío y aprobación
    for r in db.execute(select(DailyReport)).scalars().all():
        ref = f"{ev_code.get(str(r.event_id), 'Event')} · {r.report_date}"
        add(r.created_at, r.created_by, "Created", "Daily Report", ref, r.workflow_status)
        add(r.submitted_at, r.submitted_by, "Submitted", "Daily Report", ref, r.workflow_status)
        add(r.approved_at, r.approved_by, "Approved", "Daily Report", ref, r.workflow_status)
    # Recorremos todos los Well Plans registrando envío y aprobación
    for p in db.execute(select(WellPlan)).scalars().all():
        ref = ev_code.get(str(p.event_id), "Event")
        add(p.submitted_at, p.submitted_by, "Submitted", "Well Plan", ref, p.status)
        add(p.approved_at, p.approved_by_user, "Approved", "Well Plan", ref, p.status)

    # Ordenamos todas las entradas de más reciente a más antigua
    entries.sort(key=lambda e: e["when"], reverse=True)
    # Renderizamos la pestaña de auditoría con las 200 entradas más recientes
    return _shell(request, current_user, "audit", entries=entries[:200])
