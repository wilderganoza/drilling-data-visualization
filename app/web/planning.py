"""Planning workspace: Well Planning / AFE, authorized once per Event before
Daily Operations Reports start drawing against its budget. Hierarchy CRUD
lives in Master Data; this workspace only navigates down to an Event via its
own sidebar tree and works within it."""
# Importamos tipos de fecha/hora para parsear campos del formulario
from datetime import date, datetime
# Importamos Optional para tipar campos de formulario opcionales
from typing import Optional

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias, leer forms y lanzar/responder HTTP
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que exige un usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User y el helper de fecha/hora UTC actual
from app.models.legacy import User, utcnow
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos el helper que construye la dependencia de permisos por rol
from app.core.permissions import require_ops_role
# Importamos el enum de roles operativos
from app.core.ops_roles import OpsRole
# Importamos los repositorios de la jerarquía (evento, pozo, wellbore)
from app.repositories.hierarchy_repository import EventRepository, WellRepository, WellboreRepository
# Importamos las configuraciones de las grillas del plan
from app.models.planning_capture import PLAN_CONFIGS
# Importamos el repositorio del plan de pozo (header/AFE)
from app.repositories.planning_repository import WellPlanRepository
# Importamos la función que carga el WellContext compartido (usado en validación)
from app.services.engineering.context import load_context
# Importamos la función que valida el programa completo del pozo
from app.services.planning_validation import validate_program
# Importamos los helpers que arman la cadena de nodos abiertos/activos del árbol lateral
from app.web.tree import chain_for_event, chain_for_wellbore
# Importamos el motor de templates compartido
from app.web.templating import templates

# Creamos el router de Planning
router = APIRouter(prefix="/planning")

# Definimos la dependencia de permisos: solo ADMIN u OFFICE_ENGINEER pueden editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
# Definimos la dependencia de permisos: solo ADMIN puede aprobar
CAN_APPROVE = require_ops_role(OpsRole.ADMIN)

# The engineer's workflow reads left-to-right: Initial Data (the design basis
# captured up front) → Engineering (the design workspace) → Plan (the program
# the design generates + review). Initial-Data and Plan hold DISTINCT grids.
# El flujo del ingeniero se lee de izquierda a derecha: Datos Iniciales (la base de diseño capturada al inicio)
# → Ingeniería (el espacio de diseño) → Plan (el programa que genera el diseño + revisión).
# Datos Iniciales y Plan usan grillas DISTINTAS.
# Definimos las keys de las grillas de datos iniciales (base de diseño)
INITIAL_KEYS: list[str] = ["formation-tops", "geopressure"]
# Definimos los grupos de grillas del plan, agrupados por categoría, con su orden de presentación
PLAN_GROUPS: list[tuple[str, list[str]]] = [
    ("Well Program", ["casing-program", "hole-program", "mud-program", "cement-program"]),
    ("Trajectory", ["directional-plan"]),
    ("Cost & Risk", ["time-depth", "cost-estimate", "risks"]),
]


def _cfgs(keys: list[str]) -> list:
    # Indexamos las configuraciones de grilla por su key
    by_key = {c.key: c for c in PLAN_CONFIGS}
    # Devolvemos las configuraciones en el orden pedido, ignorando keys que no existan
    return [by_key[k] for k in keys if k in by_key]


def _plan_groups() -> list[dict]:
    groups = []
    # Recorremos cada grupo definido y resolvemos sus configuraciones de grilla
    for label, keys in PLAN_GROUPS:
        cfgs = _cfgs(keys)
        # Solo incluimos el grupo si tiene al menos una configuración válida
        if cfgs:
            groups.append({"label": label, "configs": cfgs})
    # Devolvemos la lista de grupos con contenido
    return groups


def _opt(value: Optional[str]) -> Optional[str]:
    # Normalizamos un string de formulario: recortamos espacios y devolvemos None si queda vacío
    return value.strip() if value and value.strip() else None


def _opt_date(value: Optional[str]) -> Optional[date]:
    # Si no viene valor, devolvemos None
    if not value:
        return None
    # Parseamos la fecha en formato ISO (YYYY-MM-DD)
    return datetime.strptime(value, "%Y-%m-%d").date()


def _opt_num(value: Optional[str]) -> Optional[float]:
    # Convertimos a float si el valor no viene vacío, si no devolvemos None
    return float(value) if value and value.strip() else None


