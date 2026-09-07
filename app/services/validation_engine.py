"""Per-report-type field validation, mirroring OpenWells' mandatory-vs-notify
distinction: mandatory violations block saving the subsection, notify
violations are surfaced but don't.

The field-level rules are now DB-backed and admin-editable (ops_validation_rules,
seeded from DEFAULT_GENERAL_RULES). On top of them the engine runs a few
report-level cross-field checks that need more than the submitted form
(MD monotonic vs the previous day, TVD ≤ MD, Time-Summary hours ≈ 24)."""
# Importamos dataclass para tipar cada violación de validación
from dataclasses import dataclass
# Importamos Any y Optional para tipar los datos genéricos del formulario y los retornos opcionales
from typing import Any, Optional

# Importamos select para construir la consulta de las reglas de validación
from sqlalchemy import select
# Importamos Session para tipar la sesión de base de datos recibida
from sqlalchemy.orm import Session

# Importamos ValidationRule, el modelo DB-backed de reglas de validación
from app.models.validation import ValidationRule
# Importamos TimeSummaryRowRepository para leer las filas del Time Summary de un reporte
# (movido al tope del archivo: no hay import circular, time_summary_repository no importa validation_engine)
from app.repositories.time_summary_repository import TimeSummaryRowRepository


# Definimos la estructura de una violación de validación (campo, nivel, mensaje)
@dataclass
class Violation:
    field: str
    level: str  # "mandatory" | "notify"
    message: str


# Seed defaults for a fresh ops_validation_rules table (report_type="general").
# (field_name, level, check, param1, param2, field_name2, message)
# Listamos las reglas semilla que se cargan en una tabla ops_validation_rules recién creada
DEFAULT_GENERAL_RULES = [
    ("dol", "mandatory", "required", None, None, None, "DOL (Days on Location) is required."),
    ("dfs", "mandatory", "required", None, None, None, "DFS (Days From Spud) is required."),
    ("md", "mandatory", "nonzero", None, None, None, "MD is required and must never be 0."),
    ("rotating_hrs", "notify", "both_blank_notify", None, None, "sliding_hrs", "No rotating or sliding hours have been entered."),
    ("current_status", "notify", "required", None, None, None, "Current Status of the operation is missing."),
]


def _blank(v) -> bool:
    # Consideramos "en blanco" tanto None como cadena vacía
    return v in (None, "")


def _num(v) -> Optional[float]:
    try:
        # Convertimos a float si el valor no está en blanco
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        # Si no se puede convertir, tratamos el valor como ausente
        return None


def _rule_violated(rule: ValidationRule, data: dict[str, Any]) -> bool:
    # Leemos el valor del campo que la regla evalúa
    v = data.get(rule.field_name)
    check = rule.check
    if check == "required":
        # La regla se viola si el campo está en blanco
        return _blank(v)
    if check == "nonzero":
        # La regla se viola si el campo está en blanco o vale cero
        n = _num(v)
        return n is None or n == 0
    if check == "both_blank_notify":
        # La regla se viola si tanto este campo como el campo relacionado están en blanco
        return _blank(v) and _blank(data.get(rule.field_name2))
    n = _num(v)
    if check == "gt":
        # La regla se viola si el valor es menor o igual al parámetro (debe ser mayor)
        return n is not None and rule.param1 is not None and n <= float(rule.param1)
    if check == "lt":
        # La regla se viola si el valor es mayor o igual al parámetro (debe ser menor)
        return n is not None and rule.param1 is not None and n >= float(rule.param1)
    if check == "range":
        if n is None:
            return False
        # Calculamos los límites inferior y superior del rango permitido
        lo = float(rule.param1) if rule.param1 is not None else None
        hi = float(rule.param2) if rule.param2 is not None else None
        # La regla se viola si el valor cae fuera del rango
        return (lo is not None and n < lo) or (hi is not None and n > hi)
    # Si el tipo de chequeo no es reconocido, no marcamos violación
    return False


def validate_general(db: Session, data: dict[str, Any], report=None) -> list[Violation]:
    # Traemos las reglas activas del tipo "general", ordenadas por su orden de despliegue
    rules = db.execute(
        select(ValidationRule).where(ValidationRule.report_type == "general", ValidationRule.is_active == True)  # noqa: E712
        .order_by(ValidationRule.sort_order)
    ).scalars().all()
    # Evaluamos cada regla contra los datos enviados y armamos la lista de violaciones
    violations = [Violation(r.field_name, r.level, r.message) for r in rules if _rule_violated(r, data)]

    # --- cross-field / report-level checks ---
    md = _num(data.get("md"))
    tvd = _num(data.get("tvd"))
    prev_md = _num(data.get("previous_md"))
    # Verificamos que el TVD no supere el MD (con una tolerancia de redondeo)
    if md is not None and tvd is not None and tvd > md + 0.01:
        violations.append(Violation("tvd", "notify", "TVD should not be greater than MD."))
    # Verificamos que el MD no retroceda respecto al día anterior
    if md is not None and prev_md is not None and md < prev_md - 0.01:
        violations.append(Violation("md", "notify", "MD is less than the previous day's depth (previous MD)."))

    if report is not None:
        # Sumamos las horas del Time Summary del reporte y avisamos si no cuadran cerca de 24h
        ts_total = _time_summary_hours(db, report.id)
        if ts_total is not None and abs(ts_total - 24.0) > 0.5:
            violations.append(Violation("md", "notify", f"Time Summary hours add up to {ts_total:.1f} h (~24 h expected)."))
    # Devolvemos todas las violaciones encontradas (reglas DB-backed + chequeos cruzados)
    return violations


def _time_summary_hours(db: Session, report_id) -> Optional[float]:
    # Traemos las filas del Time Summary del reporte
    rows = TimeSummaryRowRepository(db).list_for_report(report_id)
    if not rows:
        # Sin filas no hay total que calcular
        return None
    total = 0.0
    for r in rows:
        # Ignoramos filas sin hora de inicio o de fin
        if not r.time_from or not r.time_to:
            continue
        try:
            # Parseamos las horas y minutos de inicio y fin
            h1, m1 = (int(x) for x in r.time_from.split(":"))
            h2, m2 = (int(x) for x in r.time_to.split(":"))
        except ValueError:
            # Si el formato de hora no es válido, ignoramos la fila
            continue
        mins = (h2 * 60 + m2) - (h1 * 60 + m1)
        if mins < 0:
            # Si el fin cae antes que el inicio, asumimos que cruzó medianoche
            mins += 24 * 60
        total += mins / 60.0
    # Devolvemos el total de horas acumuladas del Time Summary
    return total


def has_mandatory(violations: list[Violation]) -> bool:
    # Indicamos si alguna violación de la lista es de nivel mandatorio
    return any(v.level == "mandatory" for v in violations)
