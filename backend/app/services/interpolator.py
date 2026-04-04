"""
Time-Depth interpolation service - Synchronize time-based and depth-based data.
"""
import pandas as pd # Pandas para manipulación de datos
import numpy as np # NumPy para operaciones numéricas
from typing import List, Optional, Literal # Tipos para anotaciones
from scipy.interpolate import interp1d # Función de interpolación de SciPy
from app.core.logging import get_logger # Función para obtener logger

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)


# Clase de servicio para interpolación entre datos basados en tiempo y profundidad
class TimeDepthInterpolator:
    
    # Método estático para interpolar datos basados en tiempo a puntos de profundidad específicos
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
        # Verificar que la columna de profundidad existe
        if depth_col not in time_df.columns:
            logger.error(f"Depth column '{depth_col}' not found in time data")
            return pd.DataFrame()
        
        # Ordenar por profundidad
        time_df_sorted = time_df.sort_values(depth_col).copy()
        
        # Remover duplicados y valores NaN en profundidad
        time_df_sorted = time_df_sorted.dropna(subset=[depth_col])
        time_df_sorted = time_df_sorted.drop_duplicates(subset=[depth_col], keep='first')
        
        # Verificar que hay suficientes puntos para interpolación
        if len(time_df_sorted) < 2:
            logger.error("Not enough data points for interpolation")
            return pd.DataFrame()
        
        # Determinar columnas a interpolar
        if value_cols is None:
            # Seleccionar todas las columnas numéricas
            value_cols = time_df_sorted.select_dtypes(include=[np.number]).columns.tolist()
            # Excluir la columna de profundidad
            value_cols = [col for col in value_cols if col != depth_col]
        
        # Preparar DataFrame de resultados
        result = pd.DataFrame({depth_col: target_depths})
        
        # Obtener profundidades de origen
        source_depths = time_df_sorted[depth_col].values
        
        # Interpolar cada columna
        for col in value_cols:
            # Verificar que la columna existe
            if col not in time_df_sorted.columns:
                continue
            
            # Obtener valores y remover NaN
            values = time_df_sorted[col].values
            valid_mask = ~np.isnan(values)
            
            # Verificar que hay suficientes valores válidos
            if valid_mask.sum() < 2:
                logger.warning(f"Not enough valid data in '{col}' for interpolation")
                continue
            
            # Obtener profundidades y valores válidos
            valid_depths = source_depths[valid_mask]
            valid_values = values[valid_mask]
            
            try:
                # Crear función de interpolación
                # Cúbica requiere al menos 4 puntos
                if method == 'cubic' and len(valid_depths) < 4:
                    method_used = 'linear'
                else:
                    method_used = method
                
                # Crear función de interpolación usando scipy
                f = interp1d(
                    valid_depths, valid_values,
                    kind=method_used,
                    bounds_error=False,
                    fill_value='extrapolate'
                )
                
                # Interpolar a profundidades objetivo
                result[col] = f(target_depths)
                
            except Exception as e:
                logger.warning(f"Failed to interpolate '{col}': {e}")
                continue
        
        # Registrar en log la operación
        logger.info(
            f"Interpolated {len(value_cols)} columns to {len(target_depths)} depth points "
            f"using {method} method"
        )
        
        # Retornar DataFrame con valores interpolados
        return result
    
    # Método estático para interpolar datos basados en profundidad a puntos de tiempo específicos
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
        # Verificar que la columna de tiempo existe
        if time_col not in depth_df.columns:
            logger.error(f"Time column '{time_col}' not found in depth data")
            return pd.DataFrame()
        
        # Convertir tiempo a numérico para interpolación
        depth_df_sorted = depth_df.copy()
        
        # Intentar parsear columna de tiempo
        try:
            # Convertir a datetime y luego a segundos (Unix timestamp)
            depth_df_sorted['_time_numeric'] = pd.to_datetime(
                depth_df_sorted[time_col]
            ).astype(np.int64) / 10**9
        except Exception as e:
            logger.error(f"Failed to parse time column: {e}")
            return pd.DataFrame()
        
        # Ordenar por tiempo
        depth_df_sorted = depth_df_sorted.sort_values('_time_numeric')
        
        # Remover duplicados y valores NaN en tiempo
        depth_df_sorted = depth_df_sorted.dropna(subset=['_time_numeric'])
        depth_df_sorted = depth_df_sorted.drop_duplicates(subset=['_time_numeric'], keep='first')
        
        # Verificar que hay suficientes puntos para interpolación
        if len(depth_df_sorted) < 2:
            logger.error("Not enough data points for interpolation")
            return pd.DataFrame()
        
        # Convertir tiempos objetivo a numérico
        try:
            target_times_numeric = pd.to_datetime(target_times).astype(np.int64) / 10**9
        except Exception as e:
            logger.error(f"Failed to parse target times: {e}")
            return pd.DataFrame()
        
        # Determinar columnas a interpolar
        if value_cols is None:
            # Seleccionar todas las columnas numéricas
            value_cols = depth_df_sorted.select_dtypes(include=[np.number]).columns.tolist()
            # Excluir columnas de tiempo
            value_cols = [col for col in value_cols if col not in [time_col, '_time_numeric']]
        
        # Preparar DataFrame de resultados
        result = pd.DataFrame({time_col: target_times})
        
        # Obtener tiempos de origen
        source_times = depth_df_sorted['_time_numeric'].values
        
        # Interpolar cada columna
        for col in value_cols:
            # Verificar que la columna existe
            if col not in depth_df_sorted.columns:
                continue
            
            # Obtener valores
            values = depth_df_sorted[col].values
            valid_mask = ~np.isnan(values)
            
            # Verificar que hay suficientes valores válidos
            if valid_mask.sum() < 2:
                logger.warning(f"Not enough valid data in '{col}' for interpolation")
                continue
            
            # Obtener tiempos y valores válidos
            valid_times = source_times[valid_mask]
            valid_values = values[valid_mask]
            
            try:
                # Cúbica requiere al menos 4 puntos
                if method == 'cubic' and len(valid_times) < 4:
                    method_used = 'linear'
                else:
                    method_used = method
                
                # Crear función de interpolación
                f = interp1d(
                    valid_times, valid_values,
                    kind=method_used,
                    bounds_error=False,
                    fill_value='extrapolate'
                )
                
                # Interpolar a tiempos objetivo
                result[col] = f(target_times_numeric)
                
            except Exception as e:
                logger.warning(f"Failed to interpolate '{col}': {e}")
                continue
        
        # Registrar en log la operación
        logger.info(
            f"Interpolated {len(value_cols)} columns to {len(target_times)} time points "
            f"using {method} method"
        )
        
        # Retornar DataFrame con valores interpolados
        return result
    
    # Método estático para combinar datos basados en tiempo y profundidad
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
        # Verificar que la columna de combinación existe en ambos DataFrames
        if merge_on not in time_df.columns or merge_on not in depth_df.columns:
            logger.error(f"Merge column '{merge_on}' not found in both DataFrames")
            return pd.DataFrame()
        
        # Método de coincidencia más cercana
        if method == 'nearest':
            # Ordenar ambos DataFrames por la columna de combinación
            time_sorted = time_df.sort_values(merge_on).copy()
            depth_sorted = depth_df.sort_values(merge_on).copy()
            
            # Usar merge_asof de pandas para coincidencia más cercana
            merged = pd.merge_asof(
                time_sorted, depth_sorted,
                on=merge_on,
                direction='nearest',
                tolerance=tolerance,
                suffixes=('_time', '_depth')
            )
            
            # Registrar en log la operación
            logger.info(
                f"Merged time and depth data on '{merge_on}' "
                f"with tolerance={tolerance} ft"
            )
            
        # Método de interpolación
        elif method == 'interpolate':
            # Interpolar datos de profundidad a profundidades de datos de tiempo
            target_depths = time_df[merge_on].dropna().unique()
            
            # Interpolar datos de profundidad
            interpolated = TimeDepthInterpolator.interpolate_to_depth(
                depth_df, target_depths, depth_col=merge_on
            )
            
            # Combinar con datos de tiempo
            merged = pd.merge(
                time_df, interpolated,
                on=merge_on,
                how='left',
                suffixes=('_time', '_depth')
            )
            
            # Registrar en log la operación
            logger.info(f"Merged time and depth data using interpolation")
        # Método desconocido
        else:
            logger.error(f"Unknown merge method: {method}")
            return pd.DataFrame()
        
        # Retornar DataFrame combinado
        return merged
    
    # Método estático para crear una grilla uniforme de profundidad para interpolación
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
        # Crear array de profundidades con numpy.arange
        depths = np.arange(min_depth, max_depth + step, step)
        # Registrar en log la operación
        logger.info(
            f"Created uniform depth grid: {min_depth} to {max_depth} ft "
            f"with step={step} ft ({len(depths)} points)"
        )
        # Retornar lista de profundidades
        return depths.tolist()
