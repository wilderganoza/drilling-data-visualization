# Importamos BaseModel y Field para declarar los esquemas Pydantic
from pydantic import BaseModel, Field
# Importamos List y Optional para tipar los campos
from typing import List, Optional
# Importamos Enum para declarar el tipo de caso de exportación
from enum import Enum


# Definimos los tipos de caso que se pueden exportar: datos crudos o ya procesados
class ExportCaseType(str, Enum):
    RAW = "raw"
    PROCESSED = "processed"


# Definimos una columna disponible para exportar
class ExportColumn(BaseModel):
    # Guardamos la clave técnica de la columna
    key: str
    # Guardamos la etiqueta visible de la columna
    label: str
    # Guardamos el grupo al que pertenece la columna, si aplica
    group: Optional[str] = None


# Definimos la respuesta con las columnas disponibles para un pozo/caso
class ExportColumnsResponse(BaseModel):
    # Guardamos el id del pozo
    well_id: int
    # Guardamos el tipo de caso (raw o processed)
    case_type: ExportCaseType
    # Guardamos el id del dataset procesado, cuando el caso es "processed"
    dataset_id: Optional[int] = None
    # Guardamos la lista de columnas disponibles
    columns: List[ExportColumn]


# Definimos la solicitud para generar un export en XLSX
class ExportXlsxRequest(BaseModel):
    # Guardamos el id del pozo a exportar
    well_id: int
    # Guardamos el tipo de caso a exportar
    case_type: ExportCaseType
    # Guardamos el id del dataset procesado, cuando el caso es "processed"
    processed_dataset_id: Optional[int] = None
    # Guardamos si se exportan todas las columnas
    include_all_columns: bool = True
    # Guardamos las columnas específicas a exportar, cuando no se exportan todas
    columns: Optional[List[str]] = None
    # Guardamos si se incluye la marca de outliers en el export
    include_outliers: bool = False
