"""
Data endpoints - Query well data from Depth database.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.logging import get_logger
from app.db.session import get_depth_db, db_manager
from app.db.repositories.data_repository import DataRepository
from app.schemas.data import (
    DataResponse, DataSampleResponse, DepthRangeResponse, ColumnsResponse
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/depth/sample/{well_id}", response_model=DataSampleResponse, summary="Get depth data sample")
async def get_depth_sample(
    well_id: int,
    sample_size: int = Query(100, ge=1, le=50000, description="Sample size"),
    db: Session = Depends(get_depth_db)
):
    """Get a sample of depth-based data for a well."""
    logger.info(f"Fetching depth sample for well {well_id}, size={sample_size}")
    try:
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth database table not found")
        repo = DataRepository(db, table)
        data = repo.query_sample(well_id, sample_size)
        if not data:
            raise HTTPException(status_code=404, detail=f"No data found for well {well_id}")
        columns = list(data[0].keys()) if data else []
        return DataSampleResponse(
            well_id=well_id,
            sample_size=len(data),
            columns=columns,
            data=data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching depth sample: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")


@router.get("/depth/range/{well_id}", response_model=DepthRangeResponse, summary="Get depth range")
async def get_depth_range(
    well_id: int,
    db: Session = Depends(get_depth_db)
):
    """Get min and max depth for a well."""
    logger.info(f"Fetching depth range for well {well_id}")
    try:
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth database table not found")
        repo = DataRepository(db, table)
        depth_range = repo.get_depth_range(well_id)
        if depth_range is None:
            raise HTTPException(status_code=404, detail=f"No data found for well {well_id}")
        return DepthRangeResponse(
            well_id=well_id,
            min_depth=depth_range.get("min_depth"),
            max_depth=depth_range.get("max_depth")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching depth range: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching depth range: {str(e)}")


@router.get("/depth/query/{well_id}", response_model=DataResponse, summary="Query depth data by range")
async def query_depth_data(
    well_id: int,
    min_depth: float = Query(..., description="Minimum depth"),
    max_depth: float = Query(..., description="Maximum depth"),
    columns: Optional[str] = Query(None, description="Comma-separated column names"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records"),
    db: Session = Depends(get_depth_db)
):
    """Query depth data by depth range."""
    logger.info(f"Querying depth data: well={well_id}, depth=[{min_depth}, {max_depth}]")
    try:
        table = db_manager.get_depth_table("well_data")
        if table is None:
            raise HTTPException(status_code=500, detail="Depth database table not found")
        repo = DataRepository(db, table)
        column_list = None
        if columns:
            column_list = [col.strip() for col in columns.split(",")]
        data = repo.query_by_depth_range(
            well_id=well_id,
            min_depth=min_depth,
            max_depth=max_depth,
            columns=column_list,
            limit=limit
        )
        if not data:
            return DataResponse(well_id=well_id, total_records=0, columns=[], data=[])
        result_columns = list(data[0].keys()) if data else []
        return DataResponse(
            well_id=well_id,
            total_records=len(data),
            columns=result_columns,
            data=data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying depth data: {e}")
        raise HTTPException(status_code=500, detail=f"Error querying data: {str(e)}")


@router.get("/depth/columns", response_model=ColumnsResponse, summary="Get depth database columns")
async def get_depth_columns():
    """Get list of available columns in Depth database."""
    try:
        columns = db_manager.get_depth_columns()
        return ColumnsResponse(
            database_type="depth",
            total_columns=len(columns),
            columns=list(columns.keys())
        )
    except Exception as e:
        logger.error(f"Error fetching depth columns: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching columns: {str(e)}")
