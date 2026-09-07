"""Pre-spud Engineering workspace inside Planning — a sub-shell of calculators
(casing design, torque & drag, hydraulics, well control, cementing, directional,
BHA, bit, AFE). Each module: an inputs form (persisted to ops_engineering_designs)
whose values feed a pure calc engine that also reads the well's program grids
(WellContext). One generic route pair serves every module via a registry.

Every module can define `context_defaults(ctx)` to seed its inputs from the
shared design basis (pore/fracture profile, casing/mud program) so each well
starts coherent. Generator modules additionally write their output straight into
a Planning program grid ("design generates the program", like StressCheck)."""
# Importamos csv/io para generar el export CSV de cada módulo
import csv
import io

# Importamos las piezas de FastAPI para definir el router, inyectar dependencias y responder HTML/streaming
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
# Importamos select para la consulta explícita que arma design_report()
from sqlalchemy import select
# Importamos Session para tipar la sesión de base de datos inyectada
from sqlalchemy.orm import Session

# Importamos la dependencia que exige un usuario autenticado
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos el modelo del plan de pozo, usado por design_report()
from app.models.planning import WellPlan
# Importamos la dependencia que nos entrega la sesión de base de datos
from app.db.session import get_db
# Importamos el helper que construye la dependencia de permisos por rol
from app.core.permissions import require_ops_role
# Importamos el enum de roles operativos (ADMIN, OFFICE_ENGINEER, etc.)
from app.core.ops_roles import OpsRole
# Importamos la función que calcula los valores derivados de una fila de grilla
from app.models.capture import compute_values as _compute_values
# Importamos el diccionario de configuraciones de las grillas del plan, indexado por key
from app.models.planning_capture import PLAN_CONFIG_BY_KEY
# Importamos el repositorio genérico de grillas (para reemplazar filas al aplicar un módulo generador)
from app.repositories.capture_repository import GridRepository
# Importamos el repositorio de eventos (para validar que el evento exista)
from app.repositories.hierarchy_repository import EventRepository
# Importamos el repositorio del plan de pozo, usado por design_report()
from app.repositories.planning_repository import WellPlanRepository
# Importamos cada módulo de servicio de ingeniería (uno por calculadora)
from app.services.engineering import (
    afe, bha, bit, casing_design, cementing, directional, hydraulics, stuck_pipe,
    swab_surge, temperature, torque_drag, well_control,
)
# Importamos las utilidades de contexto/escenario: cargar el WellContext, leer/guardar parámetros y administrar escenarios
from app.services.engineering.context import (
    DEFAULT_SCENARIO, delete_scenario, get_params, list_scenarios, load_context, save_params,
)
# Importamos la función que arma las filas del export CSV por módulo
from app.services.engineering.export import module_csv_rows
# Importamos la función que valida el programa completo del pozo, usada por design_report()
from app.services.planning_validation import validate_program
# Importamos el motor de templates compartido
from app.web.templating import templates
# Importamos el helper que bloquea sobrescribir el programa de un plan ya aprobado
from app.web.planning_program import ensure_plan_unlocked

# Creamos el router de Engineering, montado bajo el mismo prefijo que Planning
router = APIRouter(prefix="/planning")
# Definimos la dependencia de permisos: solo ADMIN u OFFICE_ENGINEER pueden editar
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)

# module key -> {title, svc module, result partial}. `compute`/`INPUTS` and the
# optional `context_defaults`/`generate_rows`/`PROGRAM_TARGETS` are read off svc.
# Registramos cada módulo de ingeniería con su título, su servicio de cálculo y el partial que renderiza su resultado
MODULES: dict[str, dict] = {
    "casing_design": {"title": "Casing Design", "svc": casing_design, "partial": "casing"},
    "torque_drag": {"title": "Torque & Drag", "svc": torque_drag, "partial": "torque_drag"},
    "hydraulics": {"title": "Hydraulics", "svc": hydraulics, "partial": "hydraulics"},
    "well_control": {"title": "Well Control", "svc": well_control, "partial": "well_control"},
    "cementing": {"title": "Cementing", "svc": cementing, "partial": "cementing"},
    "temperature": {"title": "Temperature Profile", "svc": temperature, "partial": "temperature"},
    "directional": {"title": "Directional / Anti-collision", "svc": directional, "partial": "directional"},
    "bha": {"title": "BHA Design", "svc": bha, "partial": "bha"},
    "swab_surge": {"title": "Swab & Surge", "svc": swab_surge, "partial": "swab_surge"},
    "stuck_pipe": {"title": "Stuck Pipe / Free-point", "svc": stuck_pipe, "partial": "stuck_pipe"},
    "bit": {"title": "Bit Selection", "svc": bit, "partial": "bit"},
    "afe": {"title": "AFE Builder", "svc": afe, "partial": "afe"},
}
# logical design sequence: trajectory → tubulars → thermal → assembly → hydraulics/ops → cost
# Definimos el orden lógico en que se presentan los módulos: trayectoria → tubulares → térmico → ensamblaje → hidráulica/operaciones → costo
ORDER = ["directional", "casing_design", "cementing", "temperature", "bha", "torque_drag",
         "hydraulics", "swab_surge", "well_control", "stuck_pipe", "bit", "afe"]


