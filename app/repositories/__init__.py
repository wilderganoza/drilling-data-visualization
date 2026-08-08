# Archivo de inicialización del paquete de repositorios
# Este paquete contiene repositorios para acceso a datos (well_repository, data_repository)

# Importamos los repositorios que exponemos como parte pública del paquete
from .base import BaseRepository
from .well_repository import WellRepository
from .data_repository import DataRepository
from .processed_dataset_repository import ProcessedDatasetRepository
from .capture_repository import GridRepository
from .daily_report_repository import DailyReportRepository
from .npt_repository import NptRepository
from .planning_repository import WellPlanRepository
from .time_summary_repository import StepCatalogRepository, TimeSummaryRowRepository
# Importamos los repositorios de jerarquía; "as OpsWellRepository" evita chocar con el
# WellRepository legacy (well_repository.py) importado arriba — son dos clases distintas
# sobre dos modelos distintos (pozo legacy de sensores vs. pozo operacional/de planeación).
from .hierarchy_repository import (
    CompanyRepository,
    ProjectRepository,
    SiteRepository,
    WellRepository as OpsWellRepository,
    WellboreRepository,
    EventRepository,
)

# Exponemos estos repositorios como lo público del paquete
__all__ = [
    "BaseRepository",
    "WellRepository",
    "DataRepository",
    "ProcessedDatasetRepository",
    "GridRepository",
    "DailyReportRepository",
    "NptRepository",
    "WellPlanRepository",
    "StepCatalogRepository",
    "TimeSummaryRowRepository",
    "CompanyRepository",
    "ProjectRepository",
    "SiteRepository",
    "OpsWellRepository",
    "WellboreRepository",
    "EventRepository",
]
