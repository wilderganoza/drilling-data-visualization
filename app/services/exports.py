"""Column listing and XLSX export — parameter-label lookup plus the actual
export logic, shared by app/web/exports.py (its own /exports/columns and
/exports/download routes) and every other app/web/* page that needs a
human-friendly parameter label for a chart/table (quality.py, crossplots.py,
comparison.py, welllogs.py, outliers.py) or the underlying export helpers
(app/services/rop_prediction.py, rop_features.py).

Was originally app/api/v1/endpoints/exports.py, one of 7 files under the
JSON API layer (app/api/v1) — removed because nothing called that API over
HTTP (the old React frontend it served is long gone; the current HTMX app
talks to the DB directly). This one file survived the removal because its
functions were never actually reached through FastAPI's routing/dependency
injection in practice: every caller already imported and invoked
`list_columns`/`download_xlsx`/`_get_label` directly as plain Python
functions, passing `db` and friends explicitly rather than letting
`Depends(...)` resolve them. Moving it here as an ordinary service module
just makes that reality match the code — no behavior change.
"""
# Habilitamos las anotaciones de tipo diferidas
from __future__ import annotations

# Importamos io para armar el archivo xlsx en memoria (buffer de bytes)
import io
# Importamos Optional para tipar parámetros que pueden no venir
from typing import Optional

# Importamos pandas para construir el DataFrame que exportamos a Excel (librería pesada, pero
# ya es una dependencia obligatoria del proyecto y se usa en todo el módulo, así que la cargamos arriba)
import pandas as pd
# Importamos HTTPException para reportar errores de negocio con código HTTP
from fastapi import HTTPException
# Importamos StreamingResponse para devolver el archivo xlsx como descarga
from fastapi.responses import StreamingResponse
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos db_manager para resolver la tabla de datos crudos por dominio (depth/time)
from app.db.session import db_manager
# Importamos DataRepository para consultar los datos crudos de un pozo
from app.repositories.data_repository import DataRepository
# Importamos ProcessedDatasetRepository para consultar los datasets ya procesados
from app.repositories.processed_dataset_repository import ProcessedDatasetRepository
# Importamos los esquemas Pydantic que definen la forma de las columnas y las requests de export
from app.schemas.exports import (
    ExportCaseType,
    ExportColumn,
    ExportColumnsResponse,
    ExportXlsxRequest,
)

# Internal columns to hide from the user
# Definimos las columnas internas que ocultamos al usuario en cualquier export
_HIDDEN = {"id", "well_id"}

# Parameter aliases — mirrors frontend parameterLabels.ts
# Definimos los alias legibles de cada parámetro (reflejan parameterLabels.ts del frontend)
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
    "bit_size": "Bit Size (in)",
    "trip_speed_ft_per_min": "Trip Speed (ft/min)",
    "rate_of_penetration_ft_per_hr": "ROP (ft/hr)",
    "on_bottom_rop_ft_per_hr": "On Bottom ROP (ft/hr)",
    "time_of_penetration_min_per_ft": "Time of Penetration (min/ft)",
    "is_outlier": "Is Outlier",
}


# Tokens that must stay uppercase in labels
# Definimos los tokens que mantenemos en mayúsculas al generar una etiqueta por defecto
_UPPERCASE_TOKENS = {"yyyy", "mm", "dd", "hh", "ss", "rpm", "spm", "rop", "psi", "gpm", "bbl"}


def _get_label(key: str) -> str:
    """Return the human-friendly alias for a column key."""
    # Si el key ya tiene un alias definido, lo devolvemos directamente
    if key in _PARAMETER_LABELS:
        return _PARAMETER_LABELS[key]
    # Fallback: title-case but keep certain tokens uppercase
    # Si no hay alias, generamos una etiqueta a partir del nombre de columna
    parts = key.split("_")
    result = []
    for p in parts:
        # Mantenemos en mayúsculas los tokens conocidos (rpm, psi, gpm, etc.)
        if p.lower() in _UPPERCASE_TOKENS:
            result.append(p.upper())
        else:
            result.append(p.capitalize())
    return " ".join(result)


def _sorted_columns(cols: list[ExportColumn]) -> list[ExportColumn]:
    """Sort columns alphabetically by label, but keep is_outlier first."""
    # Separamos is_outlier del resto para forzarlo siempre al inicio de la lista
    outlier = [c for c in cols if c.key == "is_outlier"]
    rest = sorted([c for c in cols if c.key != "is_outlier"], key=lambda c: c.label.lower())
    return outlier + rest


