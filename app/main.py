# 
import traceback # 
from pathlib import Path # 
from fastapi import FastAPI, Request # 
from fastapi.middleware.cors import CORSMiddleware # 
from fastapi.responses import JSONResponse, RedirectResponse # 
from fastapi.staticfiles import StaticFiles # 
from app.core.config import settings # 
from app.core.deps import NotAuthenticatedException # 
from app.core.logging import setup_logging, get_logger # 
from app.web import web_router # 

# 
setup_logging()

# 
logger = get_logger(__name__)

# 
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Drilling data analysis and visualization")

# 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])

# 
app.include_router(web_router)

# 
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 
@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    # 
    next_path = request.url.path
    
    # 
    return RedirectResponse(url=f"/login?next={next_path}", status_code=302)

# 
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    
    # 
    logger.error(f"Unhandled error on {request.method} {request.url}: {''.join(tb)}")
    
    # 
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# 
@app.on_event("startup")
async def startup_event():
    # 
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # 
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    # 
    logger.info(f"Debug mode: {settings.DEBUG}")

    #
    from app.db.session import db_manager

    #
    try:
        #
        db_manager.initialize()

        #
        logger.info("Database connections initialized successfully")
    #
    except Exception as e:
        #
        logger.error(f"Failed to initialize database connections: {e}")

        #
        logger.warning("Application will continue but database endpoints may not work")

    # Importamos aquí (no arriba) porque el manager necesita que db_manager ya esté inicializado
    from app.services.realtime.ingest_manager import realtime_manager

    # Reanudamos las conexiones WITS0 que hayan quedado habilitadas de una corrida anterior
    try:
        await realtime_manager.start()
    except Exception as e:
        # Un taladro caído/inalcanzable no debe impedir que el resto de la app arranque
        logger.error(f"Failed to start realtime ingest manager: {e}")

#
@app.on_event("shutdown")
async def shutdown_event():
    #
    logger.info("Shutting down application")

    # Importamos aquí (mismo motivo que en el arranque) para cerrar las conexiones WITS0 en curso
    from app.services.realtime.ingest_manager import realtime_manager

    # Cerramos las conexiones WITS0 antes que la base de datos, ya que cada una necesita escribir en ella
    try:
        await realtime_manager.stop()
    except Exception as e:
        logger.error(f"Error stopping realtime ingest manager: {e}")

    #
    from app.db.session import db_manager

    #
    try:
        #
        db_manager.close()

        #
        logger.info("Database connections closed")
    #
    except Exception as e:
        #
        logger.error(f"Error closing database connections: {e}")

# 
@app.get("/health", tags=["Health"])
async def health_check():
    # 
    # Devolvemos "ok", el mismo valor que las otras cuatro aplicaciones, para
    # que un balanceador o un chequeo de despliegue pueda tratarlas por igual
    return {"status": "ok", "version": settings.APP_VERSION}
