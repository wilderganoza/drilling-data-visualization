"""
Well repository - Data access layer for wells table.
"""
# Importar Session de SQLAlchemy para manejo de sesiones de BD
from sqlalchemy.orm import Session
# Importar select para consultas, func para funciones SQL
from sqlalchemy import select, func
# Importar tipos para anotaciones
from typing import List, Optional, Dict, Any
# Importar modelo Well
from app.db.models import Well
# Importar función para obtener logger
from app.core.logging import get_logger

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)


# Clase repositorio para operaciones CRUD en la tabla wells
class WellRepository:
    """Repository for wells table operations."""
    
    # Constructor del repositorio
    def __init__(self, session: Session):
        # Almacenar sesión de BD para usar en todos los métodos
        self.session = session
    
    # Método para obtener todos los pozos con paginación
    def get_all(self, skip: int = 0, limit: int = 1000) -> List[Well]:
        """
        Get all wells with pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Well objects
        """
        # Crear consulta SELECT con offset y limit para paginación
        query = select(Well).offset(skip).limit(limit)
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener todos los resultados como objetos Well
        wells = result.scalars().all()
        # Registrar en log la cantidad de pozos recuperados
        logger.info(f"Retrieved {len(wells)} wells (skip={skip}, limit={limit})")
        # Retornar lista de pozos
        return wells
    
    # Método para obtener un pozo por su ID
    def get_by_id(self, well_id: int) -> Optional[Well]:
        """
        Get a well by ID.
        
        Args:
            well_id: The well ID
            
        Returns:
            Well object or None if not found
        """
        # Crear consulta SELECT con filtro WHERE por ID
        query = select(Well).where(Well.id == well_id)
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener un resultado o None si no existe
        well = result.scalar_one_or_none()
        
        # Si se encontró el pozo, registrar en log
        if well:
            logger.info(f"Retrieved well: {well.well_name} (ID: {well_id})")
        # Si no se encontró, registrar advertencia
        else:
            logger.warning(f"Well not found: ID {well_id}")
        
        # Retornar pozo o None
        return well
    
    # Método para obtener un pozo por su nombre
    def get_by_name(self, well_name: str) -> Optional[Well]:
        """
        Get a well by name.
        
        Args:
            well_name: The well name
            
        Returns:
            Well object or None if not found
        """
        # Crear consulta SELECT con filtro WHERE por nombre
        query = select(Well).where(Well.well_name == well_name)
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Retornar un resultado o None si no existe
        return result.scalar_one_or_none()
    
    # Método para contar el total de pozos
    def count(self) -> int:
        """
        Get total count of wells.
        
        Returns:
            Total number of wells
        """
        # Crear consulta SELECT COUNT(id)
        query = select(func.count(Well.id))
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener el valor escalar (número)
        count = result.scalar()
        # Registrar en log el conteo total
        logger.info(f"Total wells count: {count}")
        # Retornar conteo
        return count
    
    # Método para obtener metadata de un pozo
    def get_metadata(self, well_id: int) -> Optional[Dict[str, Any]]:
        """
        Get well metadata.
        
        Args:
            well_id: The well ID
            
        Returns:
            Dictionary with well metadata
        """
        # Obtener pozo por ID
        well = self.get_by_id(well_id)
        # Si no existe, retornar None
        if not well:
            return None
        
        # Retornar diccionario con metadata del pozo
        return {
            # ID del pozo
            "id": well.id,
            # Nombre del pozo
            "well_name": well.well_name,
            # Nombre del archivo original
            "filename": well.filename,
            # Total de filas importadas
            "total_rows": well.total_rows,
            # Total de columnas importadas
            "total_columns": well.total_columns,
            # Fecha de importación en formato ISO (o None)
            "date_imported": well.date_imported.isoformat() if well.date_imported else None
        }
    
    # Método para buscar pozos por nombre
    def search(self, search_term: str, limit: int = 100) -> List[Well]:
        """
        Search wells by name.
        
        Args:
            search_term: Search term to match against well names
            limit: Maximum number of results
            
        Returns:
            List of matching Well objects
        """
        # Crear consulta SELECT con filtro LIKE para búsqueda parcial
        query = select(Well).where(
            # Buscar nombres que contengan el término de búsqueda
            Well.well_name.like(f"%{search_term}%")
        # Limitar número de resultados
        ).limit(limit)
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener todos los resultados como objetos Well
        wells = result.scalars().all()
        # Registrar en log la cantidad de resultados
        logger.info(f"Search '{search_term}' returned {len(wells)} results")
        # Retornar lista de pozos encontrados
        return wells
