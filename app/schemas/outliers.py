"""Pydantic schemas for outlier detection module."""
# Habilitamos anotaciones diferidas para poder referenciar tipos definidos más abajo en el archivo
from __future__ import annotations

# Importamos datetime para tipar las fechas de creación/actualización
from datetime import datetime
# Importamos Enum para declarar los métodos de escalado y de detección de outliers
from enum import Enum
# Importamos los tipos que usamos en las anotaciones
from typing import Any, Dict, List, Optional, Union

# Importamos BaseModel/Field para declarar los esquemas y field_validator para validar campos
from pydantic import BaseModel, Field, field_validator


# Definimos los métodos de escalado disponibles
class ScalingMethod(str, Enum):
    none = "none"
    standard = "standard"
    minmax = "minmax"
    robust = "robust"
    maxabs = "maxabs"


# Definimos la configuración de escalado del pipeline
class ScalingConfig(BaseModel):
    # Guardamos el método de escalado a usar
    method: ScalingMethod = Field(default=ScalingMethod.standard)
    # Guardamos los parámetros adicionales del método
    params: Dict[str, Any] = Field(default_factory=dict)


# Definimos la configuración de PCA del pipeline
class PCAConfig(BaseModel):
    # Guardamos si PCA está habilitado
    enabled: bool = Field(default=False)
    # Guardamos el número de componentes (entero) o la proporción de varianza (float)
    n_components: Optional[Union[int, float]] = Field(
        default=None,
        description="Number of PCA components (int) or variance ratio (float).",
    )
    # Guardamos si se aplica whitening
    whiten: bool = Field(default=False)
    # Guardamos el solver de SVD a usar
    svd_solver: str = Field(default="auto")

    # Validamos que n_components tenga un valor coherente según su tipo
    @field_validator("n_components")
    def validate_components(cls, value):
        # Aceptamos None sin validar más
        if value is None:
            return value
        # Exigimos que un entero de componentes sea positivo
        if isinstance(value, int) and value <= 0:
            raise ValueError("n_components must be > 0")
        # Exigimos que una proporción de varianza esté entre 0 y 1
        if isinstance(value, float) and not (0 < value <= 1):
            raise ValueError("n_components float must be between 0 and 1")
        # Devolvemos el valor si pasó las validaciones
        return value


# Definimos los métodos de detección de outliers disponibles
class OutlierMethod(str, Enum):
    isolation_forest = "isolation_forest"
    dbscan = "dbscan"
    local_outlier_factor = "local_outlier_factor"
    zscore = "zscore"
    iqr = "iqr"


# Definimos la configuración de detección de outliers del pipeline
class OutlierConfig(BaseModel):
    # Guardamos el método de detección a usar
    method: OutlierMethod = Field(default=OutlierMethod.isolation_forest)
    # Guardamos los parámetros adicionales del método
    params: Dict[str, Any] = Field(default_factory=dict)
    # Guardamos si se deben almacenar las filas outlier junto con los datos limpios
    mark_outliers: bool = Field(
        default=True,
        description="Whether to store outlier rows alongside cleaned data.",
    )


# Definimos la solicitud para correr el pipeline de detección de outliers
class OutlierDetectionRequest(BaseModel):
    # Guardamos el id del pozo
    well_id: int
    # Guardamos el dominio de datos sobre el que se arma el caso (profundidad o tiempo)
    domain: str = Field(default="depth", description="Data domain the case is built on: depth | time")
    # Guardamos el nombre personalizado del dataset procesado
    dataset_name: Optional[str] = Field(default=None, description="Custom name for processed dataset")
    # Guardamos la descripción del caso
    description: Optional[str] = Field(default=None)
    # Guardamos las variables incluidas en el pipeline
    variables: List[str] = Field(..., min_items=1)
    # Guardamos la configuración de escalado
    scaling: ScalingConfig = Field(default_factory=ScalingConfig)
    # Guardamos la configuración de PCA
    pca: PCAConfig = Field(default_factory=PCAConfig)
    # Guardamos la configuración de detección de outliers
    outlier: OutlierConfig = Field(default_factory=OutlierConfig)
    # Guardamos el máximo de filas a procesar (None = límite por defecto)
    max_records: Optional[int] = Field(
        default=None,
        description="Maximum number of rows to process (None = default limit).",
    )
    # Guardamos columnas adicionales a almacenar en el dataset procesado (ej. depth, time)
    include_columns: Optional[List[str]] = Field(
        default=None,
        description="Additional columns to store in processed dataset (e.g., depth, time).",
    )