def _columns_for_raw(repo: DataRepository, well_id: int) -> list[ExportColumn]:
    # Obtenemos las columnas disponibles en la tabla de datos crudos
    available = repo.get_available_columns()
    # Armamos las columnas exportables, ocultando las internas (id, well_id)
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
    # Leemos un solo registro de muestra para descubrir qué columnas trae el dataset procesado
    records = ds_repo.list_records(dataset_id, include_outliers=False, page=1, page_size=1)
    if not records:
        return []
    sample = records[0].data or {}
    # Armamos las columnas a partir de las claves del JSON de datos, ocultando las internas
    cols = [ExportColumn(key=k, label=_get_label(k)) for k in sample.keys() if k not in _HIDDEN]
    # Agregamos siempre la columna is_outlier, que no vive dentro del JSON de datos
    cols.append(ExportColumn(key="is_outlier", label=_get_label("is_outlier")))
    return _sorted_columns(cols)


async def list_columns(
    well_id: int,
    case_type: ExportCaseType,
    processed_dataset_id: Optional[int],
    db: Session,
) -> ExportColumnsResponse:
    # Resolvemos las columnas disponibles según el tipo de caso: datos crudos o procesados
    if case_type == ExportCaseType.RAW:
        # Buscamos la tabla de datos crudos de profundidad (well_data)
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth table not found")
        repo = DataRepository(db, table)
        columns = _columns_for_raw(repo, well_id)
    else:
        # Para datos procesados exigimos que venga el id del dataset
        if not processed_dataset_id:
            raise HTTPException(status_code=400, detail="processed_dataset_id required")
        ds_repo = ProcessedDatasetRepository(db)
        columns = _columns_for_processed(ds_repo, processed_dataset_id)

    # Devolvemos la respuesta con la lista de columnas exportables
    return ExportColumnsResponse(
        well_id=well_id,
        case_type=case_type,
        dataset_id=processed_dataset_id,
        columns=columns,
    )


async def download_xlsx(payload: ExportXlsxRequest, db: Session) -> StreamingResponse:
    # Armamos el DataFrame según el tipo de caso: datos crudos o procesados
    if payload.case_type == ExportCaseType.RAW:
        # Buscamos la tabla de datos crudos de profundidad (well_data)
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth table not found")
        repo = DataRepository(db, table)
        # Muestreamos hasta 50000 filas para no cargar datasets enormes completos en memoria
        rows = repo.query_sample(payload.well_id, sample_size=50000)
        if not rows:
            raise HTTPException(status_code=404, detail="No data found")
        df = pd.DataFrame(rows)
        # Quitamos las columnas internas antes de exportar
        df.drop(columns=[c for c in _HIDDEN if c in df.columns], inplace=True)
    else:
        # Para datos procesados exigimos que venga el id del dataset
        if not payload.processed_dataset_id:
            raise HTTPException(status_code=400, detail="processed_dataset_id required")
        ds_repo = ProcessedDatasetRepository(db)
        all_rows: list[dict] = []
        page = 1
        # Paginamos la lectura del dataset procesado hasta traer todos los registros
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
                # Combinamos el JSON de datos con el flag is_outlier calculado en el registro
                row = dict(r.data)
                row["is_outlier"] = r.is_outlier
                all_rows.append(row)
            # Si la página vino incompleta, ya no hay más registros que leer
            if len(batch) < 5000:
                break
            page += 1
        if not all_rows:
            raise HTTPException(status_code=404, detail="No processed data found")
        df = pd.DataFrame(all_rows)
        # Quitamos las columnas internas antes de exportar
        df.drop(columns=[c for c in _HIDDEN if c in df.columns], inplace=True)

    # Filter columns if requested
    # Si el usuario pidió columnas específicas (en vez de todas), filtramos el DataFrame a esas
    if not payload.include_all_columns and payload.columns:
        valid = [c for c in payload.columns if c in df.columns]
        if not valid:
            raise HTTPException(status_code=400, detail="None of the requested columns exist")
        df = df[valid]

    # Rename columns to human-friendly aliases for the Excel headers
    # Renombramos las columnas técnicas a sus etiquetas legibles para los encabezados del Excel
    rename_map = {col: _get_label(col) for col in df.columns}
    df.rename(columns=rename_map, inplace=True)

    # Escribimos el DataFrame a un buffer de bytes en formato xlsx
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    # Devolvemos el archivo como una descarga en streaming
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=export.xlsx"},
    )
