"""Admin-configurable validation rules. Replaces the code-defined GENERAL_RULES
as the source of truth for field checks on the Daily Report General subsection
(seeded from those defaults). `check` names a small fixed set of predicates the
engine knows how to evaluate — not a free expression language."""
# Importamos los tipos de columna que usamos en la tabla
from sqlalchemy import Boolean, Column, Integer, Numeric, String
# Importamos OpsBase, la base declarativa
from app.models.base import OpsBase
# Importamos AuditMixin para heredar los campos de auditoría
from app.models.mixins import AuditMixin

# Definimos el modelo de una regla de validación configurable
class ValidationRule(OpsBase, AuditMixin):
    # Nombramos la tabla
    __tablename__ = "validation_rules"

    # Guardamos a qué tipo de reporte aplica la regla
    report_type = Column(String(50), nullable=False, default="general", index=True)

    # Guardamos el nombre del campo que valida la regla
    field_name = Column(String(80), nullable=False)

    # Guardamos el nivel de la regla: mandatory (bloquea) o notify (solo avisa)
    level = Column(String(20), nullable=False, default="mandatory")

    # Guardamos qué predicado evalúa el motor de validación
    check = Column(String(40), nullable=False, default="required")

    # Guardamos el primer parámetro numérico del check (ej. el límite en gt/lt)
    param1 = Column(Numeric(16, 4), nullable=True)

    # Guardamos el segundo parámetro numérico del check (ej. el límite superior en range)
    param2 = Column(Numeric(16, 4), nullable=True)

    # Guardamos un segundo campo para checks que comparan dos campos entre sí
    field_name2 = Column(String(80), nullable=True)

    # Guardamos el mensaje que se muestra cuando la regla falla
    message = Column(String(300), nullable=False)

    # Guardamos si la regla está activa
    is_active = Column(Boolean, default=True, nullable=False)

    # Guardamos el orden en que se muestra/evalúa la regla
    sort_order = Column(Integer, default=0, nullable=False)
