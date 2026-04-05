"""Repository for processed datasets and records."""
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select, delete, func, inspect

from app.core.logging import get_logger
from app.db.models import ProcessedDataset, ProcessedRecord

logger = get_logger(__name__)


class ProcessedDatasetRepository:
    """Data access layer for processed datasets."""

    def __init__(self, session: Session):
        self.session = session
        self._processed_record_columns = self._load_table_columns("processed_records")

    def _load_table_columns(self, table_name: str) -> set[str]:
        try:
            inspector = inspect(self.session.bind)
            return {col["name"] for col in inspector.get_columns(table_name)}
        except Exception:
            logger.exception("Unable to inspect columns for table %s", table_name)
            return set()

    # Dataset operations -------------------------------------------------
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
    ) -> ProcessedDataset:
        dataset = ProcessedDataset(
            well_id=well_id,
            name=name,
            description=description,
            pipeline_config=pipeline_config,
            metrics=metrics,
            status=status,
            created_by=created_by,
        )
        self.session.add(dataset)
        self.session.flush()  # obtain dataset.id before inserting records
        logger.info(
            "Created processed dataset %s for well %s (status=%s)",
            dataset.id,
            well_id,
            status,
        )
        return dataset

    def update_metrics(
        self,
        dataset: ProcessedDataset,
        *,
        metrics: Dict[str, Any],
        record_count: int,
        status: str = "completed",
    ) -> ProcessedDataset:
        dataset.metrics = metrics
        dataset.record_count = record_count
        dataset.status = status
        self.session.add(dataset)
        logger.info(
            "Updated metrics for dataset %s (records=%s)",
            dataset.id,
            record_count,
        )
        return dataset

    def set_status(self, dataset: ProcessedDataset, status: str) -> None:
        dataset.status = status
        self.session.add(dataset)
        logger.info("Dataset %s status -> %s", dataset.id, status)

    def get_by_id(self, dataset_id: int) -> Optional[ProcessedDataset]:
        stmt = select(ProcessedDataset).where(ProcessedDataset.id == dataset_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_well(self, well_id: int) -> List[ProcessedDataset]:
        stmt = (
            select(ProcessedDataset)
            .where(ProcessedDataset.well_id == well_id)
            .order_by(ProcessedDataset.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_all(self) -> List[ProcessedDataset]:
        stmt = select(ProcessedDataset).order_by(ProcessedDataset.created_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    def delete_dataset(self, dataset_id: int) -> int:
        stmt = delete(ProcessedDataset).where(ProcessedDataset.id == dataset_id)
        result = self.session.execute(stmt)
        logger.info("Deleted dataset %s (rows=%s)", dataset_id, result.rowcount)
        return result.rowcount or 0

    # Record operations --------------------------------------------------
    def add_records(
        self,
        dataset_id: int,
        records: Sequence[Dict[str, Any]],
    ) -> int:
        if not records:
            return 0
        has_scaled = "scaled_data" in self._processed_record_columns
        has_components = "component_scores" in self._processed_record_columns

        objects = []
        for record in records:
            payload: Dict[str, Any] = {
                "dataset_id": dataset_id,
                "source_record_id": record.get("source_record_id"),
                "data": record["data"],
                "is_outlier": record.get("is_outlier", False),
            }
            if has_scaled:
                payload["scaled_data"] = record.get("scaled")
            if has_components:
                payload["component_scores"] = record.get("components")
            objects.append(ProcessedRecord(**payload))
        self.session.bulk_save_objects(objects)
        logger.info("Inserted %s processed records for dataset %s", len(objects), dataset_id)
        return len(objects)

    def delete_records(self, dataset_id: int) -> int:
        stmt = delete(ProcessedRecord).where(ProcessedRecord.dataset_id == dataset_id)
        result = self.session.execute(stmt)
        logger.info("Deleted %s records for dataset %s", result.rowcount, dataset_id)
        return result.rowcount or 0

    def list_records(
        self,
        dataset_id: int,
        *,
        include_outliers: bool = True,
        page: int = 1,
        page_size: int = 500,
    ) -> List[ProcessedRecord]:
        stmt = (
            select(ProcessedRecord)
            .where(ProcessedRecord.dataset_id == dataset_id)
            .order_by(ProcessedRecord.id)
        )
        if not include_outliers:
            stmt = stmt.where(ProcessedRecord.is_outlier.is_(False))
        if page < 1:
            page = 1
        if page_size <= 0:
            page_size = 500
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
        return list(self.session.execute(stmt).scalars().all())

    def count_records(
        self,
        dataset_id: int,
        *,
        include_outliers: bool = True,
    ) -> int:
        stmt = select(func.count(ProcessedRecord.id)).where(ProcessedRecord.dataset_id == dataset_id)
        if not include_outliers:
            stmt = stmt.where(ProcessedRecord.is_outlier.is_(False))
        return self.session.execute(stmt).scalar_one()
