"""
Pydantic schemas for Processing endpoints.
"""
# Importar BaseModel para crear schemas Pydantic, Field para definir campos
from pydantic import BaseModel, Field
# Importar tipos para anotaciones
from typing import List, Dict, Any, Optional, Literal


# Schema de petición para limpieza de datos
class CleanDataRequest(BaseModel):
    """Request to clean data."""
    # ID del pozo (requerido)
    well_id: int = Field(..., description="Well ID")
    # Lista de columnas a limpiar (opcional, None = todas)
    columns: Optional[List[str]] = Field(None, description="Columns to clean (None = all)")
    # Si se deben remover outliers (por defecto True)
    remove_outliers: bool = Field(True, description="Remove outliers")
    # Método para detectar outliers (iqr, zscore, percentile)
    outlier_method: Literal['iqr', 'zscore', 'percentile'] = Field('iqr')
    # Si se deben llenar valores faltantes (por defecto True)
    fill_missing: bool = Field(True, description="Fill missing values")
    # Método para llenar valores faltantes
    fill_method: Literal['interpolate', 'forward', 'backward', 'mean', 'median', 'zero'] = Field('interpolate')


# Schema de petición para transformación de datos
class TransformDataRequest(BaseModel):
    """Request to transform data."""
    # ID del pozo (requerido)
    well_id: int = Field(..., description="Well ID")
    # Si se debe calcular ROP (Rate of Penetration)
    calculate_rop: bool = Field(False, description="Calculate ROP")
    # Si se debe calcular MSE (Mechanical Specific Energy)
    calculate_mse: bool = Field(False, description="Calculate MSE")
    # Si se deben calcular métricas de eficiencia
    calculate_efficiency: bool = Field(False, description="Calculate efficiency metrics")
    # Si se deben remuestrear los datos
    resample: bool = Field(False, description="Resample data")
    # Número objetivo de puntos para remuestreo
    target_points: int = Field(10000, description="Target points for resampling")
    # Diámetro de broca en pulgadas (para cálculo de MSE)
    bit_diameter: float = Field(8.5, description="Bit diameter in inches for MSE")


# Schema de petición para interpolación de datos
class InterpolateRequest(BaseModel):
    """Request to interpolate data."""
    # ID del pozo (requerido)
    well_id: int = Field(..., description="Well ID")
    # Puntos de profundidad objetivo específicos (opcional)
    target_depths: Optional[List[float]] = Field(None, description="Target depth points")
    # Profundidad mínima para grilla uniforme (opcional)
    min_depth: Optional[float] = Field(None, description="Minimum depth for uniform grid")
    # Profundidad máxima para grilla uniforme (opcional)
    max_depth: Optional[float] = Field(None, description="Maximum depth for uniform grid")
    # Tamaño de paso para grilla uniforme (por defecto 1.0)
    depth_step: float = Field(1.0, description="Step size for uniform grid")
    # Método de interpolación (linear, nearest, cubic)
    method: Literal['linear', 'nearest', 'cubic'] = Field('linear', description="Interpolation method")
    # Lista de columnas a interpolar (opcional, None = todas)
    columns: Optional[List[str]] = Field(None, description="Columns to interpolate")


# Schema de petición para detección de eventos
class EventDetectionRequest(BaseModel):
    """Request to detect events."""
    # ID del pozo (requerido)
    well_id: int = Field(..., description="Well ID")
    # Si se deben detectar conexiones de tubería
    detect_connections: bool = Field(True, description="Detect pipe connections")
    # Si se deben detectar eventos de tubería atascada
    detect_stuck_pipe: bool = Field(True, description="Detect stuck pipe events")
    # Si se deben detectar anomalías
    detect_anomalies: bool = Field(True, description="Detect anomalies")
    # Nombre de columna de ROP (Rate of Penetration)
    rop_col: str = Field('rate_of_penetration_ft_per_hr', description="ROP column name")
    # Nombre de columna de WOB (Weight on Bit)
    wob_col: str = Field('weight_on_bit_klbs', description="WOB column name")


# Schema de respuesta para operaciones de procesamiento
class ProcessingResponse(BaseModel):
    """Response from processing operations."""
    # ID del pozo
    well_id: int
    # Tipo de operación realizada
    operation: str
    # Si la operación fue exitosa
    success: bool
    # Mensaje descriptivo del resultado
    message: str
    # Datos resultantes (opcional)
    data: Optional[Dict[str, Any]] = None
    # Estadísticas de la operación (opcional)
    statistics: Optional[Dict[str, Any]] = None


# Schema de respuesta para detección de eventos
class EventDetectionResponse(BaseModel):
    """Response from event detection."""
    # ID del pozo
    well_id: int
    # Total de eventos detectados
    total_events: int
    # Conteo de eventos por tipo
    events_by_type: Dict[str, int]
    # Lista de eventos agrupados por tipo
    events: Dict[str, List[Dict[str, Any]]]
    # Resumen de eventos detectados
    summary: Dict[str, Any]


# Schema de respuesta para reporte de calidad de datos
class DataQualityReport(BaseModel):
    """Data quality assessment report."""
    # ID del pozo
    well_id: int
    # Total de registros analizados
    total_records: int
    # Número de columnas analizadas
    columns_analyzed: int
    # Diccionario de valores faltantes por columna
    missing_values: Dict[str, int]
    # Diccionario de outliers detectados por columna
    outliers_detected: Dict[str, int]
    # Diccionario de rangos de datos por columna
    data_ranges: Dict[str, Dict[str, float]]
    # Score general de calidad (0-100)
    quality_score: float = Field(..., description="Overall quality score 0-100")
