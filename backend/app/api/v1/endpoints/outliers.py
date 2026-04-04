"""Endpoints for the Outlier Detection module."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import db_manager, get_depth_db
from app.db.models import User
from app.schemas.outliers import (
    OutlierDetectionRequest,
    OutlierDetectionResponse,
    ProcessedDataResponse,
    ProcessedDatasetDetail,
    ProcessedDatasetSummary,
)
from app.services.outlier_detection import (
    OutlierDetectionError,
    OutlierDetectionService,
)

logger = get_logger(__name__)

router = APIRouter()


def get_outlier_service(db: Session = Depends(get_depth_db)) -> OutlierDetectionService:
    table = db_manager.get_depth_table("well_data")
    if table is None:
        raise HTTPException(status_code=500, detail="Depth database table not found")
    return OutlierDetectionService(db, table)


@router.post(
    "/datasets",
    response_model=OutlierDetectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run outlier detection pipeline and store dataset",
)
async def run_outlier_detection(
    request: OutlierDetectionRequest,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),
) -> OutlierDetectionResponse:
    try:
        return service.run_pipeline(request, created_by=current_user.id)
    except OutlierDetectionError as exc:
        logger.error("Outlier pipeline error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failures
        logger.exception("Unexpected error running outlier pipeline")
        raise HTTPException(status_code=500, detail="Failed to execute pipeline") from exc


@router.get(
    "/datasets",
    response_model=List[ProcessedDatasetSummary],
    summary="List processed datasets for a well",
)
async def list_processed_datasets(
    well_id: int = Query(..., description="Well ID"),
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> List[ProcessedDatasetSummary]:
    _ = current_user  # ensure auth
    return service.list_datasets(well_id)


@router.get(
    "/datasets/{dataset_id}",
    response_model=ProcessedDatasetDetail,
    summary="Get processed dataset detail",
)
async def get_processed_dataset(
    dataset_id: int,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ProcessedDatasetDetail:
    _ = current_user
    dataset = service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get(
    "/datasets/{dataset_id}/data",
    response_model=ProcessedDataResponse,
    summary="Get processed data records",
)
async def get_processed_data(
    dataset_id: int,
    include_outliers: bool = Query(
        default=False,
        description="Include rows flagged as outliers",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number for paginated data",
    ),
    page_size: int = Query(
        default=500,
        ge=10,
        le=5000,
        description="Number of records per page",
    ),
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ProcessedDataResponse:
    _ = current_user
    return service.get_dataset_data(
        dataset_id,
        include_outliers=include_outliers,
        page=page,
        page_size=page_size,
    )


# NOTE: Explicit response_model=None is required to avoid FastAPI assuming a body for 204 responses.
@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete processed dataset",
    response_class=Response,
    response_model=None,
)
async def delete_processed_dataset(
    dataset_id: int,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> Response:
    _ = current_user
    deleted = service.delete_dataset(dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