@router.get("", response_class=HTMLResponse)
async def planning_index(request: Request, current_user: User = Depends(get_current_user_web)):
    # Renderizamos la página de aterrizaje de Planning
    return templates.TemplateResponse(request, "ops/pages/planning_landing.html", {"request": request, "current_user": current_user})


@router.get("/wellbores/{wellbore_id}", response_class=HTMLResponse)
async def planning_wellbore_detail(request: Request, wellbore_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el wellbore solicitado
    wellbore = WellboreRepository(db).get(wellbore_id)
    # Verificamos que el wellbore exista
    if wellbore is None:
        raise HTTPException(404)
    # Obtenemos el pozo padre del wellbore
    well = WellRepository(db).get(wellbore.well_id)
    # Listamos los eventos del wellbore, ordenados por fecha de inicio
    events = EventRepository(db).list(filters={"wellbore_id": wellbore_id}, order_by=EventRepository.model.start_date)
    # Calculamos la cadena de nodos del árbol lateral que hay que abrir para este wellbore
    chain = chain_for_wellbore(wellbore)
    # Renderizamos el detalle del wellbore, marcando el último nodo de la cadena como activo
    return templates.TemplateResponse(
        request, "ops/pages/planning_wellbore_detail.html",
        {"request": request, "current_user": current_user, "wellbore": wellbore, "well": well, "events": events,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


@router.post("/wellbores/{wellbore_id}/events", response_class=HTMLResponse)
async def create_event(
    request: Request, wellbore_id: str,
    event_code: str = Form(""), event_type: str = Form(""), objective: str = Form(""),
    contractor: str = Form(""), rig_name: str = Form(""), start_date: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Buscamos el wellbore donde se va a crear el evento
    wellbore = WellboreRepository(db).get(wellbore_id)
    # Verificamos que el wellbore exista
    if wellbore is None:
        raise HTTPException(404)
    repo = EventRepository(db)
    # Creamos el nuevo evento con los campos normalizados del formulario
    repo.create(
        wellbore_id=wellbore_id, event_code=_opt(event_code), event_type=_opt(event_type), objective=_opt(objective),
        contractor=_opt(contractor), rig_name=_opt(rig_name), start_date=_opt_date(start_date), created_by=current_user.id,
    )
    db.commit()
    # Releemos los eventos del wellbore ya actualizados
    events = repo.list(filters={"wellbore_id": wellbore_id}, order_by=EventRepository.model.start_date)
    # Devolvemos el partial de la sección de eventos actualizada
    return templates.TemplateResponse(request, "ops/partials/planning_event_section.html", {"request": request, "wellbore": wellbore, "events": events})


@router.delete("/events/{event_id}", response_class=HTMLResponse)
async def delete_event(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    repo = EventRepository(db)
    # Buscamos el evento a borrar
    instance = repo.get(event_id)
    # Verificamos que el evento exista
    if instance is None:
        raise HTTPException(404)
    # Guardamos el wellbore padre antes de borrar, para poder refrescar su lista de eventos
    wellbore_id = instance.wellbore_id
    # Borramos el evento
    repo.delete(instance)
    db.commit()
    # Obtenemos el wellbore padre
    wellbore = WellboreRepository(db).get(wellbore_id)
    # Releemos los eventos restantes del wellbore
    events = repo.list(filters={"wellbore_id": wellbore_id}, order_by=EventRepository.model.start_date)
    # Devolvemos el partial de la sección de eventos actualizada
    return templates.TemplateResponse(request, "ops/partials/planning_event_section.html", {"request": request, "wellbore": wellbore, "events": events})


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def planning_event_detail(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Verificamos que el evento exista
    if event is None:
        raise HTTPException(404)
    # Obtenemos el wellbore padre del evento
    wellbore = WellboreRepository(db).get(event.wellbore_id)
    # Obtenemos el plan (header/AFE) asociado al evento, si existe
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Calculamos la cadena de nodos del árbol lateral que hay que abrir para este evento
    chain = chain_for_event(event)
    # Importamos localmente los módulos de ingeniería para armar la lista de accesos directos (evitamos import circular a nivel de módulo)
    from app.web.engineering import MODULES as ENG_MODULES, ORDER as ENG_ORDER
    # Armamos la lista de módulos de ingeniería en su orden lógico
    eng_modules = [{"key": k, "title": ENG_MODULES[k]["title"]} for k in ENG_ORDER if k in ENG_MODULES]
    # Renderizamos el detalle del evento con las grillas iniciales, los grupos del plan y los módulos de ingeniería
    return templates.TemplateResponse(
        request, "ops/pages/planning_event_detail.html",
        {"request": request, "current_user": current_user, "event": event, "wellbore": wellbore, "plan": plan,
         "plan_configs": PLAN_CONFIGS, "initial_configs": _cfgs(INITIAL_KEYS),
         "plan_groups": _plan_groups(), "eng_modules": eng_modules,
         "tree_open_ids": chain, "tree_active_id": chain[-1]},
    )


@router.get("/events/{event_id}/summary", response_class=HTMLResponse)
async def plan_summary_tab(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Verificamos que el evento exista
    if event is None:
        raise HTTPException(404)
    # Obtenemos el plan asociado al evento, si existe
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Renderizamos el partial de la sección del plan (resumen)
    return templates.TemplateResponse(request, "ops/partials/well_plan_section.html", {"request": request, "event": event, "plan": plan})


@router.post("/events/{event_id}/plan", response_class=HTMLResponse)
async def upsert_well_plan(
    request: Request, event_id: str,
    # No `status`/`approved_by` here — deliberately. Those are exclusively
    # driven by the submit/approve/reopen workflow below (which also locks
    # the plan and records a real approver + timestamp); accepting them from
    # this free-form edit used to let anyone with edit rights set
    # status="Approved" directly, with no lock and no real approver on
    # record — a genuine bypass of the approval workflow, not just a UI
    # inconsistency. Dropping the params means even a hand-crafted POST can't
    # set them anymore, not just the form control.
    # No incluimos `status`/`approved_by` aquí — a propósito. Esos campos los maneja
    # exclusivamente el flujo de submit/approve/reopen de más abajo (que además bloquea
    # el plan y registra un aprobador real + timestamp); aceptarlos desde esta edición
    # libre permitía antes que cualquiera con permiso de edición pusiera
    # status="Approved" directamente, sin bloqueo y sin un aprobador real registrado —
    # un bypass real del flujo de aprobación, no solo una inconsistencia de UI.
    # Al quitar estos parámetros, ni siquiera un POST armado a mano puede ya asignarlos.
    afe_number: str = Form(""), engineer: str = Form(""),
    est_days: str = Form(""), authorized_date: str = Form(""), authorized_md: str = Form(""),
    authorized_tvd: str = Form(""), budget_total: str = Form(""), description: str = Form(""),
    currency: str = Form(""), target_formation: str = Form(""), rig_name: str = Form(""), rig_type: str = Form(""),
    planned_spud_date: str = Form(""), surface_location: str = Form(""), kop_md: str = Form(""),
    max_inclination: str = Form(""), target_azimuth: str = Form(""), surface_northing: str = Form(""),
    surface_easting: str = Form(""), dry_hole_cost: str = Form(""), completion_cost: str = Form(""),
    contingency_pct: str = Form(""), objective_primary: str = Form(""), objective_secondary: str = Form(""),
    geology_prognosis: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT),
):
    # Buscamos el evento asociado
    event = EventRepository(db).get(event_id)
    # Verificamos que el evento exista
    if event is None:
        raise HTTPException(404)
    repo = WellPlanRepository(db)
    # Normalizamos y parseamos todos los campos del formulario del header/AFE
    values = dict(
        afe_number=_opt(afe_number), engineer=_opt(engineer),
        est_days=_opt_num(est_days), authorized_date=_opt_date(authorized_date), authorized_md=_opt_num(authorized_md),
        authorized_tvd=_opt_num(authorized_tvd), budget_total=_opt_num(budget_total), description=_opt(description),
        currency=_opt(currency), target_formation=_opt(target_formation), rig_name=_opt(rig_name), rig_type=_opt(rig_type),
        planned_spud_date=_opt_date(planned_spud_date), surface_location=_opt(surface_location), kop_md=_opt_num(kop_md),
        max_inclination=_opt_num(max_inclination), target_azimuth=_opt_num(target_azimuth),
        surface_northing=_opt_num(surface_northing), surface_easting=_opt_num(surface_easting),
        dry_hole_cost=_opt_num(dry_hole_cost), completion_cost=_opt_num(completion_cost),
        contingency_pct=_opt_num(contingency_pct), objective_primary=_opt(objective_primary),
        objective_secondary=_opt(objective_secondary), geology_prognosis=_opt(geology_prognosis),
    )
    # Buscamos si ya existe un plan para este evento
    plan = repo.get_by_event(event_id)
    if plan is None:
        # Si no existe, creamos el plan con los valores del formulario
        repo.create(event_id=event_id, created_by=current_user.id, **values)
    else:
        # Si el plan está bloqueado (aprobado), rechazamos la edición
        if plan.is_locked:
            raise HTTPException(409, "Plan is approved and locked. Reopen it to edit.")
        # Si no está bloqueado, actualizamos el plan existente
        repo.update(plan, updated_by=current_user.id, **values)
    db.commit()
    # Releemos el plan ya guardado
    plan = repo.get_by_event(event_id)
    # Devolvemos el partial de la sección del plan actualizada
    return templates.TemplateResponse(request, "ops/partials/well_plan_section.html", {"request": request, "event": event, "plan": plan})


# ---------------------------------------------------------------------------
# Program validation — cross-checks the whole well program for coherence
# ---------------------------------------------------------------------------
@router.get("/events/{event_id}/validation", response_class=HTMLResponse)
async def plan_validation_tab(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el evento solicitado
    event = EventRepository(db).get(event_id)
    # Verificamos que el evento exista
    if event is None:
        raise HTTPException(404)
    # Cargamos el WellContext necesario para la validación cruzada
    ctx = load_context(db, event_id)
    # Ejecutamos la validación del programa completo
    report = validate_program(ctx)
    # Renderizamos el partial con el reporte de validación
    return templates.TemplateResponse(request, "ops/partials/plan_validation.html",
                                      {"request": request, "event": event, "v": report})


# ---------------------------------------------------------------------------
# Plan approval workflow (Draft -> Submitted -> Approved). Approving locks it.
# ---------------------------------------------------------------------------
def _plan_status_response(request: Request, db: Session, event_id: str) -> HTMLResponse:
    # Buscamos el evento y su plan asociado
    event = EventRepository(db).get(event_id)
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Resolvemos el usuario que envió el plan, si corresponde
    submitter = db.get(User, plan.submitted_by) if plan and plan.submitted_by else None
    # Resolvemos el usuario que aprobó el plan, si corresponde
    approver = db.get(User, plan.approved_by_user) if plan and plan.approved_by_user else None
    # Renderizamos el partial de estado del plan con submitter/approver resueltos
    return templates.TemplateResponse(
        request, "ops/partials/plan_status.html",
        {"request": request, "event": event, "plan": plan, "submitter": submitter, "approver": approver},
    )


@router.get("/events/{event_id}/plan/status", response_class=HTMLResponse)
async def plan_status(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos que el evento exista
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Devolvemos el estado actual del plan
    return _plan_status_response(request, db, event_id)


@router.post("/events/{event_id}/plan/submit", response_class=HTMLResponse)
async def submit_plan(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Buscamos el plan del evento
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Si no hay plan creado, no se puede enviar a revisión
    if plan is None:
        raise HTTPException(404, "Create the AFE / plan header first.")
    # Si ya está aprobado, no tiene sentido volver a enviarlo
    if plan.status == "Approved":
        raise HTTPException(409, "Already approved.")
    # Marcamos el plan como enviado, registrando quién y cuándo
    plan.status = "Submitted"
    plan.submitted_at = utcnow()
    plan.submitted_by = current_user.id
    db.commit()
    # Devolvemos el estado actualizado del plan
    return _plan_status_response(request, db, event_id)


@router.post("/events/{event_id}/plan/approve", response_class=HTMLResponse)
async def approve_plan(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_APPROVE)):
    # Buscamos el plan del evento
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Verificamos que el plan exista
    if plan is None:
        raise HTTPException(404)
    # Marcamos el plan como aprobado, registrando quién y cuándo, y lo bloqueamos para edición
    plan.status = "Approved"
    plan.approved_at = utcnow()
    plan.approved_by_user = current_user.id
    plan.is_locked = True
    db.commit()
    # Devolvemos el estado actualizado del plan
    return _plan_status_response(request, db, event_id)


@router.post("/events/{event_id}/plan/reopen", response_class=HTMLResponse)
async def reopen_plan(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_APPROVE)):
    # Buscamos el plan del evento
    plan = WellPlanRepository(db).get_by_event(event_id)
    # Verificamos que el plan exista
    if plan is None:
        raise HTTPException(404)
    # Reabrimos el plan: lo volvemos a Draft, lo desbloqueamos y limpiamos los datos de aprobación
    plan.status = "Draft"
    plan.is_locked = False
    plan.approved_at = None
    plan.approved_by_user = None
    db.commit()
    # Devolvemos el estado actualizado del plan
    return _plan_status_response(request, db, event_id)
