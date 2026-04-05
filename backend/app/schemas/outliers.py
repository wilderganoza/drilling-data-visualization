"""Pydantic schemas for outlier detection module."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class ScalingMethod(str, Enum):
    none = "none"
    standard = "standard"
    minmax = "minmax"
    robust = "robust"
    maxabs = "maxabs"


class ScalingConfig(BaseModel):
    method: ScalingMethod = Field(default=ScalingMethod.standard)
    params: Dict[str, Any] = Field(default_factory=dict)


class PCAConfig(BaseModel):
    enabled: bool = Field(default=False)
    n_components: Optional[Union[int, float]] = Field(
        default=None,
        description="Number of PCA components (int) or variance ratio (float).",
    )
    whiten: bool = Field(default=False)
    svd_solver: str = Field(default="auto")

    @field_validator("n_components")
    def validate_components(cls, value):
        if value is None:
            return value
        if isinstance(value, int) and value <= 0:
            raise ValueError("n_components must be > 0")
        if isinstance(value, float) and not (0 < value <= 1):
            raise ValueError("n_components float must be between 0 and 1")
        return value


class OutlierMethod(str, Enum):
    isolation_forest = "isolation_forest"
    dbscan = "dbscan"
    local_outlier_factor = "local_outlier_factor"
    zscore = "zscore"
    iqr = "iqr"


class OutlierConfig(BaseModel):
    method: OutlierMethod = Field(default=OutlierMethod.isolation_forest)
    params: Dict[str, Any] = Field(default_factory=dict)
    mark_outliers: bool = Field(
        default=True,
        description="Whether to store outlier rows alongside cleaned data.",
    )


class OutlierDetectionRequest(BaseModel):
    well_id: int
    dataset_name: Optional[str] = Field(default=None, description="Custom name for processed dataset")
    description: Optional[str] = Field(default=None)
    variables: List[str] = Field(..., min_items=1)
    scaling: ScalingConfig = Field(default_factory=ScalingConfig)
    pca: PCAConfig = Field(default_factory=PCAConfig)
    outlier: OutlierConfig = Field(default_factory=OutlierConfig)
    max_records: Optional[int] = Field(
        default=None,
        description="Maximum number of rows to process (None = default limit).",
    )
    include_columns: Optional[List[str]] = Field(
        default=None,
        description="Additional columns to store in processed dataset (e.g., depth, time).",
    )


class PipelineMetrics(BaseModel):
    total_records: int
    processed_records: int
    outlier_records: int
    outlier_percentage: float
    variables: List[str]
    dropped_records: int = Field(default=0)
    scaled_feature_labels: Optional[List[str]] = Field(default=None)
    pca_component_labels: Optional[List[str]] = Field(default=None)
    explained_variance: Optional[List[float]] = Field(default=None)
    explained_variance_ratio: Optional[List[float]] = Field(default=None)


class ProcessedDatasetSummary(BaseModel):
    id: int
    well_id: int
    name: str
    status: str
    record_count: Optional[int]
    created_at: datetime
    created_by: Optional[int]
    metrics: Optional[PipelineMetrics]


class ProcessedDatasetDetail(BaseModel):
    id: int
    well_id: int
    name: str
    description: Optional[str]
    status: str
    record_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    pipeline_config: Dict[str, Any]
    metrics: Optional[PipelineMetrics]


class OutlierDetectionResponse(BaseModel):
    dataset: ProcessedDatasetDetail


class OutlierPreviewResponse(BaseModel):
    metrics: PipelineMetrics
    component_labels: Optional[List[str]] = None
    components: List[List[float]] = Field(default_factory=list)
    is_outlier: List[bool] = Field(default_factory=list)


class ProcessedRecordData(BaseModel):
    source_record_id: Optional[int]
    is_outlier: bool
    data: Dict[str, Any]
    scaled: Optional[Dict[str, Any]] = None
    components: Optional[Dict[str, Any]] = None


class ProcessedDataResponse(BaseModel):
    dataset_id: int
    include_outliers: bool
    total_records: int
    page: int
    page_size: int
    records: List[ProcessedRecordData]

