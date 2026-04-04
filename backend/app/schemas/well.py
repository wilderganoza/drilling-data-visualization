from pydantic import BaseModel, Field # BaseModel para crear schemas Pydantic, Field para definir campos
from typing import Optional # Optional para campos opcionales
from datetime import datetime # Datetime para campos de fecha/hora

# Schema base para Well (campos comunes)
class WellBase(BaseModel):
    # Nombre del pozo (requerido)
    well_name: str = Field(..., description="Name of the well")

    # Nombre del archivo original (opcional)
    filename: Optional[str] = Field(None, description="Original filename")

    # Total de filas importadas (opcional)
    total_rows: Optional[int] = Field(None, description="Total number of rows")

    # Total de columnas importadas (opcional)
    total_columns: Optional[int] = Field(None, description="Total number of columns")

# Schema de respuesta para Well (hereda de WellBase)
class WellResponse(WellBase):
    # ID del pozo (requerido)
    id: int = Field(..., description="Well ID")

    # Fecha de importación (opcional)
    date_imported: Optional[datetime] = Field(None, description="Import date")
    
    # Configuración de Pydantic
    class Config:
        # Permitir crear desde atributos de objetos ORM (SQLAlchemy)
        from_attributes = True

# Schema de respuesta para lista de pozos
class WellListResponse(BaseModel):
    # Total de pozos disponibles
    total: int = Field(..., description="Total number of wells")

    # Lista de pozos retornados
    wells: list[WellResponse] = Field(..., description="List of wells")

    # Número de registros saltados (paginación)
    skip: int = Field(0, description="Number of records skipped")

    # Máximo de registros retornados (paginación)
    limit: int = Field(..., description="Maximum records returned")

# Schema de respuesta para metadata de pozo
class WellMetadata(BaseModel):
    # ID del pozo
    id: int

    # Nombre del pozo
    well_name: str

    # Nombre del archivo original (opcional)
    filename: Optional[str]

    # Total de filas importadas (opcional)
    total_rows: Optional[int]

    # Total de columnas importadas (opcional)
    total_columns: Optional[int]

    # Fecha de importación como string (opcional)
    date_imported: Optional[str]

    # Rango de profundidad (min y max) como diccionario (opcional)
    depth_range: Optional[dict] = Field(None, description="Min and max depth")

    # Lista de columnas disponibles en los datos (opcional)
    available_columns: Optional[list[str]] = Field(None, description="Available data columns")
