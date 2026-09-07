"""
Data repository - Data access layer for well_data table.
Handles queries for both Time and Depth databases.
"""
# Importamos Session de SQLAlchemy para manejo de sesiones de BD
from sqlalchemy.orm import Session
# Importamos select para consultas, and_ para condiciones AND, Table y Column para tablas
from sqlalchemy import select, and_, Table, Column
# Importamos los tipos que usamos en las anotaciones
from typing import List, Dict, Any, Optional
# Importamos la función para obtener el logger
from app.core.logging import get_logger
# Importamos la configuración de la aplicación
from app.core.config import settings

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)


# Definimos el repositorio para las operaciones sobre la tabla well_data
class DataRepository:
    """Repository for well_data table operations."""

    # Inicializamos el repositorio con la sesión de BD y la tabla reflejada
    def __init__(self, session: Session, well_data_table: Table):
        # Guardamos la sesión de BD
        self.session = session
        # Guardamos la tabla reflejada de well_data
        self.table = well_data_table

    # Consultamos datos por rango de profundidad
    def query_by_depth_range(
        self,
        # Guardamos el ID del pozo
        well_id: int,
        # Guardamos la profundidad mínima
        min_depth: float,
        # Guardamos la profundidad máxima
        max_depth: float,
        # Guardamos la lista opcional de columnas a devolver
        columns: Optional[List[str]] = None,
        # Guardamos el límite opcional de registros
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
        # Usamos el límite por defecto de configuración si no se especificó uno
        if limit is None:
            limit = settings.DEFAULT_QUERY_LIMIT

        # Limitamos al máximo permitido por seguridad
        limit = min(limit, settings.MAX_QUERY_LIMIT)

        # Determinamos qué columnas seleccionar
        if columns:
            # Validamos que las columnas existan en la tabla
            # Armamos el set de columnas disponibles
            available_cols = {col.name for col in self.table.columns}
            # Filtramos solo las columnas válidas
            valid_cols = [col for col in columns if col in available_cols]
            # Armamos la lista de objetos Column para el SELECT
            select_cols = [self.table.c[col] for col in valid_cols]
        # Seleccionamos todas las columnas si no se especificaron
        else:
            select_cols = [self.table]

        # Construimos la consulta
        # Obtenemos la columna de profundidad (bit_depth_feet o similar)
        depth_col = self._get_depth_column()

        # Devolvemos lista vacía si no encontramos columna de profundidad
        if depth_col is None:
            logger.error("Depth column not found in table")
            return []

        # Armamos la consulta SELECT con filtros WHERE
        query = select(*select_cols).where(
            # Combinamos las condiciones: well_id y rango de profundidad
            and_(
                # Filtramos por ID de pozo
                self.table.c.well_id == well_id,
                # Exigimos profundidad mayor o igual al mínimo
                depth_col >= min_depth,
                # Exigimos profundidad menor o igual al máximo
                depth_col <= max_depth
            )
        # Limitamos el número de resultados
        ).limit(limit)

        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos todos los resultados como mappings (diccionarios)
        rows = result.mappings().all()

        # Registramos en el log la consulta realizada
        logger.info(
            f"Query by depth: well_id={well_id}, "
            f"depth=[{min_depth}, {max_depth}], "
            f"returned {len(rows)} rows"
        )

        # Convertimos los mappings a diccionarios y los devolvemos
        return [dict(row) for row in rows]

    # Obtenemos una muestra de datos para vista previa
    def query_sample(
        self,
        # Guardamos el ID del pozo
        well_id: int,
        # Guardamos el tamaño de la muestra
        sample_size: int = 100,
        # Guardamos el rango opcional de profundidad (min, max) — cualquiera puede ser None
        depth_range: Optional[tuple] = None,
        # Guardamos el rango opcional de años (yr_min, yr_max) — cualquiera puede ser None
        date_range: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get a sample of data for preview.

        Args:
            well_id: The well ID
            sample_size: Number of records to retrieve
            depth_range: Optional (min_depth, max_depth) filter, applied in SQL
                before the LIMIT so a narrow depth window isn't starved by the cap.
            date_range: Optional (year_min, year_max) filter over yyyy_mm_dd.

        Returns:
            List of dictionaries with sample data
        """
        # Usamos el tamaño de muestra solicitado sin límite artificial

        # Armamos las condiciones WHERE: siempre filtramos por pozo, más rango de profundidad/fecha si se piden
        conditions = [self.table.c.well_id == well_id]

        # Agregamos el filtro de profundidad si se pidió
        if depth_range is not None:
            depth_col = None
            # Buscamos la primera columna de profundidad disponible
            for name in ("bit_depth_feet", "hole_depth_feet"):
                if name in self.table.c:
                    depth_col = self.table.c[name]
                    break
            if depth_col is not None:
                lo, hi = depth_range
                if lo is not None:
                    conditions.append(depth_col >= lo)
                if hi is not None:
                    conditions.append(depth_col <= hi)

        # Agregamos el filtro de fecha si se pidió y la columna existe
        if date_range is not None and "yyyy_mm_dd" in self.table.c:
            yr_lo, yr_hi = date_range
            date_col = self.table.c["yyyy_mm_dd"]
            if yr_lo is not None:
                conditions.append(date_col >= "%04d/01/01" % yr_lo)
            if yr_hi is not None:
                conditions.append(date_col <= "%04d/12/31" % yr_hi)

        # Armamos la consulta SELECT de toda la tabla con filtros y límite
        query = select(self.table).where(
            and_(*conditions)
        # Limitamos al tamaño de muestra solicitado
        ).limit(sample_size)

        # Ordenamos por id si existe: sin ORDER BY la muestra no sería determinista
        # y los pipelines de procesamiento/outliers no serían reproducibles
        if "id" in self.table.c:
            query = query.order_by(self.table.c.id)

        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos todos los resultados como mappings
        rows = result.mappings().all()

        # Registramos en el log la consulta de muestra
        logger.info(f"Sample query: well_id={well_id}, returned {len(rows)} rows")

        # Convertimos los mappings a diccionarios y los devolvemos
        return [dict(row) for row in rows]

    # Obtenemos el rango de profundidad (min y max) de un pozo
    def get_depth_range(self, well_id: int) -> Optional[Dict[str, float]]:
        """
        Get min and max depth for a well.

        Args:
            well_id: The well ID

        Returns:
            Dictionary with min_depth and max_depth
        """
        # Obtenemos la columna de profundidad
        depth_col = self._get_depth_column()

        # Devolvemos None si no existe columna de profundidad
        if depth_col is None:
            return None

        # Importamos func para las funciones agregadas de SQL
        from sqlalchemy import func

        # Armamos la consulta SELECT con las funciones MIN y MAX
        query = select(
            # Calculamos la profundidad mínima
            func.min(depth_col).label("min_depth"),
            # Calculamos la profundidad máxima
            func.max(depth_col).label("max_depth")
        # Filtramos por ID de pozo
        ).where(self.table.c.well_id == well_id)

        # Ejecutamos la consulta en la sesión de BD
        result = self.session.execute(query)
        # Obtenemos la primera (y única) fila
        row = result.first()

        # Devolvemos el diccionario con min y max si hay resultado
        if row:
            return {
                # Guardamos la profundidad mínima
                "min_depth": row.min_depth,
                # Guardamos la profundidad máxima
                "max_depth": row.max_depth
            }
        # Devolvemos None si no hay datos
        return None

    # Obtenemos la lista de columnas disponibles en la tabla
    def get_available_columns(self) -> List[str]:
        """
        Get list of available columns in the table.

        Returns:
            List of column names
        """
        # Devolvemos la lista de nombres de todas las columnas de la tabla
        return [col.name for col in self.table.columns]

    # Obtenemos la columna de profundidad de la tabla (método privado)
    def _get_depth_column(self) -> Optional[Column]:
        """Get the depth column from the table."""
        # Probamos los nombres comunes de columna de profundidad
        depth_names = ["bit_depth_feet", "Bit Depth (feet)", "depth", "Depth"]

        # Recorremos los nombres posibles
        for name in depth_names:
            # Devolvemos la columna si el nombre existe en la tabla
            if name in self.table.c:
                return self.table.c[name]

        # Devolvemos None si no encontramos ninguna
        return None
