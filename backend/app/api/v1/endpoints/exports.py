"""Exports endpoints — list columns and download XLSX."""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import db_manager, get_depth_db
from app.db.repositories.data_repository import DataRepository
from app.db.repositories.processed_dataset_repository import ProcessedDatasetRepository
from app.schemas.exports import (
    ExportCaseType,
    ExportColumn,
    ExportColumnsResponse,
    ExportXlsxRequest,
)

logger = get_logger(__name__)
router = APIRouter()

# Internal columns to hide from the user
_HIDDEN = {"id", "well_id"}

# Parameter aliases — mirrors frontend parameterLabels.ts
_PARAMETER_LABELS: dict[str, str] = {
    "on_bottom_hours_hrs": "On Bottom Hours",
    "circulating_hours_hrs": "Circulating Hours",
    "rotary_rpm_rpm": "Rotary RPM",
    "motor_rpm_rpm": "Motor RPM",
    "pump_1_strokes_min_spm": "Pump 1 SPM",
    "pump_2_strokes_min_spm": "Pump 2 SPM",
    "pump_1_total_strokes_strokes": "Pump 1 Total Strokes",
    "pump_2_total_strokes_strokes": "Pump 2 Total Strokes",
    "pump_3_total_strokes_strokes": "Pump 3 Total Strokes",
    "pump_4_total_strokes_strokes": "Pump 4 Total Strokes",
    "total_strokes_p1plusp2plusp3plusp4_strokes": "Total Strokes (All Pumps)",
    "total_pump_output_gal_per_min": "Total Pump Output (gpm)",
    "totalpumpdisplacement_barrels": "Total Pump Displacement (bbl)",
    "fill_strokes_strokes": "Fill Strokes",
    "total_fill_strokes_strokes": "Total Fill Strokes",
    "over_pull_klbs": "Over Pull (klbs)",
    "weight_on_bit_klbs": "Weight on Bit (klbs)",
    "hook_load_klbs": "Hook Load (klbs)",
    "line_wear_ton_miles": "Line Wear (ton-miles)",
    "standpipe_pressure_psi": "Standpipe Pressure (psi)",
    "differential_pressure_psi": "Differential Pressure (psi)",
    "hole_depth_feet": "Hole Depth (ft)",
    "bit_depth_feet": "Bit Depth (ft)",
    "block_height_feet": "Block Height (ft)",
    "trip_speed_ft_per_min": "Trip Speed (ft/min)",
    "rate_of_penetration_ft_per_hr": "ROP (ft/hr)",
    "on_bottom_rop_ft_per_hr": "On Bottom ROP (ft/hr)",
    "time_of_penetration_min_per_ft": "Time of Penetration (min/ft)",
    "is_outlier": "Is Outlier",
}


# Tokens that must stay uppercase in labels
_UPPERCASE_TOKENS = {"yyyy", "mm", "dd", "hh", "ss", "rpm", "spm", "rop", "psi", "gpm", "bbl"}


def _get_label(key: str) -> str:
    """Return the human-friendly alias for a column key."""
    if key in _PARAMETER_LABELS:
        return _PARAMETER_LABELS[key]
    # Fallback: title-case but keep certain tokens uppercase
    parts = key.split("_")
    result = []
    for p in parts:
        if p.lower() in _UPPERCASE_TOKENS:
            result.append(p.upper())
        else:
            result.append(p.capitalize())
    return " ".join(result)


def _sorted_columns(cols: list[ExportColumn]) -> list[ExportColumn]:
    """Sort columns alphabetically by label, but keep is_outlier first."""
    outlier = [c for c in cols if c.key == "is_outlier"]
    rest = sorted([c for c in cols if c.key != "is_outlier"], key=lambda c: c.label.lower())
    return outlier + rest


def _columns_for_raw(repo: DataRepository, well_id: int) -> list[ExportColumn]:
    available = repo.get_available_columns()
    cols = [
        ExportColumn(key=c, label=_get_label(c))
        for c in available
        if c not in _HIDDEN
    ]
    return _sorted_columns(cols)


def _columns_for_processed(
    ds_repo: ProcessedDatasetRepository,
    dataset_id: int,
) -> list[ExportColumn]:
    records = ds_repo.list_records(dataset_id, include_outliers=False, page=1, page_size=1)
    if not records:
        return []
    sample = records[0].data or {}
    cols = [ExportColumn(key=k, label=_get_label(k)) for k in sample.keys() if k not in _HIDDEN]
    cols.append(ExportColumn(key="is_outlier", label=_get_label("is_outlier")))
    return _sorted_columns(cols)


@router.get("/columns", response_model=ExportColumnsResponse)
async def list_columns(
    well_id: int = Query(...),
    case_type: ExportCaseType = Query(...),
    processed_dataset_id: Optional[int] = Query(None),
    db: Session = Depends(get_depth_db),
):
    if case_type == ExportCaseType.RAW:
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth table not found")
        repo = DataRepository(db, table)
        columns = _columns_for_raw(repo, well_id)
    else:
        if not processed_dataset_id:
            raise HTTPException(status_code=400, detail="processed_dataset_id required")
        ds_repo = ProcessedDatasetRepository(db)
        columns = _columns_for_processed(ds_repo, processed_dataset_id)

    return ExportColumnsResponse(
        well_id=well_id,
        case_type=case_type,
        dataset_id=processed_dataset_id,
        columns=columns,
    )


@router.post("/xlsx")
async def download_xlsx(
    payload: ExportXlsxRequest,
    db: Session = Depends(get_depth_db),
):
    if payload.case_type == ExportCaseType.RAW:
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth table not found")
        repo = DataRepository(db, table)
        rows = repo.query_sample(payload.well_id, sample_size=50000)
        if not rows:
            raise HTTPException(status_code=404, detail="No data found")
        df = pd.DataFrame(rows)
        df.drop(columns=[c for c in _HIDDEN if c in df.columns], inplace=True)
    else:
        if not payload.processed_dataset_id:
            raise HTTPException(status_code=400, detail="processed_dataset_id required")
        ds_repo = ProcessedDatasetRepository(db)
        all_rows: list[dict] = []
        page = 1
        while True:
            batch = ds_repo.list_records(
                payload.processed_dataset_id,
                include_outliers=payload.include_outliers,
                page=page,
                page_size=5000,
            )
            if not batch:
                break
            for r in batch:
                if not r.data:
                    continue
                row = dict(r.data)
                row["is_outlier"] = r.is_outlier
                all_rows.append(row)
            if len(batch) < 5000:
                break
            page += 1
        if not all_rows:
            raise HTTPException(status_code=404, detail="No processed data found")
        df = pd.DataFrame(all_rows)
        df.drop(columns=[c for c in _HIDDEN if c in df.columns], inplace=True)

    # Filter columns if requested
    if not payload.include_all_columns and payload.columns:
        valid = [c for c in payload.columns if c in df.columns]
        if not valid:
            raise HTTPException(status_code=400, detail="None of the requested columns exist")
        df = df[valid]

    # Rename columns to human-friendly aliases for the Excel headers
    rename_map = {col: _get_label(col) for col in df.columns}
    df.rename(columns=rename_map, inplace=True)

    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=export.xlsx"},
    )