# Definimos las métricas resultantes del pipeline
class PipelineMetrics(BaseModel):
    # Guardamos el total de registros de entrada
    total_records: int
    # Guardamos el total de registros procesados
    processed_records: int
    # Guardamos el total de registros marcados como outlier
    outlier_records: int
    # Guardamos el porcentaje de outliers
    outlier_percentage: float
    # Guardamos las variables usadas en el pipeline
    variables: List[str]
    # Guardamos el total de registros descartados
    dropped_records: int = Field(default=0)
    # Guardamos las etiquetas de los features escalados
    scaled_feature_labels: Optional[List[str]] = Field(default=None)
    # Guardamos las etiquetas de los componentes de PCA
    pca_component_labels: Optional[List[str]] = Field(default=None)
    # Guardamos la varianza explicada por cada componente
    explained_variance: Optional[List[float]] = Field(default=None)
    # Guardamos la proporción de varianza explicada por cada componente
    explained_variance_ratio: Optional[List[float]] = Field(default=None)


# Definimos el resumen de un dataset procesado (para listados)
class ProcessedDatasetSummary(BaseModel):
    # Guardamos el id del dataset
    id: int
    # Guardamos el id del pozo
    well_id: int
    # Guardamos el nombre del dataset
    name: str
    # Guardamos el estado del dataset
    status: str
    # Guardamos el número de registros del dataset
    record_count: Optional[int]
    # Guardamos cuándo se creó el dataset
    created_at: datetime
    # Guardamos quién creó el dataset
    created_by: Optional[int]
    # Guardamos las métricas del dataset
    metrics: Optional[PipelineMetrics]


# Definimos el detalle completo de un dataset procesado
class ProcessedDatasetDetail(BaseModel):
    # Guardamos el id del dataset
    id: int
    # Guardamos el id del pozo
    well_id: int
    # Guardamos el nombre del dataset
    name: str
    # Guardamos la descripción del dataset
    description: Optional[str]
    # Guardamos el estado del dataset
    status: str
    # Guardamos el número de registros del dataset
    record_count: Optional[int]
    # Guardamos cuándo se creó el dataset
    created_at: datetime
    # Guardamos cuándo se actualizó el dataset por última vez
    updated_at: datetime
    # Guardamos la configuración del pipeline que generó el dataset
    pipeline_config: Dict[str, Any]
    # Guardamos las métricas del dataset
    metrics: Optional[PipelineMetrics]


# Definimos la respuesta de correr el pipeline de detección de outliers
class OutlierDetectionResponse(BaseModel):
    # Guardamos el dataset resultante
    dataset: ProcessedDatasetDetail


# Definimos la respuesta de una vista previa de detección de outliers
class OutlierPreviewResponse(BaseModel):
    # Guardamos las métricas de la vista previa
    metrics: PipelineMetrics
    # Guardamos las etiquetas de los componentes, si aplica
    component_labels: Optional[List[str]] = None
    # Guardamos los valores de los componentes por fila
    components: List[List[float]] = Field(default_factory=list)
    # Guardamos la marca de outlier por fila
    is_outlier: List[bool] = Field(default_factory=list)


# Definimos una fila de la vista previa de escalado
class ScalingPreviewRowData(BaseModel):
    # Guardamos el índice de la fila
    index: int
    # Guardamos los valores originales de la fila
    raw: Dict[str, Optional[float]]
    # Guardamos los valores escalados de la fila
    scaled: Dict[str, Optional[float]]


# Definimos la respuesta de la vista previa de escalado
class ScalingPreviewResponse(BaseModel):
    # Guardamos las variables incluidas en la vista previa
    variables: List[str]
    # Guardamos el total de filas disponibles
    total_rows: int
    # Guardamos las filas de la vista previa
    rows: List[ScalingPreviewRowData]


# Definimos el puntaje de una fila en la vista previa de PCA
class PcaPreviewScore(BaseModel):
    # Guardamos el índice de la fila
    index: int
    # Guardamos los valores de los componentes para esa fila
    components: List[float]


# Definimos la respuesta de la vista previa de PCA
class PcaPreviewResponse(BaseModel):
    # Guardamos las etiquetas de los componentes
    component_labels: List[str]
    # Guardamos la varianza explicada por cada componente
    explained_variance: List[float]
    # Guardamos la proporción de varianza explicada por cada componente
    explained_variance_ratio: List[float]
    # Guardamos los puntajes de PCA por fila
    scores: List[PcaPreviewScore]


# Definimos los datos de un registro procesado
class ProcessedRecordData(BaseModel):
    # Guardamos el id del registro original en la fuente de datos
    source_record_id: Optional[int]
    # Guardamos si el registro fue marcado como outlier
    is_outlier: bool
    # Guardamos los datos originales del registro
    data: Dict[str, Any]
    # Guardamos los datos escalados del registro, si aplica
    scaled: Optional[Dict[str, Any]] = None
    # Guardamos los componentes de PCA del registro, si aplica
    components: Optional[Dict[str, Any]] = None


# Definimos la respuesta paginada de datos procesados
class ProcessedDataResponse(BaseModel):
    # Guardamos el id del dataset
    dataset_id: int
    # Guardamos si la respuesta incluye los outliers
    include_outliers: bool
    # Guardamos el total de registros disponibles
    total_records: int
    # Guardamos el número de página actual
    page: int
    # Guardamos el tamaño de página
    page_size: int
    # Guardamos los registros de esta página
    records: List[ProcessedRecordData]
