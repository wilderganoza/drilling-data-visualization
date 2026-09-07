"""
Time-Depth interpolation service - Synchronize time-based and depth-based data.
"""
# Importamos pandas para manipular los DataFrames de datos de perforación
import pandas as pd
# Importamos numpy para operaciones numéricas (arrays, NaN, máscaras)
import numpy as np
# Importamos los tipos que usamos para anotar los parámetros de las funciones
from typing import List, Optional, Literal
# Importamos interp1d de scipy, la función que hace la interpolación en sí
from scipy.interpolate import interp1d
# Importamos la función para obtener el logger del módulo
from app.core.logging import get_logger

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)


# Definimos la clase de servicio para interpolación entre datos basados en tiempo y profundidad
class TimeDepthInterpolator:

    # Definimos el método estático que interpola datos basados en tiempo a puntos de profundidad específicos
    @staticmethod
    def interpolate_to_depth(
        time_df: pd.DataFrame, # DataFrame con datos basados en tiempo
        target_depths: List[float], # Lista de profundidades objetivo
        time_col: str = 'yyyy_mm_dd', # Columna de tiempo
        depth_col: str = 'bit_depth_feet', # Columna de profundidad
        value_cols: Optional[List[str]] = None, # Columnas a interpolar
        method: Literal['linear', 'nearest', 'cubic'] = 'linear' # Método de interpolación
    ) -> pd.DataFrame:
        """
        Interpolate time-based data to specific depth points.

        Args:
            time_df: DataFrame with time-based data
            target_depths: List of depth values to interpolate to
            time_col: Time column name
            depth_col: Depth column name in time_df
            value_cols: Columns to interpolate (None = all numeric columns)
            method: Interpolation method

        Returns:
            DataFrame with interpolated values at target depths
        """
        # Verificamos que la columna de profundidad exista en el DataFrame de entrada
        if depth_col not in time_df.columns:
            logger.error(f"Depth column '{depth_col}' not found in time data")
            return pd.DataFrame()

        # Ordenamos por profundidad porque interp1d necesita puntos de origen ordenados
        time_df_sorted = time_df.sort_values(depth_col).copy()

        # Removemos las filas sin profundidad, no las podemos usar como punto de origen
        time_df_sorted = time_df_sorted.dropna(subset=[depth_col])
        # Removemos duplicados en profundidad, quedándonos con la primera ocurrencia
        time_df_sorted = time_df_sorted.drop_duplicates(subset=[depth_col], keep='first')

        # Verificamos que queden al menos 2 puntos, mínimo indispensable para interpolar
        if len(time_df_sorted) < 2:
            logger.error("Not enough data points for interpolation")
            return pd.DataFrame()

        # Determinamos qué columnas vamos a interpolar
        if value_cols is None:
            # Si no nos indicaron columnas, seleccionamos todas las numéricas
            value_cols = time_df_sorted.select_dtypes(include=[np.number]).columns.tolist()
            # Excluimos la columna de profundidad porque es el eje, no un valor a interpolar
            value_cols = [col for col in value_cols if col != depth_col]

        # Preparamos el DataFrame de resultados con las profundidades objetivo
        result = pd.DataFrame({depth_col: target_depths})

        # Obtenemos las profundidades de origen como array de numpy
        source_depths = time_df_sorted[depth_col].values

        # Interpolamos cada columna de valores por separado
        for col in value_cols:
            # Verificamos que la columna todavía exista (por si el filtro previo la eliminó)
            if col not in time_df_sorted.columns:
                continue

            # Obtenemos los valores de la columna y detectamos cuáles son válidos (no NaN)
            values = time_df_sorted[col].values
            valid_mask = ~np.isnan(values)

            # Verificamos que haya al menos 2 valores válidos para poder interpolar
            if valid_mask.sum() < 2:
                logger.warning(f"Not enough valid data in '{col}' for interpolation")
                continue

            # Nos quedamos solo con las profundidades y valores válidos
            valid_depths = source_depths[valid_mask]
            valid_values = values[valid_mask]

            try:
                # Creamos la función de interpolación
                # Cúbica requiere al menos 4 puntos, si no alcanza usamos lineal
                if method == 'cubic' and len(valid_depths) < 4:
                    method_used = 'linear'
                else:
                    method_used = method

                # Creamos la función de interpolación usando scipy
                f = interp1d(
                    valid_depths, valid_values,
                    kind=method_used,
                    bounds_error=False,
                    fill_value=np.nan  # NaN fuera del rango medido: no inventamos valores extrapolados
                )

                # Interpolamos a las profundidades objetivo y guardamos el resultado
                result[col] = f(target_depths)

            except Exception as e:
                logger.warning(f"Failed to interpolate '{col}': {e}")
                continue

        # Registramos en el log la operación realizada
        logger.info(
            f"Interpolated {len(value_cols)} columns to {len(target_depths)} depth points "
            f"using {method} method"
        )

        # Devolvemos el DataFrame con los valores interpolados
        return result

    # Definimos el método estático que interpola datos basados en profundidad a puntos de tiempo específicos
    @staticmethod
    def interpolate_to_time(
        depth_df: pd.DataFrame, # DataFrame con datos basados en profundidad
        target_times: List[str], # Lista de tiempos objetivo
        time_col: str = 'yyyy_mm_dd', # Columna de tiempo
        depth_col: str = 'bit_depth_feet', # Columna de profundidad
        value_cols: Optional[List[str]] = None, # Columnas a interpolar
        method: Literal['linear', 'nearest', 'cubic'] = 'linear' # Método de interpolación
    ) -> pd.DataFrame:
        """
        Interpolate depth-based data to specific time points.

        Args:
            depth_df: DataFrame with depth-based data
            target_times: List of time values to interpolate to
            time_col: Time column name in depth_df
            depth_col: Depth column name
            value_cols: Columns to interpolate (None = all numeric columns)
            method: Interpolation method

        Returns:
            DataFrame with interpolated values at target times
        """
        # Verificamos que la columna de tiempo exista en el DataFrame de entrada
        if time_col not in depth_df.columns:
            logger.error(f"Time column '{time_col}' not found in depth data")
            return pd.DataFrame()

        # Copiamos el DataFrame para no modificar el original al agregar la columna numérica de tiempo
        depth_df_sorted = depth_df.copy()

        # Intentamos parsear la columna de tiempo a un valor numérico interpolable
        try:
            # Convertimos a datetime y luego a segundos (timestamp Unix)
            depth_df_sorted['_time_numeric'] = pd.to_datetime(
                depth_df_sorted[time_col]
            ).astype(np.int64) / 10**9
        except Exception as e:
            logger.error(f"Failed to parse time column: {e}")
            return pd.DataFrame()

        # Ordenamos por tiempo porque interp1d necesita puntos de origen ordenados
        depth_df_sorted = depth_df_sorted.sort_values('_time_numeric')

        # Removemos las filas sin tiempo, no las podemos usar como punto de origen
        depth_df_sorted = depth_df_sorted.dropna(subset=['_time_numeric'])
        # Removemos duplicados en tiempo, quedándonos con la primera ocurrencia
        depth_df_sorted = depth_df_sorted.drop_duplicates(subset=['_time_numeric'], keep='first')

        # Verificamos que queden al menos 2 puntos, mínimo indispensable para interpolar
        if len(depth_df_sorted) < 2:
            logger.error("Not enough data points for interpolation")
            return pd.DataFrame()

        # Convertimos los tiempos objetivo al mismo formato numérico
        try:
            target_times_numeric = pd.to_datetime(target_times).astype(np.int64) / 10**9
        except Exception as e:
            logger.error(f"Failed to parse target times: {e}")
            return pd.DataFrame()

        # Determinamos qué columnas vamos a interpolar
        if value_cols is None:
            # Si no nos indicaron columnas, seleccionamos todas las numéricas
            value_cols = depth_df_sorted.select_dtypes(include=[np.number]).columns.tolist()
            # Excluimos las columnas de tiempo porque son el eje, no un valor a interpolar
            value_cols = [col for col in value_cols if col not in [time_col, '_time_numeric']]

        # Preparamos el DataFrame de resultados con los tiempos objetivo
        result = pd.DataFrame({time_col: target_times})

        # Obtenemos los tiempos de origen como array de numpy
        source_times = depth_df_sorted['_time_numeric'].values

        # Interpolamos cada columna de valores por separado
        for col in value_cols:
            # Verificamos que la columna todavía exista
            if col not in depth_df_sorted.columns:
                continue

            # Obtenemos los valores de la columna y detectamos cuáles son válidos (no NaN)
            values = depth_df_sorted[col].values
            valid_mask = ~np.isnan(values)

            # Verificamos que haya al menos 2 valores válidos para poder interpolar
            if valid_mask.sum() < 2:
                logger.warning(f"Not enough valid data in '{col}' for interpolation")
                continue

            # Nos quedamos solo con los tiempos y valores válidos
            valid_times = source_times[valid_mask]
            valid_values = values[valid_mask]

            try:
                # Cúbica requiere al menos 4 puntos, si no alcanza usamos lineal
                if method == 'cubic' and len(valid_times) < 4:
                    method_used = 'linear'
                else:
                    method_used = method

                # Creamos la función de interpolación
                f = interp1d(
                    valid_times, valid_values,
                    kind=method_used,
                    bounds_error=False,
                    fill_value=np.nan  # NaN fuera del rango medido: no inventamos valores extrapolados
                )

                # Interpolamos a los tiempos objetivo y guardamos el resultado
                result[col] = f(target_times_numeric)

            except Exception as e:
                logger.warning(f"Failed to interpolate '{col}': {e}")
                continue

        # Registramos en el log la operación realizada
        logger.info(
            f"Interpolated {len(value_cols)} columns to {len(target_times)} time points "
            f"using {method} method"
        )

        # Devolvemos el DataFrame con los valores interpolados
        return result

    # Definimos el método estático que combina datos basados en tiempo y profundidad
    @staticmethod
    def merge_time_depth_data(
        time_df: pd.DataFrame, # DataFrame con datos basados en tiempo
        depth_df: pd.DataFrame, # DataFrame con datos basados en profundidad
        merge_on: str = 'bit_depth_feet', # Columna para combinar
        tolerance: float = 1.0, # Tolerancia máxima para coincidencia
        method: str = 'nearest' # Método de combinación
    ) -> pd.DataFrame:
        """
        Merge time-based and depth-based data on depth values.

        Args:
            time_df: DataFrame with time-based data
            depth_df: DataFrame with depth-based data
            merge_on: Column to merge on (should be depth)
            tolerance: Maximum difference for matching (in feet)
            method: Merge method ('nearest', 'interpolate')

        Returns:
            Merged DataFrame
        """
        # Verificamos que la columna de combinación exista en ambos DataFrames
        if merge_on not in time_df.columns or merge_on not in depth_df.columns:
            logger.error(f"Merge column '{merge_on}' not found in both DataFrames")
            return pd.DataFrame()

        # Aplicamos el método de coincidencia más cercana
        if method == 'nearest':
            # Ordenamos ambos DataFrames por la columna de combinación
            time_sorted = time_df.sort_values(merge_on).copy()
            depth_sorted = depth_df.sort_values(merge_on).copy()

            # Usamos merge_asof de pandas para hacer la coincidencia más cercana
            merged = pd.merge_asof(
                time_sorted, depth_sorted,
                on=merge_on,
                direction='nearest',
                tolerance=tolerance,
                suffixes=('_time', '_depth')
            )

            # Registramos en el log la operación realizada
            logger.info(
                f"Merged time and depth data on '{merge_on}' "
                f"with tolerance={tolerance} ft"
            )

        # Aplicamos el método de interpolación
        elif method == 'interpolate':
            # Obtenemos las profundidades únicas presentes en los datos de tiempo
            target_depths = time_df[merge_on].dropna().unique()

            # Interpolamos los datos de profundidad a esas profundidades objetivo
            interpolated = TimeDepthInterpolator.interpolate_to_depth(
                depth_df, target_depths, depth_col=merge_on
            )

            # Combinamos el resultado interpolado con los datos de tiempo
            merged = pd.merge(
                time_df, interpolated,
                on=merge_on,
                how='left',
                suffixes=('_time', '_depth')
            )

            # Registramos en el log la operación realizada
            logger.info(f"Merged time and depth data using interpolation")
        # Rechazamos cualquier método que no reconozcamos
        else:
            logger.error(f"Unknown merge method: {method}")
            return pd.DataFrame()

        # Devolvemos el DataFrame combinado
        return merged

    # Definimos el método estático que crea una grilla uniforme de profundidad para interpolación
    @staticmethod
    def create_uniform_depth_grid(
        min_depth: float, # Profundidad mínima
        max_depth: float, # Profundidad máxima
        step: float = 1.0 # Tamaño de paso en pies
    ) -> List[float]:
        """
        Create a uniform depth grid for interpolation.

        Args:
            min_depth: Minimum depth
            max_depth: Maximum depth
            step: Step size in feet

        Returns:
            List of depth values
        """
        # Validamos el rango y el paso antes de crear la grilla
        if step <= 0:
            logger.error(f"Invalid depth step: {step}, must be positive")
            return []
        if min_depth > max_depth:
            logger.error(f"Invalid depth range: min ({min_depth}) > max ({max_depth})")
            return []

        # Creamos el array de profundidades con numpy.arange
        depths = np.arange(min_depth, max_depth + step, step)
        # Registramos en el log la operación realizada
        logger.info(
            f"Created uniform depth grid: {min_depth} to {max_depth} ft "
            f"with step={step} ft ({len(depths)} points)"
        )
        # Devolvemos la lista de profundidades
        return depths.tolist()
