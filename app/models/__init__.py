"""Import every model module so OpsBase.metadata is fully populated for
create-time table registration and for regenerating the baseline DDL."""
# Importamos OpsBase, la base declarativa que comparten todos los modelos de Ops
from app.models.base import OpsBase
# Importamos cada submódulo de modelos para que sus clases se registren en OpsBase.metadata
from app.models import attachment, capture, daily_report, engineering, hierarchy, npt, planning, planning_capture, realtime, registers, roles, time_summary, validation  # noqa: F401

# Exponemos OpsBase como lo único público de este paquete
__all__ = ["OpsBase"]
