"""Outlier detection service that orchestrates scaling, PCA and anomaly removal."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Table

from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import (
    MaxAbsScaler,
    MinMaxScaler,
    RobustScaler,
    StandardScaler,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import ProcessedDataset
from app.db.repositories.data_repository import DataRepository
from app.db.repositories.processed_dataset_repository import ProcessedDatasetRepository
from app.schemas.outliers import (
    OutlierConfig,
    OutlierDetectionRequest,
    OutlierDetectionResponse,
    OutlierMethod,
    PCAConfig,
    PipelineMetrics,
    ProcessedDataResponse,
    ProcessedDatasetDetail,
    ProcessedDatasetSummary,
    ProcessedRecordData,
    ScalingConfig,
    ScalingMethod,
)

logger = get_logger(__name__)


class OutlierDetectionError(Exception):
    """Raised when pipeline execution fails."""


class OutlierDetectionService:
    """Encapsulates the outlier detection workflow and persistence."""

    def __init__(self, session: Session, well_data_table: Table):
        self.session = session
        self.well_data_table = well_data_table
        self.data_repo = DataRepository(session, well_data_table)
        self.datasets_repo = ProcessedDatasetRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_pipeline(
        self,
        request: OutlierDetectionRequest,
        *,
        created_by: Optional[int] = None,
        replace_dataset_id: Optional[int] = None,
    ) -> OutlierDetectionResponse:
        """Execute the pipeline and persist results.

        When ``replace_dataset_id`` is provided, the existing dataset is
        updated in place (records replaced, config/metrics overwritten).
        """
        logger.info(
            "Running outlier detection: well_id=%s, variables=%s, method=%s",
            request.well_id,
            request.variables,
            request.outlier.method,
        )

        raw_records = self._fetch_raw_data(request)
        if not raw_records:
            raise OutlierDetectionError("No data available for the selected well")

        df = pd.DataFrame(raw_records)
        available_columns = set(df.columns)
        missing = [col for col in request.variables if col not in available_columns]
        if missing:
            raise OutlierDetectionError(
                f"Variables not found in dataset: {', '.join(missing)}"
            )

        include_columns = request.include_columns or []
        include_missing = [col for col in include_columns if col not in available_columns]
        if include_missing:
            raise OutlierDetectionError(
                f"Included columns not found in dataset: {', '.join(include_missing)}"
            )

        numeric_df = self._prepare_numeric_dataframe(df, request.variables)
        total_records = len(df)
        numeric_records = len(numeric_df)
        dropped_due_to_nan = total_records - numeric_records
        if numeric_records == 0:
            raise OutlierDetectionError("All selected variables contain non-numeric data")

        scaled_array = self._apply_scaling(numeric_df.values, request.scaling)
        (
            feature_array,
            feature_labels,
            explained_variance,
            explained_variance_ratio,
        ) = self._apply_pca(scaled_array, request.pca, request.variables)
        outlier_mask = self._detect_outliers(feature_array, request.outlier)

        outlier_count = int(outlier_mask.sum())
        inlier_mask = ~outlier_mask
        inlier_count = int(inlier_mask.sum())
        if inlier_count == 0:
            raise OutlierDetectionError("Pipeline flagged all rows as outliers")

        dataset_name = request.dataset_name or self._generate_dataset_name(request)

        pipeline_config = {
            "variables": request.variables,
            "scaling": request.scaling.model_dump(),
            "pca": request.pca.model_dump(),
            "outlier": request.outlier.model_dump(),
            "max_records": request.max_records,
            "include_columns": include_columns,
        }

        if replace_dataset_id is not None:
            existing = self.datasets_repo.get_by_id(replace_dataset_id)
            if existing is None:
                raise OutlierDetectionError(
                    f"Dataset {replace_dataset_id} not found for replacement"
                )
            try:
                # Evict the dataset from the session so the delete-orphan
                # cascade on its records relationship cannot fire when we
                # subsequently modify the row via bulk SQL.
                self.session.expunge(existing)
                self.datasets_repo.delete_records(replace_dataset_id)
                self.session.execute(
                    sa_update(ProcessedDataset)
                    .where(ProcessedDataset.id == replace_dataset_id)
                    .values(
                        well_id=request.well_id,
                        name=dataset_name,
                        description=request.description,
                        pipeline_config=pipeline_config,
                        metrics=None,
                        record_count=None,
                        status="processing",
                        updated_at=datetime.utcnow(),
                    )
                )
                self.session.flush()
                dataset = self.datasets_repo.get_by_id(replace_dataset_id)
                if dataset is None:
                    raise OutlierDetectionError(
                        f"Dataset {replace_dataset_id} vanished during replacement"
                    )
            except OutlierDetectionError:
                raise
            except Exception as exc:
                self.session.rollback()
                logger.exception("Failed to prepare dataset for replacement")
                raise OutlierDetectionError(
                    f"Failed to replace dataset {replace_dataset_id}: {exc}"
                ) from exc
        else:
            dataset = self.datasets_repo.create_dataset(
                well_id=request.well_id,
                name=dataset_name,
                description=request.description,
                pipeline_config=pipeline_config,
                metrics=None,
                created_by=created_by,
                status="processing",
            )

        try:
            storage_columns = list(dict.fromkeys(request.variables + include_columns))
            records_payload = self._build_records_payload(
                df.loc[numeric_df.index],
                storage_columns,
                outlier_mask=outlier_mask,
                include_outliers=request.outlier.mark_outliers,
                scaled_array=scaled_array,
                scaled_labels=list(numeric_df.columns),
                component_array=feature_array if request.pca.enabled else None,
                component_labels=feature_labels if request.pca.enabled else None,
            )

            inserted = self.datasets_repo.add_records(dataset.id, records_payload)

            metrics = PipelineMetrics(
                total_records=total_records,
                processed_records=inlier_count,
                outlier_records=outlier_count,
                outlier_percentage=(outlier_count / total_records * 100) if total_records else 0.0,
                variables=request.variables,
                dropped_records=dropped_due_to_nan,
                scaled_feature_labels=list(numeric_df.columns),
                pca_component_labels=feature_labels if request.pca.enabled else None,
                explained_variance=explained_variance,
                explained_variance_ratio=explained_variance_ratio,
            )

            self.datasets_repo.update_metrics(
                dataset,
                metrics=metrics.model_dump(),
                record_count=inlier_count if not request.outlier.mark_outliers else inserted,
                status="completed",
            )
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.exception("Failed to persist processed dataset")
            raise OutlierDetectionError(f"Failed to persist processed dataset: {exc}") from exc

        refreshed_dataset = self.datasets_repo.get_by_id(dataset.id)
        if refreshed_dataset is None:
            raise OutlierDetectionError("Failed to load processed dataset after saving")

        detail = self._to_detail(refreshed_dataset)
        return OutlierDetectionResponse(dataset=detail)

    def list_datasets(self, well_id: int) -> List[ProcessedDatasetSummary]:
        datasets = self.datasets_repo.list_by_well(well_id)
        return [self._to_summary(ds) for ds in datasets]

    def list_all_datasets(self) -> List[ProcessedDatasetSummary]:
        datasets = self.datasets_repo.list_all()
        return [self._to_summary(ds) for ds in datasets]

    def get_dataset(self, dataset_id: int) -> Optional[ProcessedDatasetDetail]:
        dataset = self.datasets_repo.get_by_id(dataset_id)
        if not dataset:
            return None
        return self._to_detail(dataset)

    def get_dataset_data(
        self,
        dataset_id: int,
        *,
        include_outliers: bool,
        page: int,
        page_size: int,
    ) -> ProcessedDataResponse:
        total_records = self.datasets_repo.count_records(
            dataset_id,
            include_outliers=include_outliers,
        )
        records = self.datasets_repo.list_records(
            dataset_id,
            include_outliers=include_outliers,
            page=page,
            page_size=page_size,
        )
        payload = [
            ProcessedRecordData(
                source_record_id=record.source_record_id,
                is_outlier=record.is_outlier,
                data=record.data or {},
                scaled=record.scaled_data or None,
                components=record.component_scores or None,
            )
            for record in records
        ]
        return ProcessedDataResponse(
            dataset_id=dataset_id,
            include_outliers=include_outliers,
            total_records=total_records,
            page=page,
            page_size=page_size,
            records=payload,
        )

    def delete_dataset(self, dataset_id: int) -> bool:
        deleted_rows = self.datasets_repo.delete_dataset(dataset_id)
        if deleted_rows:
            self.session.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fetch_raw_data(self, request: OutlierDetectionRequest) -> List[Dict[str, Any]]:
        limit = request.max_records or settings.DEFAULT_QUERY_LIMIT
        limit = min(limit, settings.MAX_QUERY_LIMIT)
        return self.data_repo.query_sample(request.well_id, sample_size=limit)

    def _prepare_numeric_dataframe(self, df: pd.DataFrame, variables: Sequence[str]) -> pd.DataFrame:
        numeric_df = df[list(variables)].apply(pd.to_numeric, errors="coerce")
        valid_mask = numeric_df.notna().all(axis=1)
        numeric_df = numeric_df.loc[valid_mask]
        return numeric_df

    def _apply_scaling(self, values: np.ndarray, config: ScalingConfig) -> np.ndarray:
        if config.method == ScalingMethod.none:
            return values

        scaler: Any
        params = {**config.params}
        if config.method == ScalingMethod.standard:
            scaler = StandardScaler(**params)
        elif config.method == ScalingMethod.minmax:
            scaler = MinMaxScaler(**params)
        elif config.method == ScalingMethod.robust:
            scaler = RobustScaler(**params)
        elif config.method == ScalingMethod.maxabs:
            scaler = MaxAbsScaler(**params)
        else:
            raise OutlierDetectionError(f"Unsupported scaling method: {config.method}")

        return scaler.fit_transform(values)

    def _apply_pca(
        self,
        values: np.ndarray,
        config: PCAConfig,
        variable_labels: Sequence[str],
    ) -> Tuple[np.ndarray, List[str], Optional[List[float]], Optional[List[float]]]:
        if not config.enabled:
            return values, list(variable_labels), None, None

        params = {
            "n_components": config.n_components,
            "whiten": config.whiten,
            "svd_solver": config.svd_solver,
        }
        params = {k: v for k, v in params.items() if v is not None}

        try:
            pca = PCA(**params)
            transformed = pca.fit_transform(values)
        except Exception as exc:
            raise OutlierDetectionError(f"PCA failed: {exc}") from exc

        component_labels = [f"PC{i+1}" for i in range(transformed.shape[1])]
        explained_variance = (
            pca.explained_variance_.tolist() if hasattr(pca, "explained_variance_") else None
        )
        explained_ratio = (
            pca.explained_variance_ratio_.tolist() if hasattr(pca, "explained_variance_ratio_") else None
        )
        return transformed, component_labels, explained_variance, explained_ratio

    def _detect_outliers(self, values: np.ndarray, config: OutlierConfig) -> np.ndarray:
        method = config.method
        params = {**config.params}

        if method == OutlierMethod.isolation_forest:
            contamination = params.pop("contamination", 0.05)
            model = IsolationForest(contamination=contamination, random_state=42, **params)
            predictions = model.fit_predict(values)
            return predictions == -1

        if method == OutlierMethod.dbscan:
            eps = params.pop("eps", 0.5)
            min_samples = params.pop("min_samples", 5)
            model = DBSCAN(eps=eps, min_samples=min_samples, **params)
            labels = model.fit_predict(values)
            return labels == -1

        if method == OutlierMethod.local_outlier_factor:
            n_neighbors = params.pop("n_neighbors", 20)
            lof = LocalOutlierFactor(n_neighbors=n_neighbors, novelty=False, **params)
            labels = lof.fit_predict(values)
            return labels == -1

        if method == OutlierMethod.zscore:
            threshold = float(params.pop("threshold", 3.0))
            z_scores = np.abs(stats.zscore(values, axis=0, nan_policy="omit"))
            z_scores = np.nan_to_num(z_scores)
            return (z_scores > threshold).any(axis=1)

        if method == OutlierMethod.iqr:
            multiplier = float(params.pop("multiplier", 1.5))
            q1 = np.percentile(values, 25, axis=0)
            q3 = np.percentile(values, 75, axis=0)
            iqr = q3 - q1
            lower_bound = q1 - multiplier * iqr
            upper_bound = q3 + multiplier * iqr
            mask = ((values < lower_bound) | (values > upper_bound)).any(axis=1)
            return mask

        raise OutlierDetectionError(f"Unsupported outlier method: {method}")

    def _build_records_payload(
        self,
        df: pd.DataFrame,
        columns: Iterable[str],
        *,
        outlier_mask: np.ndarray,
        include_outliers: bool,
        scaled_array: Optional[np.ndarray] = None,
        scaled_labels: Optional[Sequence[str]] = None,
        component_array: Optional[np.ndarray] = None,
        component_labels: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        store_columns = [col for col in columns if col in df.columns]
        records: List[Dict[str, Any]] = []

        ids = df["id"].tolist() if "id" in df.columns else [None] * len(df)

        for idx, (row_index, row) in enumerate(df.iterrows()):
            is_outlier = bool(outlier_mask[idx])
            if is_outlier and not include_outliers:
                continue

            record_data: Dict[str, Any] = {}
            for column in store_columns:
                if column not in row:
                    continue
                raw_value = row[column]
                if pd.isna(raw_value):
                    continue
                native_value = self._to_native(raw_value)
                if native_value is not None:
                    record_data[column] = native_value

            scaled_payload: Optional[Dict[str, Any]] = None
            if scaled_array is not None and scaled_labels is not None:
                scaled_row = scaled_array[idx]
                scaled_payload = {
                    label: self._to_native(scaled_row[col_idx])
                    for col_idx, label in enumerate(scaled_labels)
                }

            components_payload: Optional[Dict[str, Any]] = None
            if component_array is not None and component_labels is not None:
                component_row = component_array[idx]
                components_payload = {
                    label: self._to_native(component_row[col_idx])
                    for col_idx, label in enumerate(component_labels)
                }

            source_record_id: Optional[int] = None
            try:
                raw_id = ids[idx]
                if raw_id is not None and not pd.isna(raw_id):
                    source_record_id = int(raw_id)
            except (TypeError, ValueError):
                source_record_id = None

            record_payload = {
                "source_record_id": source_record_id,
                "data": record_data,
                "is_outlier": is_outlier,
                "scaled": scaled_payload,
                "components": components_payload,
            }
            records.append(record_payload)

        return records

    @staticmethod
    def _to_native(value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, (np.generic,)):  # numpy scalar
            return OutlierDetectionService._to_native(value.item())

        if isinstance(value, np.ndarray):
            return [OutlierDetectionService._to_native(item) for item in value.tolist()]

        if isinstance(value, dict):
            return {
                str(key): OutlierDetectionService._to_native(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [OutlierDetectionService._to_native(item) for item in value]

        if isinstance(value, float):
            if np.isnan(value) or np.isinf(value):
                return None
            return value

        if isinstance(value, (datetime, date, time)):
            return value.isoformat()

        if isinstance(value, (timedelta, pd.Timedelta)):
            return value.total_seconds()

        if isinstance(value, np.timedelta64):
            return float(value / np.timedelta64(1, "s"))

        if isinstance(value, pd.Timestamp):
            return value.isoformat()

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")

        return value

    @staticmethod
    def _generate_dataset_name(request: OutlierDetectionRequest) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"{request.outlier.method.value}-{timestamp}"

    def _to_summary(self, dataset: ProcessedDataset) -> ProcessedDatasetSummary:
        metrics = None
        if dataset.metrics:
            try:
                metrics = PipelineMetrics(**dataset.metrics)
            except Exception:  # pragma: no cover - resilience against legacy data
                logger.warning("Unable to parse metrics for dataset %s", dataset.id)

        return ProcessedDatasetSummary(
            id=dataset.id,
            well_id=dataset.well_id,
            name=dataset.name,
            status=dataset.status,
            record_count=dataset.record_count,
            created_at=dataset.created_at,
            created_by=dataset.created_by,
            metrics=metrics,
        )

    def _to_detail(self, dataset: ProcessedDataset) -> ProcessedDatasetDetail:
        metrics = None
        if dataset.metrics:
            try:
                metrics = PipelineMetrics(**dataset.metrics)
            except Exception:
                logger.warning("Unable to parse metrics for dataset %s", dataset.id)

        return ProcessedDatasetDetail(
            id=dataset.id,
            well_id=dataset.well_id,
            name=dataset.name,
            description=dataset.description,
            status=dataset.status,
            record_count=dataset.record_count,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            pipeline_config=dataset.pipeline_config or {},
            metrics=metrics,
        )
