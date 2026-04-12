from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class ExportCaseType(str, Enum):
    RAW = "raw"
    PROCESSED = "processed"


class ExportColumn(BaseModel):
    key: str
    label: str
    group: Optional[str] = None


class ExportColumnsResponse(BaseModel):
    well_id: int
    case_type: ExportCaseType
    dataset_id: Optional[int] = None
    columns: List[ExportColumn]


class ExportXlsxRequest(BaseModel):
    well_id: int
    case_type: ExportCaseType
    processed_dataset_id: Optional[int] = None
    include_all_columns: bool = True
    columns: Optional[List[str]] = None
    include_outliers: bool = False
