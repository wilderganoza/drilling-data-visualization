"""
Well repository - Data access layer for wells table.
"""
# Importamos Session de SQLAlchemy para manejo de sesiones de BD
from sqlalchemy.orm import Session
# Importamos select para consultas y func para funciones SQL
from sqlalchemy import select, func
# Importamos los tipos que usamos en las anotaciones
from typing import List, Optional, Dict, Any
# Importamos el modelo Well
from app.models.legacy import SensorWell
# Importamos la función para obtener el logger
from app.core.logging import get_logger

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)


# Definimos el repositorio para las operaciones CRUD sobre la tabla wells
class WellRepository:
    """Repository for wells table operations."""

    # Inicializamos el repositorio con la sesión de base de datos a usar
    def __init__(self, session: Session):
        # Guardamos la sesión de BD para usarla en todos los métodos
        self.session = session

    # Obtenemos todos los pozos con paginación
    def get_all(self, skip: int = 0, limit: int = 1000) -> List[SensorWell]:
        """
        Get all wells with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Well objects
        """
        # Armamos la consulta SELECT con offset y limit para la paginación
        query = select(SensorWell).offset(skip).limit(limit)
        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos todos los resultados como objetos Well
        wells = result.scalars().all()
        # Registramos en el log la cantidad de pozos recuperados
        logger.info(f"Retrieved {len(wells)} wells (skip={skip}, limit={limit})")
        # Devolvemos la lista de pozos
        return wells

    # Buscamos un pozo por su ID
    def get_by_id(self, well_id: int) -> Optional[SensorWell]:
        """
        Get a well by ID.

        Args:
            well_id: The well ID

        Returns:
            Well object or None if not found
        """
        # Armamos la consulta SELECT con filtro WHERE por ID
        query = select(SensorWell).where(SensorWell.id == well_id)
        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos un resultado o None si no existe
        well = result.scalar_one_or_none()

        # Registramos en el log si encontramos el pozo
        if well:
            logger.info(f"Retrieved well: {well.well_name} (ID: {well_id})")
        # Registramos una advertencia si no lo encontramos
        else:
            logger.warning(f"Well not found: ID {well_id}")

        # Devolvemos el pozo o None
        return well

    # Buscamos un pozo por su nombre
    def get_by_name(self, well_name: str) -> Optional[SensorWell]:
        """
        Get a well by name.

        Args:
            well_name: The well name

        Returns:
            Well object or None if not found
        """
        # Armamos la consulta SELECT con filtro WHERE por nombre
        query = select(SensorWell).where(SensorWell.well_name == well_name)
        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Devolvemos un resultado o None si no existe
        return result.scalar_one_or_none()

    # Contamos el total de pozos
    def count(self) -> int:
        """
        Get total count of wells.

        Returns:
            Total number of wells
        """
        # Armamos la consulta SELECT COUNT(id)
        query = select(func.count(SensorWell.id))
        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos el valor escalar (número)
        count = result.scalar()
        # Registramos en el log el conteo total
        logger.info(f"Total wells count: {count}")
        # Devolvemos el conteo
        return count

    # Obtenemos la metadata de un pozo
    def get_metadata(self, well_id: int) -> Optional[Dict[str, Any]]:
        """
        Get well metadata.

        Args:
            well_id: The well ID

        Returns:
            Dictionary with well metadata
        """
        # Obtenemos el pozo por ID
        well = self.get_by_id(well_id)
        # Devolvemos None si no existe
        if not well:
            return None

        # Devolvemos el diccionario con la metadata del pozo
        return {
            # Guardamos el ID del pozo
            "id": well.id,
            # Guardamos el nombre del pozo
            "well_name": well.well_name,
            # Guardamos el nombre del archivo original
            "filename": well.filename,
            # Guardamos el total de filas importadas
            "total_rows": well.total_rows,
            # Guardamos el total de columnas importadas
            "total_columns": well.total_columns,
            # Guardamos la fecha de importación en formato ISO (o None)
            "date_imported": well.date_imported.isoformat() if well.date_imported else None
        }

    # Buscamos pozos por nombre
    def search(self, search_term: str, limit: int = 100) -> List[SensorWell]:
        """
        Search wells by name.

        Args:
            search_term: Search term to match against well names
            limit: Maximum number of results

        Returns:
            List of matching Well objects
        """
        # Escapamos los comodines de LIKE para que el término se busque literal
        escaped_term = search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        # Armamos la consulta SELECT con filtro LIKE para búsqueda parcial
        query = select(SensorWell).where(
            # Buscamos nombres que contengan el término de búsqueda
            SensorWell.well_name.like(f"%{escaped_term}%", escape="\\")
        # Limitamos el número de resultados
        ).limit(limit)
        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos todos los resultados como objetos Well
        wells = result.scalars().all()
        # Registramos en el log la cantidad de resultados
        logger.info(f"Search '{search_term}' returned {len(wells)} results")
        # Devolvemos la lista de pozos encontrados
        return wells
