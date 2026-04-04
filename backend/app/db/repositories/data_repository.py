"""
Data repository - Data access layer for well_data table.
Handles queries for both Time and Depth databases.
"""
# Importar Session de SQLAlchemy para manejo de sesiones de BD
from sqlalchemy.orm import Session
# Importar select para consultas, and_ para condiciones AND, Table y Column para tablas
from sqlalchemy import select, and_, Table, Column
# Importar tipos para anotaciones
from typing import List, Dict, Any, Optional
# Importar función para obtener logger
from app.core.logging import get_logger
# Importar configuración de la aplicación
from app.core.config import settings

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)


# Clase repositorio para operaciones en la tabla well_data
class DataRepository:
    """Repository for well_data table operations."""
    
    # Constructor del repositorio
    def __init__(self, session: Session, well_data_table: Table):
        # Almacenar sesión de BD
        self.session = session
        # Almacenar tabla reflejada de well_data
        self.table = well_data_table
    
    # Método para consultar datos por rango de profundidad
    def query_by_depth_range(
        self,
        # ID del pozo
        well_id: int,
        # Profundidad mínima
        min_depth: float,
        # Profundidad máxima
        max_depth: float,
        # Lista opcional de columnas a retornar
        columns: Optional[List[str]] = None,
        # Límite opcional de registros
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query data by depth range.
        
        Args:
            well_id: The well ID
            min_depth: Minimum depth
            max_depth: Maximum depth
            columns: List of column names to retrieve (None = all)
            limit: Maximum number of records (None = use default)
            
        Returns:
            List of dictionaries with query results
        """
        # Si no se especificó límite, usar el por defecto de configuración
        if limit is None:
            limit = settings.DEFAULT_QUERY_LIMIT
        
        # Limitar al máximo permitido por seguridad
        limit = min(limit, settings.MAX_QUERY_LIMIT)
        
        # Determinar qué columnas seleccionar
        if columns:
            # Validar que las columnas existen en la tabla
            # Crear set de columnas disponibles
            available_cols = {col.name for col in self.table.columns}
            # Filtrar solo columnas válidas
            valid_cols = [col for col in columns if col in available_cols]
            # Crear lista de objetos Column para SELECT
            select_cols = [self.table.c[col] for col in valid_cols]
        # Si no se especificaron columnas, seleccionar todas
        else:
            select_cols = [self.table]
        
        # Construir consulta
        # Obtener columna de profundidad (bit_depth_feet o similar)
        depth_col = self._get_depth_column()
        
        # Si no se encuentra columna de profundidad, retornar lista vacía
        if depth_col is None:
            logger.error("Depth column not found in table")
            return []
        
        # Crear consulta SELECT con filtros WHERE
        query = select(*select_cols).where(
            # Condiciones AND: well_id y rango de profundidad
            and_(
                # Filtrar por ID de pozo
                self.table.c.well_id == well_id,
                # Profundidad mayor o igual a mínimo
                depth_col >= min_depth,
                # Profundidad menor o igual a máximo
                depth_col <= max_depth
            )
        # Limitar número de resultados
        ).limit(limit)
        
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener todos los resultados como mappings (diccionarios)
        rows = result.mappings().all()
        
        # Registrar en log la consulta realizada
        logger.info(
            f"Query by depth: well_id={well_id}, "
            f"depth=[{min_depth}, {max_depth}], "
            f"returned {len(rows)} rows"
        )
        
        # Convertir mappings a diccionarios y retornar
        return [dict(row) for row in rows]
    
    # Método para consultar datos por rango de tiempo
    def query_by_time_range(
        self,
        # ID del pozo
        well_id: int,
        # Tiempo inicial (formato YYYY/MM/DD)
        start_time: str,
        # Tiempo final (formato YYYY/MM/DD)
        end_time: str,
        # Lista opcional de columnas a retornar
        columns: Optional[List[str]] = None,
        # Límite opcional de registros
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query data by time range.
        
        Args:
            well_id: The well ID
            start_time: Start time (YYYY/MM/DD format)
            end_time: End time (YYYY/MM/DD format)
            columns: List of column names to retrieve (None = all)
            limit: Maximum number of records
            
        Returns:
            List of dictionaries with query results
        """
        # Si no se especificó límite, usar el por defecto
        if limit is None:
            limit = settings.DEFAULT_QUERY_LIMIT
        
        # Limitar al máximo permitido por seguridad
        limit = min(limit, settings.MAX_QUERY_LIMIT)
        
        # Determinar qué columnas seleccionar
        if columns:
            # Crear set de columnas disponibles
            available_cols = {col.name for col in self.table.columns}
            # Filtrar solo columnas válidas
            valid_cols = [col for col in columns if col in available_cols]
            # Crear lista de objetos Column para SELECT
            select_cols = [self.table.c[col] for col in valid_cols]
        # Si no se especificaron columnas, seleccionar todas
        else:
            select_cols = [self.table]
        
        # Obtener columna de tiempo (yyyy_mm_dd o YYYY/MM/DD)
        time_col = self._get_time_column()
        
        # Si no se encuentra columna de tiempo, retornar lista vacía
        if time_col is None:
            logger.error("Time column not found in table")
            return []
        
        # Crear consulta SELECT con filtros WHERE
        query = select(*select_cols).where(
            # Condiciones AND: well_id y rango de tiempo
            and_(
                # Filtrar por ID de pozo
                self.table.c.well_id == well_id,
                # Tiempo mayor o igual a inicio
                time_col >= start_time,
                # Tiempo menor o igual a fin
                time_col <= end_time
            )
        # Limitar número de resultados
        ).limit(limit)
        
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener todos los resultados como mappings
        rows = result.mappings().all()
        
        # Registrar en log la consulta realizada
        logger.info(
            f"Query by time: well_id={well_id}, "
            f"time=[{start_time}, {end_time}], "
            f"returned {len(rows)} rows"
        )
        
        # Convertir mappings a diccionarios y retornar
        return [dict(row) for row in rows]
    
    # Método para obtener una muestra de datos
    def query_sample(
        self,
        # ID del pozo
        well_id: int,
        # Tamaño de la muestra
        sample_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get a sample of data for preview.
        
        Args:
            well_id: The well ID
            sample_size: Number of records to retrieve
            
        Returns:
            List of dictionaries with sample data
        """
        # Usar el tamaño de muestra solicitado sin límite artificial
        
        # Crear consulta SELECT de toda la tabla con filtro y límite
        query = select(self.table).where(
            # Filtrar por ID de pozo
            self.table.c.well_id == well_id
        # Limitar al tamaño de muestra solicitado
        ).limit(sample_size)
        
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener todos los resultados como mappings
        rows = result.mappings().all()
        
        # Registrar en log la consulta de muestra
        logger.info(f"Sample query: well_id={well_id}, returned {len(rows)} rows")
        
        # Convertir mappings a diccionarios y retornar
        return [dict(row) for row in rows]
    
    # Método para obtener rango de profundidad (min y max) de un pozo
    def get_depth_range(self, well_id: int) -> Optional[Dict[str, float]]:
        """
        Get min and max depth for a well.
        
        Args:
            well_id: The well ID
            
        Returns:
            Dictionary with min_depth and max_depth
        """
        # Obtener columna de profundidad
        depth_col = self._get_depth_column()
        
        # Si no existe columna de profundidad, retornar None
        if depth_col is None:
            return None
        
        # Importar func para funciones agregadas SQL
        from sqlalchemy import func
        
        # Crear consulta SELECT con funciones MIN y MAX
        query = select(
            # Profundidad mínima
            func.min(depth_col).label("min_depth"),
            # Profundidad máxima
            func.max(depth_col).label("max_depth")
        # Filtrar por ID de pozo
        ).where(self.table.c.well_id == well_id)
        
        # Ejecutar consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtener primera (y única) fila
        row = result.first()
        
        # Si hay resultado, retornar diccionario con min y max
        if row:
            return {
                # Profundidad mínima
                "min_depth": row.min_depth,
                # Profundidad máxima
                "max_depth": row.max_depth
            }
        # Si no hay datos, retornar None
        return None
    
    # Método para obtener lista de columnas disponibles en la tabla
    def get_available_columns(self) -> List[str]:
        """
        Get list of available columns in the table.
        
        Returns:
            List of column names
        """
        # Retornar lista de nombres de todas las columnas de la tabla
        return [col.name for col in self.table.columns]
    
    # Método privado para obtener la columna de profundidad de la tabla
    def _get_depth_column(self) -> Optional[Column]:
        """Get the depth column from the table."""
        # Intentar nombres comunes de columna de profundidad
        depth_names = ["bit_depth_feet", "Bit Depth (feet)", "depth", "Depth"]
        
        # Iterar sobre nombres posibles
        for name in depth_names:
            # Si el nombre existe en las columnas de la tabla, retornarlo
            if name in self.table.c:
                return self.table.c[name]
        
        # Si no se encuentra ninguna, retornar None
        return None
    
    # Método privado para obtener la columna de tiempo de la tabla
    def _get_time_column(self) -> Optional[Column]:
        """Get the time column from the table."""
        # Intentar nombres comunes de columna de tiempo
        time_names = ["yyyy_mm_dd", "YYYY/MM/DD", "date", "Date"]
        
        # Iterar sobre nombres posibles
        for name in time_names:
            # Si el nombre existe en las columnas de la tabla, retornarlo
            if name in self.table.c:
                return self.table.c[name]
        
        # Si no se encuentra ninguna, retornar None
        return None
