from fastapi import APIRouter, HTTPException, Depends, Query # Componentes de FastAPI para crear endpoints
from sqlalchemy.orm import Session # Session de SQLAlchemy para manejo de sesiones de BD
from typing import Optional # Optional para parámetros opcionales
from app.core.logging import get_logger # Función para obtener logger
from app.db.session import get_db, get_depth_db, db_manager # Funciones para obtener sesión de BD y gestor de BD
from app.db.repositories.well_repository import WellRepository # Repositorio de pozos para operaciones CRUD
from app.db.repositories.data_repository import DataRepository # Repositorio de datos para consultas de datos de perforación
from app.schemas.well import WellListResponse, WellResponse, WellMetadata # Schemas Pydantic para validación y serialización

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)

# Crear router de FastAPI para endpoints de pozos
router = APIRouter()

# Endpoint GET / para listar todos los pozos
@router.get("/", response_model=WellListResponse, summary="List all wells")
# Función asíncrona para listar pozos con paginación y búsqueda
async def list_wells(
    # Parámetro skip: número de registros a saltar (para paginación)
    skip: int = Query(0, ge=0, description="Number of records to skip"),

    # Parámetro limit: máximo de registros a retornar (1-1000)
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),

    # Parámetro search: término de búsqueda opcional para filtrar por nombre
    search: Optional[str] = Query(None, description="Search term for well names"),

    # Inyección de dependencia: sesión de base de datos
    db: Session = Depends(get_db)
):
    # Registrar en log la petición de listado de pozos
    logger.info(f"Fetching wells list (skip={skip}, limit={limit}, search={search})")
    
    # Intentar obtener la lista de pozos
    try:
        # Crear instancia del repositorio de pozos con la sesión de BD
        repo = WellRepository(db)
        
        # Si hay término de búsqueda, filtrar pozos
        if search:
            # Buscar pozos que coincidan con el término
            wells = repo.search(search, limit=limit)

            # Contar total de resultados de búsqueda
            total = len(wells)
        # Si no hay búsqueda, obtener todos los pozos con paginación
        else:
            # Obtener pozos con skip y limit para paginación
            wells = repo.get_all(skip=skip, limit=limit)

            # Contar total de pozos en la base de datos
            total = repo.count()
        
        # Convertir modelos de BD a schemas Pydantic para respuesta
        wells_response = [WellResponse.model_validate(well) for well in wells]
        
        # Retornar respuesta con lista de pozos y metadata de paginación
        return WellListResponse(
            # Total de pozos disponibles
            total=total,

            # Lista de pozos serializados
            wells=wells_response,

            # Número de registros saltados
            skip=skip,

            # Límite de registros retornados
            limit=limit
        )
    # Capturar cualquier excepción durante la consulta
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error fetching wells: {e}")

        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error fetching wells: {str(e)}")

# Endpoint GET /{well_id} para obtener detalles de un pozo específico
@router.get("/{well_id}", response_model=WellMetadata, summary="Get well details")
# Función asíncrona para obtener metadata de un pozo
async def get_well(
    # Parámetro de ruta: ID del pozo a consultar
    well_id: int,

    # Inyección de dependencia: sesión de base de datos
    db: Session = Depends(get_db)
):
    # Registrar en log la petición de detalles del pozo
    logger.info(f"Fetching well details for well_id: {well_id}")
    
    # Intentar obtener metadata del pozo
    try:
        # Crear instancia del repositorio de pozos
        repo = WellRepository(db)

        # Obtener metadata básica del pozo desde la tabla wells
        metadata = repo.get_metadata(well_id)
        
        # Si no se encuentra el pozo
        if not metadata:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"Well {well_id} not found")
        
        # Obtener rango de profundidad desde la base de datos de profundidad
        try:
            # Obtener tabla de datos de profundidad
            depth_table = db_manager.get_depth_table("well_data")
            
            # Si la tabla existe, consultar rango de profundidad
            if depth_table is not None:
                # Obtener sesión de BD de profundidad
                depth_session = next(db_manager.get_depth_session())
            
                # Crear repositorio de datos con la sesión y tabla
                data_repo = DataRepository(depth_session, depth_table)
            
                # Consultar rango de profundidad para este pozo
                depth_range = data_repo.get_depth_range(well_id)
            
                # Agregar rango de profundidad a metadata
                metadata["depth_range"] = depth_range
            
                # Cerrar sesión de BD
                depth_session.close()
        # Si hay error obteniendo rango de profundidad
        except Exception as e:
            # Registrar advertencia
            logger.warning(f"Could not get depth range: {e}")
            
            # Establecer rango de profundidad como None
            metadata["depth_range"] = None
        
        # Obtener columnas disponibles en la base de datos
        try:
            # Obtener diccionario de columnas de profundidad
            depth_columns = db_manager.get_depth_columns()
            
            # Agregar lista de nombres de columnas a metadata
            metadata["available_columns"] = list(depth_columns.keys())
        # Si hay error obteniendo columnas
        except Exception as e:
            # Registrar advertencia
            logger.warning(f"Could not get columns: {e}")
            
            # Establecer lista vacía de columnas
            metadata["available_columns"] = []
        
        # Retornar metadata completa del pozo como schema Pydantic
        return WellMetadata(**metadata)
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error fetching well {well_id}: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error fetching well: {str(e)}")
