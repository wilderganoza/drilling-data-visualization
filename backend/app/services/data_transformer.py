"""
Data transformation service - Calculate ROP, convert units, resample data.
"""
import pandas as pd # Pandas para manipulación de datos
import numpy as np # NumPy para operaciones numéricas
from typing import Dict, Optional # Tipos para anotaciones
from app.core.logging import get_logger # Función para obtener logger

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)


# Clase de servicio para transformación y cálculo de métricas derivadas
class DataTransformer:
    
    # Método estático para calcular ROP (Rate of Penetration)
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
        # Verificar que las columnas requeridas existen
        if depth_col not in df.columns or time_col not in df.columns:
            logger.warning(f"Required columns not found: {depth_col}, {time_col}")
            return df
        
        # Crear copia del DataFrame
        df_rop = df.copy()
        
        # Calcular diferencia de profundidad entre registros consecutivos
        df_rop['depth_diff'] = df_rop[depth_col].diff()
        
        # Calcular diferencia de tiempo entre registros consecutivos
        df_rop['time_diff'] = df_rop[time_col].diff()
        
        # Calcular ROP (pies/hora): ROP = cambio_profundidad / cambio_tiempo
        df_rop['calculated_rop_ft_per_hr'] = df_rop['depth_diff'] / df_rop['time_diff']
        
        # Reemplazar valores infinitos con NaN
        df_rop['calculated_rop_ft_per_hr'] = df_rop['calculated_rop_ft_per_hr'].replace(
            [np.inf, -np.inf], np.nan
        )
        # Limitar valores negativos a 0
        df_rop['calculated_rop_ft_per_hr'] = df_rop['calculated_rop_ft_per_hr'].clip(lower=0)
        
        # Eliminar columnas temporales
        df_rop = df_rop.drop(columns=['depth_diff', 'time_diff'])
        
        # Registrar en log la operación
        logger.info(f"Calculated ROP from {depth_col} and {time_col}")
        
        # Retornar DataFrame con ROP calculado
        return df_rop
    
    # Método estático para convertir unidades de columnas especificadas
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
        # Crear copia del DataFrame
        df_converted = df.copy()
        
        # Iterar sobre cada conversión especificada
        for column, conversion in conversions.items():
            # Verificar que la columna existe
            if column not in df_converted.columns:
                logger.warning(f"Column '{column}' not found for conversion")
                continue
            
            # Obtener factor de conversión
            factor = conversion.get('factor', 1.0)
            # Obtener nombre de nueva columna
            new_name = conversion.get('new_name', f"{column}_converted")
            
            # Aplicar conversión multiplicando por el factor
            df_converted[new_name] = df_converted[column] * factor
            
            # Registrar en log la conversión
            logger.info(f"Converted '{column}' to '{new_name}' (factor: {factor})")
        
        # Retornar DataFrame con unidades convertidas
        return df_converted
    
    # Método estático para remuestrear datos reduciendo número de puntos
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
        # Guardar conteo original de registros
        original_count = len(df)
        
        # Si ya tiene menos puntos que el objetivo, no remuestrear
        if original_count <= target_points:
            logger.info(f"Data already has {original_count} points, no resampling needed")
            return df
        
        # Método de muestreo uniforme
        if method == 'uniform':
            # Calcular paso para muestreo uniforme
            step = original_count // target_points
            # Tomar cada n-ésimo punto
            df_resampled = df.iloc[::step].reset_index(drop=True)
            
        # Método LTTB (Largest Triangle Three Buckets)
        elif method == 'lttb':
            # Calcular tamaño de cada bucket
            bucket_size = original_count // target_points
            
            # Siempre incluir el primer punto
            sampled_indices = [0]
            
            # Iterar sobre buckets intermedios
            for i in range(1, target_points - 1):
                # Índice inicial del bucket
                start_idx = i * bucket_size
                # Índice final del bucket
                end_idx = min((i + 1) * bucket_size, original_count)
                
                # Tomar el punto medio de cada bucket
                mid_idx = (start_idx + end_idx) // 2
                sampled_indices.append(mid_idx)
            
            # Siempre incluir el último punto
            sampled_indices.append(original_count - 1)
            
            # Crear DataFrame remuestreado
            df_resampled = df.iloc[sampled_indices].reset_index(drop=True)
        # Método desconocido
        else:
            logger.error(f"Unknown resampling method: {method}")
            return df
        
        # Registrar en log la operación
        logger.info(
            f"Resampled data from {original_count} to {len(df_resampled)} points "
            f"using {method} method"
        )
        
        # Retornar DataFrame remuestreado
        return df_resampled
    
    # Método estático para calcular MSE (Mechanical Specific Energy)
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
        # Verificar columnas requeridas
        required_cols = [wob_col, rpm_col, rop_col]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        # Si faltan columnas, retornar sin cambios
        if missing_cols:
            logger.warning(f"Missing columns for MSE calculation: {missing_cols}")
            return df
        
        # Crear copia del DataFrame
        df_mse = df.copy()
        
        # Calcular área de la broca (pulgadas cuadradas)
        bit_area = np.pi * (bit_diameter / 2) ** 2
        
        # Convertir WOB de klbs a lbs
        wob_lbs = df_mse[wob_col] * 1000
        
        # Convertir ROP de pies/hora a pies/minuto
        rop_ft_min = df_mse[rop_col] / 60
        
        # Si hay columna de torque disponible
        if torque_col and torque_col in df_mse.columns:
            # Fórmula completa de MSE con torque
            torque = df_mse[torque_col]
            rpm = df_mse[rpm_col]
            
            # MSE = (WOB / Área) + (120 * π * RPM * Torque) / (Área * ROP)
            # Primer término: presión por WOB
            term1 = wob_lbs / bit_area
            # Segundo término: energía rotacional
            term2 = (120 * np.pi * rpm * torque) / (bit_area * rop_ft_min)
            
            # Sumar ambos términos
            df_mse['mse_psi'] = term1 + term2
            logger.info("Calculated MSE with torque")
        # Si no hay torque, usar fórmula simplificada
        else:
            # Fórmula simplificada de MSE sin torque
            df_mse['mse_psi'] = wob_lbs / (bit_area * rop_ft_min)
            logger.info("Calculated MSE without torque (simplified)")
        
        # Reemplazar valores infinitos con NaN
        df_mse['mse_psi'] = df_mse['mse_psi'].replace([np.inf, -np.inf], np.nan)
        # Limitar valores negativos a 0
        df_mse['mse_psi'] = df_mse['mse_psi'].clip(lower=0)
        
        # Retornar DataFrame con MSE calculado
        return df_mse
    
    # Método estático para calcular métricas de eficiencia de perforación
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
        # Verificar columnas requeridas
        required_cols = [rop_col, wob_col, rpm_col]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        # Si faltan columnas, retornar sin cambios
        if missing_cols:
            logger.warning(f"Missing columns for efficiency calculation: {missing_cols}")
            return df
        
        # Crear copia del DataFrame
        df_eff = df.copy()
        
        # Calcular ROP por WOB (pies/hora por klbs)
        df_eff['rop_per_wob'] = df_eff[rop_col] / df_eff[wob_col]
        
        # Calcular ROP por RPM (pies/hora por RPM)
        df_eff['rop_per_rpm'] = df_eff[rop_col] / df_eff[rpm_col]
        
        # Calcular energía específica (simplificada)
        df_eff['specific_energy'] = df_eff[wob_col] / df_eff[rop_col]
        
        # Reemplazar valores infinitos con NaN en todas las métricas
        for col in ['rop_per_wob', 'rop_per_rpm', 'specific_energy']:
            df_eff[col] = df_eff[col].replace([np.inf, -np.inf], np.nan)
        
        # Registrar en log la operación
        logger.info("Calculated drilling efficiency metrics")
        
        # Retornar DataFrame con métricas de eficiencia
        return df_eff
    
    # Método estático para normalizar una columna al rango 0-1
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
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return df
        
        # Crear copia del DataFrame
        df_norm = df.copy()
        # Nombre de la nueva columna normalizada
        normalized_col = f"{column}_normalized"
        
        # Método Min-Max (escala 0-1)
        if method == 'minmax':
            # Obtener valor mínimo
            min_val = df_norm[column].min()
            # Obtener valor máximo
            max_val = df_norm[column].max()
            # Aplicar normalización Min-Max
            df_norm[normalized_col] = (df_norm[column] - min_val) / (max_val - min_val)
        # Método Z-score (estandarización)
        elif method == 'zscore':
            # Calcular media
            mean = df_norm[column].mean()
            # Calcular desviación estándar
            std = df_norm[column].std()
            # Aplicar normalización Z-score
            df_norm[normalized_col] = (df_norm[column] - mean) / std
        # Método desconocido
        else:
            logger.error(f"Unknown normalization method: {method}")
            return df
        
        # Registrar en log la operación
        logger.info(f"Normalized '{column}' using {method} method")
        
        # Retornar DataFrame con columna normalizada
        return df_norm
