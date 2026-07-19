from fastapi import APIRouter, Depends
from app.api.v1.endpoints import wells, data, processing, auth, users, outliers, exports
from app.core.deps import get_current_user

api_router = APIRouter()

# Todos los routers de datos exigen usuario autenticado; auth queda público
# para permitir el login.
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(
    wells.router, prefix="/wells", tags=["Wells"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    data.router, prefix="/data", tags=["Data"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    processing.router, prefix="/processing", tags=["Processing"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(outliers.router, prefix="/outliers", tags=["Outlier Detection"])
api_router.include_router(
    exports.router, prefix="/exports", tags=["Exports"],
    dependencies=[Depends(get_current_user)],
)
