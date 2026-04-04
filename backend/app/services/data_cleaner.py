import pandas as pd # Pandas para manipulación de datos
import numpy as np # NumPy para operaciones numéricas
from typing import Optional, Literal # Tipos para anotaciones
from app.core.logging import get_logger # Función para obtener logger

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)

# Clase de servicio para limpieza y preprocesamiento de datos de perforación
class DataCleaner:    
    # Método estático para remover outliers de una columna específica
    @staticmethod
    def remove_outliers(
        df: pd.DataFrame,
        column: str, 
        method: Literal['iqr', 'zscore', 'percentile'] = 'iqr', 
        threshold: float = 1.5 
    ) -> pd.DataFrame:
        # Verificar que la columna existe
        if column not in df.columns:
            # 
            logger.warning(f"Column '{column}' not found in DataFrame")
            
            # 
            return df
        
        # Guardar conteo original de registros
        original_count = len(df)
        
        # Método IQR (Interquartile Range)
        if method == 'iqr':
            # Calcular primer cuartil (Q1)
            Q1 = df[column].quantile(0.25)
            
            # Calcular tercer cuartil (Q3)
            Q3 = df[column].quantile(0.75)
            
            # Calcular rango intercuartílico
            IQR = Q3 - Q1
            
            # Calcular límite inferior
            lower_bound = Q1 - threshold * IQR
            
            # Calcular límite superior
            upper_bound = Q3 + threshold * IQR
            
            # Filtrar datos dentro de los límites
            df_clean = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]
            
        # Método Z-score
        elif method == 'zscore':
            # Calcular media
            mean = df[column].mean()
            
            # Calcular desviación estándar
            std = df[column].std()
            
            # Calcular z-scores absolutos
            z_scores = np.abs((df[column] - mean) / std)
            
            # Filtrar datos con z-score menor o igual al umbral
            df_clean = df[z_scores <= threshold]
            
        # Método de percentiles
        elif method == 'percentile':
            # Percentil inferior
            lower_percentile = threshold
            
            # Percentil superior
            upper_percentile = 100 - threshold
            
            # Calcular límite inferior
            lower_bound = df[column].quantile(lower_percentile / 100)
            
            # Calcular límite superior
            upper_bound = df[column].quantile(upper_percentile / 100)
            
            # Filtrar datos dentro de los límites
            df_clean = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]
            
        # Método desconocido
        else:
            logger.error(f"Unknown outlier detection method: {method}")
            return df
        
        # Calcular cantidad de registros removidos
        removed_count = original_count - len(df_clean)
        # Registrar en log la operación
        logger.info(
            f"Removed {removed_count} outliers from '{column}' "
            f"using {method} method ({removed_count/original_count*100:.2f}%)"
        )
        
        # Retornar DataFrame limpio
        return df_clean
    
    # Método estático para llenar valores faltantes en una columna
    @staticmethod
    def fill_missing_values(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Nombre de columna a llenar
        method: Literal['interpolate', 'forward', 'backward', 'mean', 'median', 'zero'] = 'interpolate' # Método de llenado
    ) -> pd.DataFrame:
        """
        Fill missing values in a column.
        
        Args:
            df: DataFrame with data
            column: Column name to fill
            method: Method to fill missing values
                - interpolate: Linear interpolation
                - forward: Forward fill
                - backward: Backward fill
                - mean: Fill with column mean
                - median: Fill with column median
                - zero: Fill with zero
                
        Returns:
            DataFrame with missing values filled
        """
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df
        
        # Contar valores faltantes
        missing_count = df[column].isna().sum()
        
        # Si no hay valores faltantes, retornar sin cambios
        if missing_count == 0:
            logger.info(f"No missing values in '{column}'")
            return df
        
        # Crear copia del DataFrame
        df_filled = df.copy()
        
        # Método de interpolación lineal
        if method == 'interpolate':
            df_filled[column] = df_filled[column].interpolate(method='linear', limit_direction='both')
        # Método de llenado hacia adelante
        elif method == 'forward':
            df_filled[column] = df_filled[column].fillna(method='ffill')
        # Método de llenado hacia atrás
        elif method == 'backward':
            df_filled[column] = df_filled[column].fillna(method='bfill')
        # Llenar con la media
        elif method == 'mean':
            df_filled[column] = df_filled[column].fillna(df[column].mean())
        # Llenar con la mediana
        elif method == 'median':
            df_filled[column] = df_filled[column].fillna(df[column].median())
        # Llenar con ceros
        elif method == 'zero':
            df_filled[column] = df_filled[column].fillna(0)
        # Método desconocido
        else:
            logger.error(f"Unknown fill method: {method}")
            return df
        
        # Calcular cantidad de valores llenados
        filled_count = missing_count - df_filled[column].isna().sum()
        # Registrar en log la operación
        logger.info(
            f"Filled {filled_count} missing values in '{column}' "
            f"using {method} method"
        )
        
        # Retornar DataFrame con valores llenados
        return df_filled
    
    # Método estático para suavizar datos usando promedios móviles
    @staticmethod
    def smooth_data(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Nombre de columna a suavizar
        window: int = 5, # Tamaño de ventana para suavizado
        method: Literal['rolling_mean', 'rolling_median', 'exponential'] = 'rolling_mean' # Método de suavizado
    ) -> pd.DataFrame:
        """
        Smooth data using moving average or exponential smoothing.
        
        Args:
            df: DataFrame with data
            column: Column name to smooth
            window: Window size for smoothing
            method: Smoothing method
                - rolling_mean: Rolling mean
                - rolling_median: Rolling median
                - exponential: Exponential weighted moving average
                
        Returns:
            DataFrame with smoothed data
        """
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df
        
        # Crear copia del DataFrame
        df_smooth = df.copy()
        # Nombre de la nueva columna suavizada
        smoothed_col = f"{column}_smoothed"
        
        # Método de media móvil
        if method == 'rolling_mean':
            df_smooth[smoothed_col] = df_smooth[column].rolling(
                window=window, center=True, min_periods=1
            ).mean()
        # Método de mediana móvil
        elif method == 'rolling_median':
            df_smooth[smoothed_col] = df_smooth[column].rolling(
                window=window, center=True, min_periods=1
            ).median()
        # Método de suavizado exponencial
        elif method == 'exponential':
            df_smooth[smoothed_col] = df_smooth[column].ewm(
                span=window, adjust=False
            ).mean()
        # Método desconocido
        else:
            logger.error(f"Unknown smoothing method: {method}")
            return df
        
        # Registrar en log la operación
        logger.info(
            f"Smoothed '{column}' using {method} with window={window}, "
            f"created column '{smoothed_col}'"
        )
        
        # Retornar DataFrame con columna suavizada
        return df_smooth
    
    # Método estático para validar que valores estén dentro de rangos esperados
    @staticmethod
    def validate_ranges(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Nombre de columna a validar
        min_value: Optional[float] = None, # Valor mínimo válido
        max_value: Optional[float] = None # Valor máximo válido
    ) -> pd.DataFrame:
        """
        Validate that values are within expected ranges.
        
        Args:
            df: DataFrame with data
            column: Column name to validate
            min_value: Minimum valid value (None = no minimum)
            max_value: Maximum valid value (None = no maximum)
            
        Returns:
            DataFrame with invalid values removed
        """
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df
        
        # Guardar conteo original
        original_count = len(df)
        # Crear copia del DataFrame
        df_valid = df.copy()
        
        # Aplicar filtro de valor mínimo si se especificó
        if min_value is not None:
            df_valid = df_valid[df_valid[column] >= min_value]
        
        # Aplicar filtro de valor máximo si se especificó
        if max_value is not None:
            df_valid = df_valid[df_valid[column] <= max_value]
        
        # Calcular cantidad de registros removidos
        removed_count = original_count - len(df_valid)
        
        # Si se removieron registros, registrar en log
        if removed_count > 0:
            logger.info(
                f"Removed {removed_count} invalid values from '{column}' "
                f"(range: {min_value} to {max_value})"
            )
        
        # Retornar DataFrame validado
        return df_valid
    
    # Método estático para aplicar pipeline estándar de limpieza de datos de perforación
    @staticmethod
    def clean_drilling_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply standard cleaning pipeline for drilling data.
        
        Args:
            df: DataFrame with drilling data
            
        Returns:
            Cleaned DataFrame
        """
        # Registrar inicio del pipeline de limpieza
        logger.info("Starting standard drilling data cleaning pipeline")
        
        # Crear copia del DataFrame
        df_clean = df.copy()
        
        # Parámetros comunes de perforación y sus rangos válidos
        cleaning_rules = {
            'Weight on Bit (klbs)': {'min': 0, 'max': 100},
            'weight_on_bit_klbs': {'min': 0, 'max': 100},
            'Rotary RPM (RPM)': {'min': 0, 'max': 300},
            'rotary_rpm_rpm': {'min': 0, 'max': 300},
            'Standpipe Pressure (psi)': {'min': 0, 'max': 10000},
            'standpipe_pressure_psi': {'min': 0, 'max': 10000},
            'Hook Load (klbs)': {'min': 0, 'max': 1000},
            'hook_load_klbs': {'min': 0, 'max': 1000},
            'On Bottom ROP (ft_per_hr)': {'min': 0, 'max': 500},
            'rate_of_penetration_ft_per_hr': {'min': 0, 'max': 500}
        }
        
        # Iterar sobre cada parámetro y aplicar validación de rangos
        for column, rules in cleaning_rules.items():
            # Si la columna existe en el DataFrame
            if column in df_clean.columns:
                # Aplicar validación de rangos
                df_clean = DataCleaner.validate_ranges(
                    df_clean, column, 
                    min_value=rules.get('min'),
                    max_value=rules.get('max')
                )
        
        # Registrar finalización del pipeline
        logger.info("Drilling data cleaning pipeline completed")
        
        # Retornar DataFrame limpio
        return df_clean
