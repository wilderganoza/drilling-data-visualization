# Importamos pandas para manipular los DataFrames de datos de perforación
import pandas as pd
# Importamos numpy para los cálculos numéricos (z-scores, detección de NaN)
import numpy as np
# Importamos los tipos para anotar los métodos (Optional para valores opcionales, Literal para los métodos permitidos)
from typing import Optional, Literal
# Importamos la función para obtener el logger del módulo
from app.core.logging import get_logger

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)

# Definimos la clase de servicio para limpieza y preprocesamiento de datos de perforación
class DataCleaner:
    # Método estático para remover outliers de una columna específica
    @staticmethod
    def remove_outliers(
        df: pd.DataFrame,
        column: str,
        method: Literal['iqr', 'zscore', 'percentile'] = 'iqr',
        threshold: float = 1.5
    ) -> pd.DataFrame:
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            # Registramos la advertencia porque no podemos limpiar una columna inexistente
            logger.warning(f"Column '{column}' not found in DataFrame")

            # Devolvemos el DataFrame sin cambios
            return df

        # Guardamos el conteo original de registros para calcular cuántos removemos después
        original_count = len(df)

        # Método IQR (rango intercuartílico)
        if method == 'iqr':
            # Calculamos el primer cuartil (Q1)
            Q1 = df[column].quantile(0.25)

            # Calculamos el tercer cuartil (Q3)
            Q3 = df[column].quantile(0.75)

            # Calculamos el rango intercuartílico
            IQR = Q3 - Q1

            # Calculamos el límite inferior permitido
            lower_bound = Q1 - threshold * IQR

            # Calculamos el límite superior permitido
            upper_bound = Q3 + threshold * IQR

            # Filtramos los datos que caen dentro de los límites
            df_clean = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]

        # Método Z-score
        elif method == 'zscore':
            # Calculamos la media de la columna
            mean = df[column].mean()

            # Calculamos la desviación estándar de la columna
            std = df[column].std()

            # Con desviación cero o indefinida no hay outliers que remover
            if not std or np.isnan(std):
                df_clean = df
            else:
                # Calculamos los z-scores absolutos de cada valor
                z_scores = np.abs((df[column] - mean) / std)

                # Filtramos los datos cuyo z-score no supera el umbral
                df_clean = df[z_scores <= threshold]

        # Método de percentiles
        elif method == 'percentile':
            # Definimos el percentil inferior a partir del umbral
            lower_percentile = threshold

            # Definimos el percentil superior a partir del umbral
            upper_percentile = 100 - threshold

            # Calculamos el límite inferior según el percentil
            lower_bound = df[column].quantile(lower_percentile / 100)

            # Calculamos el límite superior según el percentil
            upper_bound = df[column].quantile(upper_percentile / 100)

            # Filtramos los datos que caen dentro de los límites
            df_clean = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]

        # Método desconocido: no sabemos cómo limpiar, así que no tocamos los datos
        else:
            logger.error(f"Unknown outlier detection method: {method}")
            return df

        # Calculamos la cantidad de registros removidos
        removed_count = original_count - len(df_clean)
        # Calculamos el porcentaje removido (0 si el DataFrame estaba vacío, para evitar dividir entre cero)
        removed_pct = removed_count / original_count * 100 if original_count else 0.0
        # Registramos en el log el resultado de la operación
        logger.info(
            f"Removed {removed_count} outliers from '{column}' "
            f"using {method} method ({removed_pct:.2f}%)"
        )

        # Devolvemos el DataFrame limpio
        return df_clean

    # Método estático para llenar valores faltantes en una columna
    @staticmethod
    def fill_missing_values(
        df: pd.DataFrame, # DataFrame con los datos
        column: str, # Nombre de la columna a llenar
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
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df

        # Contamos cuántos valores faltantes hay en la columna
        missing_count = df[column].isna().sum()

        # Si no hay valores faltantes, devolvemos el DataFrame sin cambios
        if missing_count == 0:
            logger.info(f"No missing values in '{column}'")
            return df

        # Creamos una copia del DataFrame para no mutar el original
        df_filled = df.copy()

        # Método de interpolación lineal
        if method == 'interpolate':
            df_filled[column] = df_filled[column].interpolate(method='linear', limit_direction='both')
        # Método de llenado hacia adelante (propagamos el último valor válido)
        elif method == 'forward':
            df_filled[column] = df_filled[column].ffill()
        # Método de llenado hacia atrás (propagamos el próximo valor válido)
        elif method == 'backward':
            df_filled[column] = df_filled[column].bfill()
        # Llenamos con la media de la columna
        elif method == 'mean':
            df_filled[column] = df_filled[column].fillna(df[column].mean())
        # Llenamos con la mediana de la columna
        elif method == 'median':
            df_filled[column] = df_filled[column].fillna(df[column].median())
        # Llenamos con ceros
        elif method == 'zero':
            df_filled[column] = df_filled[column].fillna(0)
        # Método desconocido: no sabemos cómo llenar, así que no tocamos los datos
        else:
            logger.error(f"Unknown fill method: {method}")
            return df

        # Calculamos cuántos valores llenamos efectivamente
        filled_count = missing_count - df_filled[column].isna().sum()
        # Registramos en el log el resultado de la operación
        logger.info(
            f"Filled {filled_count} missing values in '{column}' "
            f"using {method} method"
        )

        # Devolvemos el DataFrame con los valores llenados
        return df_filled

    # Método estático para suavizar datos usando promedios móviles
    @staticmethod
    def smooth_data(
        df: pd.DataFrame, # DataFrame con los datos
        column: str, # Nombre de la columna a suavizar
        window: int = 5, # Tamaño de la ventana para el suavizado
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
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df

        # Creamos una copia del DataFrame para no mutar el original
        df_smooth = df.copy()
        # Definimos el nombre de la nueva columna suavizada
        smoothed_col = f"{column}_smoothed"

        # Método de media móvil (centrada en cada punto)
        if method == 'rolling_mean':
            df_smooth[smoothed_col] = df_smooth[column].rolling(
                window=window, center=True, min_periods=1
            ).mean()
        # Método de mediana móvil (centrada en cada punto)
        elif method == 'rolling_median':
            df_smooth[smoothed_col] = df_smooth[column].rolling(
                window=window, center=True, min_periods=1
            ).median()
        # Método de suavizado exponencial (media móvil ponderada exponencialmente)
        elif method == 'exponential':
            df_smooth[smoothed_col] = df_smooth[column].ewm(
                span=window, adjust=False
            ).mean()
        # Método desconocido: no sabemos cómo suavizar, así que no tocamos los datos
        else:
            logger.error(f"Unknown smoothing method: {method}")
            return df

        # Registramos en el log el resultado de la operación
        logger.info(
            f"Smoothed '{column}' using {method} with window={window}, "
            f"created column '{smoothed_col}'"
        )

        # Devolvemos el DataFrame con la columna suavizada agregada
        return df_smooth

    # Método estático para validar que los valores estén dentro de rangos esperados
    @staticmethod
    def validate_ranges(
        df: pd.DataFrame, # DataFrame con los datos
        column: str, # Nombre de la columna a validar
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
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found in DataFrame")
            return df

        # Guardamos el conteo original de registros
        original_count = len(df)
        # Creamos una copia del DataFrame para no mutar el original
        df_valid = df.copy()

        # Aplicamos el filtro de valor mínimo si se especificó
        if min_value is not None:
            df_valid = df_valid[df_valid[column] >= min_value]

        # Aplicamos el filtro de valor máximo si se especificó
        if max_value is not None:
            df_valid = df_valid[df_valid[column] <= max_value]

        # Calculamos la cantidad de registros removidos
        removed_count = original_count - len(df_valid)

        # Si removimos registros, lo registramos en el log
        if removed_count > 0:
            logger.info(
                f"Removed {removed_count} invalid values from '{column}' "
                f"(range: {min_value} to {max_value})"
            )

        # Devolvemos el DataFrame validado
        return df_valid

    # Método estático para aplicar el pipeline estándar de limpieza de datos de perforación
    @staticmethod
    def clean_drilling_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply standard cleaning pipeline for drilling data.

        Args:
            df: DataFrame with drilling data

        Returns:
            Cleaned DataFrame
        """
        # Registramos el inicio del pipeline de limpieza
        logger.info("Starting standard drilling data cleaning pipeline")

        # Creamos una copia del DataFrame para no mutar el original
        df_clean = df.copy()

        # Definimos los parámetros comunes de perforación y sus rangos válidos
        # (incluimos tanto el nombre legible como el nombre de columna interno,
        # porque no sabemos de antemano cuál de los dos trae el DataFrame de entrada)
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

        # Iteramos sobre cada parámetro y aplicamos la validación de rangos
        for column, rules in cleaning_rules.items():
            # Si la columna existe en el DataFrame, la validamos
            if column in df_clean.columns:
                # Aplicamos la validación de rangos y reemplazamos el DataFrame acumulado
                df_clean = DataCleaner.validate_ranges(
                    df_clean, column,
                    min_value=rules.get('min'),
                    max_value=rules.get('max')
                )

        # Registramos la finalización del pipeline
        logger.info("Drilling data cleaning pipeline completed")

        # Devolvemos el DataFrame limpio
        return df_clean
