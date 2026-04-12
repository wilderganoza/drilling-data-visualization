from fastapi import APIRouter
from app.api.v1.endpoints import wells, data, processing, auth, users, outliers, exports

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(wells.router, prefix="/wells", tags=["Wells"])
api_router.include_router(data.router, prefix="/data", tags=["Data"])
api_router.include_router(processing.router, prefix="/processing", tags=["Processing"])
api_router.include_router(outliers.router, prefix="/outliers", tags=["Outlier Detection"])
api_router.include_router(exports.router, prefix="/exports", tags=["Exports"])
