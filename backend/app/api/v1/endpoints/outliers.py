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
    OutlierPreviewResponse,
    PcaPreviewResponse,
    ProcessedDataResponse,
    ProcessedDatasetDetail,
    ProcessedDatasetSummary,
    ScalingPreviewResponse,
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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute pipeline: {type(exc).__name__}: {exc}",
        ) from exc


@router.post(
    "/scaling-preview",
    response_model=ScalingPreviewResponse,
    summary="Preview sklearn-scaled values for the selected variables",
)
async def preview_scaling(
    request: OutlierDetectionRequest,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),
) -> ScalingPreviewResponse:
    _ = current_user
    try:
        return service.preview_scaling(request)
    except OutlierDetectionError as exc:
        logger.error("Scaling preview error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error running scaling preview")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute scaling preview: {type(exc).__name__}: {exc}",
        ) from exc


@router.post(
    "/pca-preview",
    response_model=PcaPreviewResponse,
    summary="Preview sklearn PCA scores and explained variance",
)
async def preview_pca(
    request: OutlierDetectionRequest,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),
) -> PcaPreviewResponse:
    _ = current_user
    try:
        return service.preview_pca(request)
    except OutlierDetectionError as exc:
        logger.error("PCA preview error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error running PCA preview")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute PCA preview: {type(exc).__name__}: {exc}",
        ) from exc


@router.post(
    "/preview",
    response_model=OutlierPreviewResponse,
    summary="Run the pipeline without persisting (preview metrics and scatter)",
)
async def preview_outlier_detection(
    request: OutlierDetectionRequest,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),
) -> OutlierPreviewResponse:
    _ = current_user
    try:
        return service.preview_pipeline(request)
    except OutlierDetectionError as exc:
        logger.error("Outlier preview error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error running outlier preview")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute preview: {type(exc).__name__}: {exc}",
        ) from exc


@router.put(
    "/datasets/{dataset_id}",
    response_model=OutlierDetectionResponse,
    summary="Re-run pipeline replacing an existing dataset in place",
)
async def rerun_outlier_detection(
    dataset_id: int,
    request: OutlierDetectionRequest,
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),
) -> OutlierDetectionResponse:
    try:
        return service.run_pipeline(
            request,
            created_by=current_user.id,
            replace_dataset_id=dataset_id,
        )
    except OutlierDetectionError as exc:
        logger.error("Outlier pipeline error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error re-running outlier pipeline")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute pipeline: {type(exc).__name__}: {exc}",
        ) from exc


@router.get(
    "/datasets-all",
    response_model=List[ProcessedDatasetSummary],
    summary="List all processed datasets across wells",
)
async def list_all_processed_datasets(
    service: OutlierDetectionService = Depends(get_outlier_service),
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> List[ProcessedDatasetSummary]:
    _ = current_user
    return service.list_all_datasets()


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