def _effective_params(m: dict, ctx, saved: dict) -> dict:
    """saved value > context default (design basis) > static default."""
    # Obtenemos el módulo de servicio asociado
    svc = m["svc"]
    # Calculamos los valores por defecto derivados del contexto (design basis), si el módulo los define
    overrides = svc.context_defaults(ctx) if hasattr(svc, "context_defaults") else {}
    params = {}
    # Recorremos cada input declarado por el módulo para resolver su valor efectivo
    for i in svc.INPUTS:
        # Priorizamos el valor guardado por el usuario si existe
        if i.name in saved:
            params[i.name] = saved[i.name]
        # Si no hay valor guardado, usamos el default derivado del contexto (si está definido)
        elif overrides.get(i.name) is not None:
            params[i.name] = overrides[i.name]
        # Como última opción, caemos al default estático del input
        else:
            params[i.name] = i.default
    # Devolvemos el diccionario de parámetros resuelto
    return params


def _module_context(db: Session, event_id: str, key: str, saved: dict,
                    scenario: str = DEFAULT_SCENARIO) -> dict:
    # Obtenemos la configuración del módulo pedido
    m = MODULES[key]
    svc = m["svc"]
    # Cargamos el WellContext, incluyendo offsets solo para directional y benchmark solo para afe (son costosos de calcular)
    ctx = load_context(db, event_id, with_offsets=(key == "directional"), with_benchmark=(key == "afe"))
    # Resolvemos los parámetros efectivos combinando lo guardado, el contexto y los defaults
    params = _effective_params(m, ctx, saved)
    # Ejecutamos el cálculo del módulo con esos parámetros y el contexto
    res = svc.compute(params, ctx)
    # Armamos la lista de campos del formulario con su valor actual, para renderizar el partial
    fields = [{"name": i.name, "label": i.label, "unit": i.unit, "kind": i.kind, "options": i.options,
               "value": params[i.name]} for i in svc.INPUTS]
    # Armamos la lista de grillas de destino a las que este módulo puede "aplicar" (generar) filas
    targets = [{"key": t, "title": PLAN_CONFIG_BY_KEY[t].title}
               for t in getattr(svc, "PROGRAM_TARGETS", []) if t in PLAN_CONFIG_BY_KEY]
    # Devolvemos el contexto de renderizado del módulo, incluyendo escenarios disponibles
    return {"key": key, "title": m["title"], "fields": fields, "res": res,
            "result_partial": f"ops/partials/engineering/eng_{m['partial']}.html", "event_id": event_id,
            "targets": targets, "scenario": scenario, "scenarios": list_scenarios(db, event_id, key),
            "depth_unit": "ft"}


def _parse_params(key: str, form) -> dict:
    """Raises ValueError (caller turns it into a 400 naming the field) on a
    non-empty numeric value that doesn't parse. This used to silently swap in
    the field's static default and save/re-render THAT as if it were the
    user's input — a mistyped Mud weight ("aa") would silently become 0.0
    with no indication anything was rejected."""
    params = {}
    # Recorremos cada input declarado por el módulo para parsear su valor desde el form
    for i in MODULES[key]["svc"].INPUTS:
        raw = form.get(i.name)
        # Si el input es numérico, validamos que parsee como float
        if i.kind == "number":
            # Si viene vacío o ausente, usamos el default del input (no es un error del usuario)
            if raw in (None, ""):
                params[i.name] = i.default
            else:
                try:
                    # Intentamos convertir el valor ingresado a float
                    params[i.name] = float(raw)
                except ValueError:
                    # Si no parsea, lanzamos el error nombrando el campo para que el caller devuelva un 400
                    raise ValueError(f'"{raw}" is not a valid number for {i.label}.')
        else:
            # Para inputs no numéricos, usamos el valor tal cual (o el default si viene vacío)
            params[i.name] = raw if raw not in (None, "") else i.default
    # Devolvemos los parámetros ya validados
    return params


