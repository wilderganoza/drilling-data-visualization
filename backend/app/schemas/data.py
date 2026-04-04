from pydantic import BaseModel, Field # BaseModel para crear schemas Pydantic, Field para definir campos
from typing import Optional, List, Dict, Any # Tipos para anotaciones

# Schema base para peticiones de consulta de datos
class DataQueryRequest(BaseModel):
    # ID del pozo (requerido)
    well_id: int = Field(..., description="Well ID")
  
    # Lista de columnas a retornar (opcional, None = todas)
    columns: Optional[List[str]] = Field(None, description="Columns to retrieve (None = all)")
  
    # Límite de registros (opcional, por defecto 10000)
    limit: Optional[int] = Field(10000, description="Maximum number of records")

# Schema para consulta por rango de profundidad (hereda de DataQueryRequest)
class DepthRangeQuery(DataQueryRequest):
    # Profundidad mínima (requerido)
    min_depth: float = Field(..., description="Minimum depth")

    # Profundidad máxima (requerido)
    max_depth: float = Field(..., description="Maximum depth")

# Schema para consulta por rango de tiempo (hereda de DataQueryRequest)
class TimeRangeQuery(DataQueryRequest):
    # Tiempo inicial en formato YYYY/MM/DD (requerido)
    start_time: str = Field(..., description="Start time (YYYY/MM/DD)")

    # Tiempo final en formato YYYY/MM/DD (requerido)
    end_time: str = Field(..., description="End time (YYYY/MM/DD)")

# Schema de respuesta para consultas de datos
class DataResponse(BaseModel):
    # ID del pozo
    well_id: int = Field(..., description="Well ID")

    # Número total de registros retornados
    total_records: int = Field(..., description="Number of records returned")

    # Lista de nombres de columnas
    columns: List[str] = Field(..., description="Column names")

    # Lista de registros (cada registro es un diccionario)
    data: List[Dict[str, Any]] = Field(..., description="Query results")

# Schema de respuesta para muestra de datos
class DataSampleResponse(BaseModel):
    # ID del pozo
    well_id: int
    
    # Tamaño de la muestra retornada
    sample_size: int
    
    # Lista de nombres de columnas
    columns: List[str]
    
    # Lista de registros de la muestra
    data: List[Dict[str, Any]]

# Schema de respuesta para rango de profundidad
class DepthRangeResponse(BaseModel):
    # ID del pozo
    well_id: int
    
    # Profundidad mínima (opcional)
    min_depth: Optional[float]
    
    # Profundidad máxima (opcional)
    max_depth: Optional[float]

# Schema de respuesta para columnas disponibles
class ColumnsResponse(BaseModel):
    # Tipo de base de datos (time o depth)
    database_type: str = Field(..., description="Database type (time or depth)")

    # Total de columnas disponibles
    total_columns: int

    # Lista de nombres de columnas
    columns: List[str]
