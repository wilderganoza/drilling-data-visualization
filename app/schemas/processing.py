"""
Pydantic schemas for Processing endpoints.
"""
# Importamos BaseModel para crear los esquemas y Field para definir cada campo con su descripción
from pydantic import BaseModel, Field
# Importamos los tipos que usamos en las anotaciones
from typing import Dict


# Definimos el esquema de respuesta para el reporte de calidad de datos
class DataQualityReport(BaseModel):
    """Data quality assessment report."""
    # Guardamos el id del pozo
    well_id: int
    # Guardamos el total de registros analizados
    total_records: int
    # Guardamos el número de columnas analizadas
    columns_analyzed: int
    # Guardamos los valores faltantes por columna
    missing_values: Dict[str, int]
    # Guardamos los outliers detectados por columna
    outliers_detected: Dict[str, int]
    # Guardamos los rangos de datos por columna
    data_ranges: Dict[str, Dict[str, float]]
    # Guardamos el score general de calidad (0-100)
    quality_score: float = Field(..., description="Overall quality score 0-100")