@router.get("/events/{event_id}/engineering", response_class=HTMLResponse)
async def engineering_shell(request: Request, event_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos que el evento exista antes de mostrar el shell de ingeniería
    if EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Armamos la lista de módulos disponibles en el orden lógico definido
    modules = [{"key": k, "title": MODULES[k]["title"]} for k in ORDER if k in MODULES]
    # Renderizamos el shell, indicando cuál es el primer módulo a mostrar
    return templates.TemplateResponse(request, "ops/partials/engineering_shell.html",
                                      {"request": request, "event_id": event_id, "modules": modules, "first_key": ORDER[0]})


@router.get("/events/{event_id}/design-report", response_class=HTMLResponse)
async def design_report(request: Request, event_id: str, scenario: str = DEFAULT_SCENARIO,
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    """Consolidated, printable Well Design Report — the plan header, every program
    grid, the shared pore/fracture basis, all nine engineering modules and the
    program-validation result on one page (browser Print → PDF)."""
    # Obtenemos el evento y verificamos que exista
    event = EventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(404)
    # Cargamos el contexto completo (con offsets y benchmark) porque el reporte incluye todos los módulos
    ctx_full = load_context(db, event_id, with_offsets=True, with_benchmark=True)
    # Obtenemos el plan (header/AFE) asociado al evento
    plan = WellPlanRepository(db).get_by_event(event_id)
    modules = []
    # Calculamos el resultado de cada módulo de ingeniería, en el orden lógico, para incluirlo en el reporte
    for k in ORDER:
        m = MODULES[k]
        params = _effective_params(m, ctx_full, get_params(db, event_id, k, scenario))
        res = m["svc"].compute(params, ctx_full)
        modules.append({"key": k, "title": m["title"], "res": res,
                        "partial": f"ops/partials/engineering/eng_{m['partial']}.html"})
    # Ejecutamos la validación cruzada de todo el programa del pozo
    validation = validate_program(ctx_full)
    # Renderizamos la página completa del reporte de diseño
    return templates.TemplateResponse(
        request, "ops/pages/design_report.html",
        {"request": request, "event": event, "plan": plan, "ctx": ctx_full, "modules": modules,
         "validation": validation, "event_id": event_id, "depth_unit": "ft", "scenario": scenario,
         "plan_configs": PLAN_CONFIG_BY_KEY})


@router.get("/events/{event_id}/engineering/{key}", response_class=HTMLResponse)
async def engineering_module(request: Request, event_id: str, key: str, scenario: str = DEFAULT_SCENARIO,
                             db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos que el módulo pedido exista y que el evento exista
    if key not in MODULES or EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Armamos el contexto de renderizado del módulo con los parámetros guardados para ese escenario
    ctx = _module_context(db, event_id, key, get_params(db, event_id, key, scenario), scenario)
    # Renderizamos el partial del módulo
    return templates.TemplateResponse(request, "ops/partials/engineering_module.html", {"request": request, **ctx})


@router.post("/events/{event_id}/engineering/{key}", response_class=HTMLResponse)
async def engineering_save(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Verificamos que el módulo pedido exista y que el evento exista
    if key not in MODULES or EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Leemos el form enviado
    form = await request.form()
    # Resolvemos el escenario destino (cae al escenario por defecto si viene vacío)
    scenario = (form.get("_scenario") or DEFAULT_SCENARIO).strip() or DEFAULT_SCENARIO
    try:
        # Parseamos y validamos los parámetros del form
        params = _parse_params(key, form)
    except ValueError as exc:
        # htmx doesn't swap on a 4xx by default, so the form is left exactly
        # as the user typed it (nothing silently replaced) and the global
        # error toast (app.js) surfaces this message.
        # htmx no reemplaza el contenido ante un 4xx, así que el form queda tal cual lo escribió el usuario
        # (nada se reemplaza silenciosamente) y el toast de error global (app.js) muestra este mensaje
        raise HTTPException(status_code=400, detail=str(exc))
    # Guardamos los parámetros validados para este módulo/escenario
    save_params(db, event_id, key, params, user_id=current_user.id, scenario=scenario)
    # Recalculamos el contexto de renderizado con los parámetros recién guardados
    ctx = _module_context(db, event_id, key, params, scenario)
    # Renderizamos el partial actualizado
    return templates.TemplateResponse(request, "ops/partials/engineering_module.html", {"request": request, **ctx})


@router.post("/events/{event_id}/engineering/{key}/scenario", response_class=HTMLResponse)
async def engineering_scenario(request: Request, event_id: str, key: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    """Save-as a new design scenario (copies the current inputs) or delete one."""
    # Verificamos que el módulo pedido exista y que el evento exista
    if key not in MODULES or EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    # Leemos el form enviado
    form = await request.form()
    action = form.get("_action")
    # Si la acción es borrar, eliminamos el escenario indicado y volvemos al escenario por defecto
    if action == "delete":
        target = (form.get("_scenario") or "").strip()
        delete_scenario(db, event_id, key, target)
        scenario = DEFAULT_SCENARIO
    else:  # save-as: clone current inputs under a new name
        # save-as: clonamos los parámetros actuales bajo un nuevo nombre de escenario
        src = (form.get("_scenario") or DEFAULT_SCENARIO).strip()
        new_name = (form.get("_new_scenario") or "").strip()
        # Si nos dieron un nombre nuevo lo usamos, si no seguimos en el escenario origen
        scenario = new_name or src
        if new_name:
            # Guardamos los parámetros del escenario origen bajo el nuevo nombre
            save_params(db, event_id, key, get_params(db, event_id, key, src), user_id=current_user.id, scenario=new_name)
    # Recalculamos el contexto de renderizado para el escenario resultante
    ctx = _module_context(db, event_id, key, get_params(db, event_id, key, scenario), scenario)
    # Renderizamos el partial actualizado
    return templates.TemplateResponse(request, "ops/partials/engineering_module.html", {"request": request, **ctx})


@router.get("/events/{event_id}/engineering/{key}/export.csv")
async def engineering_export(request: Request, event_id: str, key: str, scenario: str = DEFAULT_SCENARIO,
                             db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Verificamos que el módulo pedido exista y que el evento exista
    if key not in MODULES or EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    m = MODULES[key]
    # Cargamos el contexto necesario para recalcular el resultado a exportar
    ctx_load = load_context(db, event_id, with_offsets=(key == "directional"), with_benchmark=(key == "afe"))
    # Resolvemos los parámetros efectivos para ese escenario
    params = _effective_params(m, ctx_load, get_params(db, event_id, key, scenario))
    # Recalculamos el resultado del módulo
    res = m["svc"].compute(params, ctx_load)
    # Armamos el CSV en memoria
    buf = io.StringIO()
    writer = csv.writer(buf)
    # Escribimos cada fila que arma el exportador específico del módulo
    for row in module_csv_rows(key, m["title"], res, params, "ft"):
        writer.writerow(row)
    buf.seek(0)
    # Construimos el nombre de archivo a partir del módulo y el escenario
    fname = f"{key}_{scenario}".replace(" ", "_")
    # Devolvemos el CSV como descarga (streaming)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'})


@router.post("/events/{event_id}/engineering/{key}/apply", response_class=HTMLResponse)
async def engineering_apply(request: Request, event_id: str, key: str, target: str = "", scenario: str = DEFAULT_SCENARIO,
                            db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    """Generator modules write their computed output into a Planning program grid
    (design → program). Replaces the target grid's rows."""
    # Obtenemos el módulo (puede no existir) y su servicio asociado
    m = MODULES.get(key)
    svc = m["svc"] if m else None
    # Obtenemos las grillas de destino válidas que este módulo puede generar
    valid = getattr(svc, "PROGRAM_TARGETS", []) if svc else []
    # Verificamos que el target sea válido para este módulo, que la config del target exista y que el evento exista
    if target not in valid or target not in PLAN_CONFIG_BY_KEY or EventRepository(db).get(event_id) is None:
        raise HTTPException(404)
    ensure_plan_unlocked(db, event_id)  # don't overwrite an approved plan's program
    # Verificamos que el plan no esté aprobado/bloqueado antes de sobrescribir su programa
    # Cargamos el contexto completo para recalcular con los datos más recientes
    ctx_load = load_context(db, event_id)
    # Resolvemos los parámetros efectivos para ese escenario
    params = _effective_params(m, ctx_load, get_params(db, event_id, key, scenario))
    # Generamos las filas que el módulo va a escribir en la grilla de destino
    rows = svc.generate_rows(params, ctx_load, target)
    cfg = PLAN_CONFIG_BY_KEY[target]
    repo = GridRepository(db, cfg.model, parent_field="event_id")
    # Borramos las filas existentes de la grilla de destino antes de escribir las nuevas
    for existing in repo.list_for_parent(event_id):
        db.delete(existing)
    db.flush()
    # Insertamos cada fila generada, calculando sus valores derivados y registrando quién la creó
    for i, row in enumerate(rows):
        db.add(cfg.model(event_id=event_id, sort_order=i, **_compute_values(cfg, dict(row)), created_by=current_user.id))
    db.commit()
    # Recalculamos el contexto de renderizado del módulo tras aplicar los cambios
    ctx = _module_context(db, event_id, key, get_params(db, event_id, key, scenario), scenario)
    # Agregamos un mensaje flash indicando cuántas filas se aplicaron y a qué grilla
    ctx["applied_flash"] = f"Applied {len(rows)} rows to {cfg.title}."
    # Renderizamos el partial actualizado
    return templates.TemplateResponse(request, "ops/partials/engineering_module.html", {"request": request, **ctx})
