"""
Data transformation service - Calculate ROP, convert units, resample data.
"""
# Importamos pandas para manipular los DataFrames de datos de perforación
import pandas as pd
# Importamos numpy para operaciones numéricas (infinitos, pi, clip)
import numpy as np
# Importamos los tipos que usamos para anotar los parámetros de las funciones
from typing import Dict, Optional
# Importamos la función para obtener el logger del módulo
from app.core.logging import get_logger

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)


# Definimos la clase de servicio para transformación y cálculo de métricas derivadas
class DataTransformer:

    # Definimos el método estático que calcula el ROP (Rate of Penetration)
    @staticmethod
    def calculate_rop(
        df: pd.DataFrame, # DataFrame con datos de perforación
        depth_col: str = 'bit_depth_feet', # Columna de profundidad
        time_col: str = 'on_bottom_hours_hrs' # Columna de tiempo
    ) -> pd.DataFrame:
        """
        Calculate Rate of Penetration (ROP) from depth and time.

        Args:
            df: DataFrame with drilling data
            depth_col: Column name for depth
            time_col: Column name for time

        Returns:
            DataFrame with ROP column added
        """
        # Verificamos que las columnas requeridas existan en el DataFrame
        if depth_col not in df.columns or time_col not in df.columns:
            logger.warning(f"Required columns not found: {depth_col}, {time_col}")
            return df

        # Creamos una copia del DataFrame para no modificar el original
        df_rop = df.copy()

        # Calculamos la diferencia de profundidad entre registros consecutivos
        df_rop['depth_diff'] = df_rop[depth_col].diff()

        # Calculamos la diferencia de tiempo entre registros consecutivos
        df_rop['time_diff'] = df_rop[time_col].diff()

        # Calculamos el ROP (pies/hora): ROP = cambio_profundidad / cambio_tiempo
        df_rop['calculated_rop_ft_per_hr'] = df_rop['depth_diff'] / df_rop['time_diff']

        # Reemplazamos los valores infinitos (división entre cero) con NaN
        df_rop['calculated_rop_ft_per_hr'] = df_rop['calculated_rop_ft_per_hr'].replace(
            [np.inf, -np.inf], np.nan
        )
        # Limitamos los valores negativos a 0, un ROP negativo no tiene sentido físico
        df_rop['calculated_rop_ft_per_hr'] = df_rop['calculated_rop_ft_per_hr'].clip(lower=0)

        # Eliminamos las columnas temporales que usamos solo para el cálculo
        df_rop = df_rop.drop(columns=['depth_diff', 'time_diff'])

        # Registramos en el log la operación realizada
        logger.info(f"Calculated ROP from {depth_col} and {time_col}")

        # Devolvemos el DataFrame con el ROP calculado
        return df_rop

    # Definimos el método estático que convierte unidades de las columnas especificadas
    @staticmethod
    def convert_units(
        df: pd.DataFrame, # DataFrame con datos
        conversions: Dict[str, Dict[str, float]] # Diccionario de conversiones
    ) -> pd.DataFrame:
        """
        Convert units for specified columns.

        Args:
            df: DataFrame with data
            conversions: Dictionary mapping column names to conversion info
                Example: {
                    'depth_m': {'factor': 3.28084, 'new_name': 'depth_ft'},
                    'pressure_bar': {'factor': 14.5038, 'new_name': 'pressure_psi'}
                }

        Returns:
            DataFrame with converted units
        """
        # Creamos una copia del DataFrame para no modificar el original
        df_converted = df.copy()

        # Iteramos sobre cada conversión especificada
        for column, conversion in conversions.items():
            # Verificamos que la columna exista en el DataFrame
            if column not in df_converted.columns:
                logger.warning(f"Column '{column}' not found for conversion")
                continue

            # Obtenemos el factor de conversión
            factor = conversion.get('factor', 1.0)
            # Obtenemos el nombre de la nueva columna
            new_name = conversion.get('new_name', f"{column}_converted")

            # Aplicamos la conversión multiplicando por el factor
            df_converted[new_name] = df_converted[column] * factor

            # Registramos en el log la conversión realizada
            logger.info(f"Converted '{column}' to '{new_name}' (factor: {factor})")

        # Devolvemos el DataFrame con las unidades convertidas
        return df_converted

    # Definimos el método estático que remuestrea datos reduciendo el número de puntos
    @staticmethod
    def resample_data(
        df: pd.DataFrame, # DataFrame con datos
        target_points: int = 10000, # Número objetivo de puntos
        method: str = 'uniform' # Método de remuestreo
    ) -> pd.DataFrame:
        """
        Resample data to reduce number of points for visualization.

        Args:
            df: DataFrame with data
            target_points: Target number of points
            method: Resampling method ('uniform' or 'lttb')
                - uniform: Take every nth point
                - lttb: Largest Triangle Three Buckets (preserves shape)

        Returns:
            Resampled DataFrame
        """
        # Guardamos el conteo original de registros
        original_count = len(df)

        # Validamos que el objetivo de puntos sea positivo (evita división por cero)
        if target_points <= 0:
            logger.error(f"Invalid target_points: {target_points}, must be positive")
            return df

        # Si ya tiene menos puntos que el objetivo, no remuestreamos
        if original_count <= target_points:
            logger.info(f"Data already has {original_count} points, no resampling needed")
            return df

        # Aplicamos el método de muestreo uniforme
        if method == 'uniform':
            # Calculamos el paso para el muestreo uniforme
            step = original_count // target_points
            # Tomamos cada n-ésimo punto
            df_resampled = df.iloc[::step].reset_index(drop=True)

        # Aplicamos el método LTTB (Largest Triangle Three Buckets)
        elif method == 'lttb':
            # Calculamos el tamaño de cada bucket
            bucket_size = original_count // target_points

            # Incluimos siempre el primer punto
            sampled_indices = [0]

            # Iteramos sobre los buckets intermedios
            for i in range(1, target_points - 1):
                # Calculamos el índice inicial del bucket
                start_idx = i * bucket_size
                # Calculamos el índice final del bucket
                end_idx = min((i + 1) * bucket_size, original_count)

                # Tomamos el punto medio de cada bucket
                mid_idx = (start_idx + end_idx) // 2
                sampled_indices.append(mid_idx)

            # Incluimos siempre el último punto
            sampled_indices.append(original_count - 1)

            # Creamos el DataFrame remuestreado con los índices elegidos
            df_resampled = df.iloc[sampled_indices].reset_index(drop=True)
        # Rechazamos cualquier método que no reconozcamos
        else:
            logger.error(f"Unknown resampling method: {method}")
            return df

        # Registramos en el log la operación realizada
        logger.info(
            f"Resampled data from {original_count} to {len(df_resampled)} points "
            f"using {method} method"
        )

        # Devolvemos el DataFrame remuestreado
        return df_resampled

    # Definimos el método estático que calcula el MSE (Mechanical Specific Energy)
    @staticmethod
    def calculate_mse(
        df: pd.DataFrame, # DataFrame con datos de perforación
        wob_col: str = 'weight_on_bit_klbs', # Columna de peso sobre broca
        rpm_col: str = 'rotary_rpm_rpm', # Columna de RPM
        torque_col: Optional[str] = None, # Columna de torque (opcional)
        rop_col: str = 'calculated_rop_ft_per_hr', # Columna de ROP
        bit_diameter: float = 8.5 # Diámetro de broca en pulgadas
    ) -> pd.DataFrame:
        """
        Calculate Mechanical Specific Energy (MSE).

        Formula:
        MSE = (WOB / Area) + (120 * π * RPM * Torque) / (Area * ROP)

        If torque is not available, simplified formula:
        MSE = (WOB / Area) / (ROP / 60)  # ROP converted to ft/min

        Args:
            df: DataFrame with drilling data
            wob_col: Weight on Bit column (klbs)
            rpm_col: Rotary RPM column
            torque_col: Torque column (ft-lbs), optional
            rop_col: Rate of Penetration column (ft/hr)
            bit_diameter: Bit diameter in inches

        Returns:
            DataFrame with MSE column added
        """
        # Verificamos que las columnas requeridas existan
        required_cols = [wob_col, rpm_col, rop_col]
        missing_cols = [col for col in required_cols if col not in df.columns]

        # Si faltan columnas, devolvemos el DataFrame sin cambios
        if missing_cols:
            logger.warning(f"Missing columns for MSE calculation: {missing_cols}")
            return df

        # Creamos una copia del DataFrame para no modificar el original
        df_mse = df.copy()

        # Calculamos el área de la broca (pulgadas cuadradas)
        bit_area = np.pi * (bit_diameter / 2) ** 2

        # Convertimos el WOB de klbs a lbs
        wob_lbs = df_mse[wob_col] * 1000

        # Convertimos el ROP de pies/hora a pies/minuto
        rop_ft_min = df_mse[rop_col] / 60

        # Si hay columna de torque disponible, usamos la fórmula completa
        if torque_col and torque_col in df_mse.columns:
            # Fórmula completa de MSE con torque
            torque = df_mse[torque_col]
            rpm = df_mse[rpm_col]

            # MSE = (WOB / Área) + (120 * π * RPM * Torque) / (Área * ROP)
            # Calculamos el primer término: presión por WOB
            term1 = wob_lbs / bit_area
            # Calculamos el segundo término: energía rotacional
            term2 = (120 * np.pi * rpm * torque) / (bit_area * rop_ft_min)

            # Sumamos ambos términos
            df_mse['mse_psi'] = term1 + term2
            logger.info("Calculated MSE with torque")
        # Si no hay torque, usamos la fórmula simplificada
        else:
            # Aplicamos la fórmula simplificada de MSE sin torque
            df_mse['mse_psi'] = wob_lbs / (bit_area * rop_ft_min)
            logger.info("Calculated MSE without torque (simplified)")

        # Reemplazamos los valores infinitos con NaN
        df_mse['mse_psi'] = df_mse['mse_psi'].replace([np.inf, -np.inf], np.nan)
        # Limitamos los valores negativos a 0, un MSE negativo no tiene sentido físico
        df_mse['mse_psi'] = df_mse['mse_psi'].clip(lower=0)

        # Devolvemos el DataFrame con el MSE calculado
        return df_mse

    # Definimos el método estático que calcula métricas de eficiencia de perforación
    @staticmethod
    def calculate_drilling_efficiency(
        df: pd.DataFrame, # DataFrame con datos de perforación
        rop_col: str = 'calculated_rop_ft_per_hr', # Columna de ROP
        wob_col: str = 'weight_on_bit_klbs', # Columna de WOB
        rpm_col: str = 'rotary_rpm_rpm' # Columna de RPM
    ) -> pd.DataFrame:
        """
        Calculate drilling efficiency metrics.

        Args:
            df: DataFrame with drilling data
            rop_col: ROP column
            wob_col: WOB column
            rpm_col: RPM column

        Returns:
            DataFrame with efficiency metrics
        """
        # Verificamos que las columnas requeridas existan
        required_cols = [rop_col, wob_col, rpm_col]
        missing_cols = [col for col in required_cols if col not in df.columns]

        # Si faltan columnas, devolvemos el DataFrame sin cambios
        if missing_cols:
            logger.warning(f"Missing columns for efficiency calculation: {missing_cols}")
            return df

        # Creamos una copia del DataFrame para no modificar el original
        df_eff = df.copy()

        # Calculamos el ROP por WOB (pies/hora por klbs)
        df_eff['rop_per_wob'] = df_eff[rop_col] / df_eff[wob_col]

        # Calculamos el ROP por RPM (pies/hora por RPM)
        df_eff['rop_per_rpm'] = df_eff[rop_col] / df_eff[rpm_col]

        # Calculamos la energía específica (simplificada)
        df_eff['specific_energy'] = df_eff[wob_col] / df_eff[rop_col]

        # Reemplazamos los valores infinitos con NaN en todas las métricas
        for col in ['rop_per_wob', 'rop_per_rpm', 'specific_energy']:
            df_eff[col] = df_eff[col].replace([np.inf, -np.inf], np.nan)

        # Registramos en el log la operación realizada
        logger.info("Calculated drilling efficiency metrics")

        # Devolvemos el DataFrame con las métricas de eficiencia
        return df_eff

    # Definimos el método estático que normaliza una columna al rango 0-1
    @staticmethod
    def normalize_column(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Columna a normalizar
        method: str = 'minmax' # Método de normalización
    ) -> pd.DataFrame:
        """
        Normalize a column to 0-1 range.

        Args:
            df: DataFrame with data
            column: Column to normalize
            method: Normalization method ('minmax' or 'zscore')

        Returns:
            DataFrame with normalized column
        """
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return df

        # Creamos una copia del DataFrame para no modificar el original
        df_norm = df.copy()
        # Definimos el nombre de la nueva columna normalizada
        normalized_col = f"{column}_normalized"

        # Aplicamos el método Min-Max (escala 0-1)
        if method == 'minmax':
            # Obtenemos el valor mínimo
            min_val = df_norm[column].min()
            # Obtenemos el valor máximo
            max_val = df_norm[column].max()
            # Calculamos el rango de la columna
            value_range = max_val - min_val
            # Con columna constante o vacía no hay rango que escalar
            if not value_range or pd.isna(value_range):
                logger.warning(f"Column '{column}' has no value range, normalized to 0")
                df_norm[normalized_col] = 0.0
            else:
                # Aplicamos la normalización Min-Max
                df_norm[normalized_col] = (df_norm[column] - min_val) / value_range
        # Aplicamos el método Z-score (estandarización)
        elif method == 'zscore':
            # Calculamos la media
            mean = df_norm[column].mean()
            # Calculamos la desviación estándar
            std = df_norm[column].std()
            # Con desviación cero o indefinida no podemos estandarizar
            if not std or pd.isna(std):
                logger.warning(f"Column '{column}' has zero std, normalized to 0")
                df_norm[normalized_col] = 0.0
            else:
                # Aplicamos la normalización Z-score
                df_norm[normalized_col] = (df_norm[column] - mean) / std
        # Rechazamos cualquier método que no reconozcamos
        else:
            logger.error(f"Unknown normalization method: {method}")
            return df

        # Registramos en el log la operación realizada
        logger.info(f"Normalized '{column}' using {method} method")

        # Devolvemos el DataFrame con la columna normalizada
        return df_norm
