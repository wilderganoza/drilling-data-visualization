"""Repository for processed datasets and records."""
# Importamos los tipos que usamos para tipar los métodos
from typing import Any, Dict, List, Optional, Sequence

# Importamos Session para tipar la sesión de SQLAlchemy
from sqlalchemy.orm import Session
# Importamos select/delete/func/inspect para construir las consultas e inspeccionar columnas
from sqlalchemy import select, delete, func, inspect

# Importamos get_logger para registrar la actividad del repositorio
from app.core.logging import get_logger
# Importamos los modelos sobre los que opera este repositorio
from app.models.legacy import ProcessedDataset, ProcessedRecord

# Creamos el logger de este módulo
logger = get_logger(__name__)


# Definimos el repositorio de datasets procesados y sus registros
class ProcessedDatasetRepository:
    """Data access layer for processed datasets."""

    # Inicializamos el repositorio con la sesión de base de datos a usar
    def __init__(self, session: Session):
        # Guardamos la sesión para todas las operaciones del repositorio
        self.session = session
        # Cargamos las columnas reales de processed_records para saber qué campos opcionales existen
        self._processed_record_columns = self._load_table_columns("processed_records")

    # Inspeccionamos las columnas reales de una tabla en la base de datos
    def _load_table_columns(self, table_name: str) -> set[str]:
        # Intentamos inspeccionar la tabla; si falla, seguimos sin romper el repositorio
        try:
            inspector = inspect(self.session.bind)
            return {col["name"] for col in inspector.get_columns(table_name)}
        except Exception:
            # Registramos el error y devolvemos un set vacío para degradar sin romper
            logger.exception("Unable to inspect columns for table %s", table_name)
            return set()

    # Dataset operations -------------------------------------------------
    # Creamos un nuevo dataset procesado
    def create_dataset(
        self,
        *,
        well_id: int,
        name: str,
        description: Optional[str],
        pipeline_config: Dict[str, Any],
        metrics: Optional[Dict[str, Any]],
        created_by: Optional[int],
        status: str = "completed",
        domain: str = "depth",
    ) -> ProcessedDataset:
        # Construimos la instancia del dataset con los valores recibidos
        dataset = ProcessedDataset(
            well_id=well_id,
            domain=domain if domain == "time" else "depth",
            name=name,
            description=description,
            pipeline_config=pipeline_config,
            metrics=metrics,
            status=status,
            created_by=created_by,
        )
        # Agregamos el dataset a la sesión
        self.session.add(dataset)
        # Enviamos el insert para obtener dataset.id antes de insertar sus registros
        self.session.flush()  # obtain dataset.id before inserting records
        # Registramos la creación del dataset
        logger.info(
            "Created processed dataset %s for well %s (status=%s)",
            dataset.id,
            well_id,
            status,
        )
        # Devolvemos el dataset creado
        return dataset

    # Actualizamos las métricas y el conteo de registros de un dataset
    def update_metrics(
        self,
        dataset: ProcessedDataset,
        *,
        metrics: Dict[str, Any],
        record_count: int,
        status: str = "completed",
    ) -> ProcessedDataset:
        # Asignamos las métricas nuevas
        dataset.metrics = metrics
        # Asignamos el conteo de registros
        dataset.record_count = record_count
        # Asignamos el estado
        dataset.status = status
        # Agregamos el dataset a la sesión (por si venía detached)
        self.session.add(dataset)
        # Registramos la actualización de métricas
        logger.info(
            "Updated metrics for dataset %s (records=%s)",
            dataset.id,
            record_count,
        )
        # Devolvemos el dataset actualizado
        return dataset

    # Cambiamos el estado de un dataset
    def set_status(self, dataset: ProcessedDataset, status: str) -> None:
        # Asignamos el nuevo estado
        dataset.status = status
        # Agregamos el dataset a la sesión (por si venía detached)
        self.session.add(dataset)
        # Registramos el cambio de estado
        logger.info("Dataset %s status -> %s", dataset.id, status)

    # Buscamos un dataset por su id
    def get_by_id(self, dataset_id: int) -> Optional[ProcessedDataset]:
        # Armamos y ejecutamos el select por id
        stmt = select(ProcessedDataset).where(ProcessedDataset.id == dataset_id)
        return self.session.execute(stmt).scalar_one_or_none()

    # Listamos los datasets de un pozo, del más reciente al más antiguo
    def list_by_well(self, well_id: int) -> List[ProcessedDataset]:
        # Armamos el select filtrado por pozo y ordenado por fecha de creación descendente
        stmt = (
            select(ProcessedDataset)
            .where(ProcessedDataset.well_id == well_id)
            .order_by(ProcessedDataset.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    # Listamos todos los datasets, del más reciente al más antiguo
    def list_all(self) -> List[ProcessedDataset]:
        # Armamos el select ordenado por fecha de creación descendente
        stmt = select(ProcessedDataset).order_by(ProcessedDataset.created_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    # Borramos un dataset por su id
    def delete_dataset(self, dataset_id: int) -> int:
        # Armamos y ejecutamos el delete por id
        stmt = delete(ProcessedDataset).where(ProcessedDataset.id == dataset_id)
        result = self.session.execute(stmt)
        # Registramos cuántas filas se borraron
        logger.info("Deleted dataset %s (rows=%s)", dataset_id, result.rowcount)
        # Devolvemos el número de filas borradas
        return result.rowcount or 0

    # Record operations --------------------------------------------------
    # Insertamos en bloque los registros procesados de un dataset
    def add_records(
        self,
        dataset_id: int,
        records: Sequence[Dict[str, Any]],
    ) -> int:
        # Salimos temprano si no hay registros que insertar
        if not records:
            return 0
        # Verificamos si la tabla real tiene las columnas opcionales de escalado/componentes
        has_scaled = "scaled_data" in self._processed_record_columns
        has_components = "component_scores" in self._processed_record_columns

        # Armamos la lista de objetos ProcessedRecord a insertar
        objects = []
        for record in records:
            # Construimos el payload base de cada registro
            payload: Dict[str, Any] = {
                "dataset_id": dataset_id,
                "source_record_id": record.get("source_record_id"),
                "data": record["data"],
                "is_outlier": record.get("is_outlier", False),
            }
            # Agregamos los datos escalados solo si la tabla real tiene esa columna
            if has_scaled:
                payload["scaled_data"] = record.get("scaled")
            # Agregamos los puntajes de componentes solo si la tabla real tiene esa columna
            if has_components:
                payload["component_scores"] = record.get("components")
            objects.append(ProcessedRecord(**payload))
        # Insertamos todos los objetos en bloque (más rápido que uno por uno)
        self.session.bulk_save_objects(objects)
        # Registramos cuántos registros se insertaron
        logger.info("Inserted %s processed records for dataset %s", len(objects), dataset_id)
        # Devolvemos el número de registros insertados
        return len(objects)

    # Borramos todos los registros de un dataset
    def delete_records(self, dataset_id: int) -> int:
        # Armamos y ejecutamos el delete por dataset
        stmt = delete(ProcessedRecord).where(ProcessedRecord.dataset_id == dataset_id)
        result = self.session.execute(stmt)
        # Registramos cuántas filas se borraron
        logger.info("Deleted %s records for dataset %s", result.rowcount, dataset_id)
        # Devolvemos el número de filas borradas
        return result.rowcount or 0

    # Listamos los registros de un dataset, paginados
    def list_records(
        self,
        dataset_id: int,
        *,
        include_outliers: bool = True,
        page: int = 1,
        page_size: int = 500,
    ) -> List[ProcessedRecord]:
        # Armamos el select filtrado por dataset y ordenado por id
        stmt = (
            select(ProcessedRecord)
            .where(ProcessedRecord.dataset_id == dataset_id)
            .order_by(ProcessedRecord.id)
        )
        # Excluimos los outliers si no se pidieron
        if not include_outliers:
            stmt = stmt.where(ProcessedRecord.is_outlier.is_(False))
        # Normalizamos la página a un mínimo de 1
        if page < 1:
            page = 1
        # Normalizamos el tamaño de página a un valor por defecto si viene inválido
        if page_size <= 0:
            page_size = 500
        # Aplicamos la paginación
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
        return list(self.session.execute(stmt).scalars().all())

    # Contamos los registros de un dataset
    def count_records(
        self,
        dataset_id: int,
        *,
        include_outliers: bool = True,
    ) -> int:
        # Armamos el select de conteo filtrado por dataset
        stmt = select(func.count(ProcessedRecord.id)).where(ProcessedRecord.dataset_id == dataset_id)
        # Excluimos los outliers si no se pidieron
        if not include_outliers:
            stmt = stmt.where(ProcessedRecord.is_outlier.is_(False))
        return self.session.execute(stmt).scalar_one()
