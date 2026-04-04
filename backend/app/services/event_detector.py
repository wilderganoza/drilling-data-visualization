"""
Event detection service - Automatically detect drilling events and anomalies.
"""
import pandas as pd # Pandas para manipulación de datos
import numpy as np # NumPy para operaciones numéricas
from typing import List, Dict, Any, Optional # Tipos para anotaciones
from app.core.logging import get_logger # Función para obtener logger

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)


# Clase de servicio para detección de eventos y anomalías de perforación
class EventDetector:
    
    # Método estático para detectar conexiones de tubería (períodos de ROP bajo)
    @staticmethod
    def detect_connections(
        df: pd.DataFrame, # DataFrame con datos de perforación
        rop_col: str = 'rate_of_penetration_ft_per_hr', # Columna de ROP
        threshold: float = 5.0, # Umbral de ROP para considerar conexión
        min_duration: int = 3 # Duración mínima en puntos consecutivos
    ) -> List[Dict[str, Any]]:
        """
        Detect pipe connections (periods of zero or very low ROP).
        
        Args:
            df: DataFrame with drilling data
            rop_col: ROP column name
            threshold: ROP threshold below which it's considered a connection
            min_duration: Minimum number of consecutive points
            
        Returns:
            List of detected connection events
        """
        # Verificar que la columna de ROP existe
        if rop_col not in df.columns:
            logger.warning(f"ROP column '{rop_col}' not found")
            return []
        
        # Encontrar períodos donde ROP está por debajo del umbral
        low_rop = df[rop_col] < threshold
        
        # Encontrar secuencias consecutivas
        connections = []
        in_connection = False # Flag para indicar si estamos en una conexión
        start_idx = None # Índice de inicio de la conexión
        
        # Iterar sobre cada punto de datos
        for idx, is_low in enumerate(low_rop):
            # Si ROP es bajo y no estamos en conexión, iniciar nueva conexión
            if is_low and not in_connection:
                in_connection = True
                start_idx = idx
            # Si ROP es normal y estamos en conexión, finalizar conexión
            elif not is_low and in_connection:
                # Calcular duración de la conexión
                duration = idx - start_idx
                # Si la duración cumple el mínimo, agregar evento
                if duration >= min_duration:
                    connections.append({
                        'event_type': 'connection',
                        'start_index': start_idx,
                        'end_index': idx - 1,
                        'duration_points': duration,
                        'start_depth': df.iloc[start_idx].get('bit_depth_feet', None),
                        'end_depth': df.iloc[idx - 1].get('bit_depth_feet', None)
                    })
                in_connection = False
                start_idx = None
        
        # Manejar caso donde la conexión se extiende hasta el final de los datos
        if in_connection and start_idx is not None:
            duration = len(df) - start_idx
            if duration >= min_duration:
                connections.append({
                    'event_type': 'connection',
                    'start_index': start_idx,
                    'end_index': len(df) - 1,
                    'duration_points': duration,
                    'start_depth': df.iloc[start_idx].get('bit_depth_feet', None),
                    'end_depth': df.iloc[-1].get('bit_depth_feet', None)
                })
        
        # Registrar en log la cantidad de eventos detectados
        logger.info(f"Detected {len(connections)} connection events")
        return connections
    
    # Método estático para detectar eventos de tubería atascada (WOB alto pero ROP bajo)
    @staticmethod
    def detect_stuck_pipe(
        df: pd.DataFrame, # DataFrame con datos de perforación
        wob_col: str = 'weight_on_bit_klbs', # Columna de WOB
        rop_col: str = 'rate_of_penetration_ft_per_hr', # Columna de ROP
        wob_threshold: float = 10.0, # Umbral mínimo de WOB
        rop_threshold: float = 1.0, # Umbral máximo de ROP
        min_duration: int = 5 # Duración mínima en puntos consecutivos
    ) -> List[Dict[str, Any]]:
        """
        Detect potential stuck pipe events (high WOB but low ROP).
        
        Args:
            df: DataFrame with drilling data
            wob_col: WOB column name
            rop_col: ROP column name
            wob_threshold: Minimum WOB to consider (klbs)
            rop_threshold: Maximum ROP to consider stuck (ft/hr)
            min_duration: Minimum consecutive points
            
        Returns:
            List of detected stuck pipe events
        """
        # Verificar que las columnas requeridas existen
        if wob_col not in df.columns or rop_col not in df.columns:
            logger.warning(f"Required columns not found: {wob_col}, {rop_col}")
            return []
        
        # Condiciones para tubería atascada: WOB alto pero ROP bajo
        stuck_condition = (df[wob_col] > wob_threshold) & (df[rop_col] < rop_threshold)
        
        stuck_events = []
        in_stuck = False # Flag para indicar si estamos en evento de atascamiento
        start_idx = None # Índice de inicio del evento
        
        # Iterar sobre cada punto de datos
        for idx, is_stuck in enumerate(stuck_condition):
            # Si cumple condición y no estamos en evento, iniciar nuevo evento
            if is_stuck and not in_stuck:
                in_stuck = True
                start_idx = idx
            # Si no cumple condición y estamos en evento, finalizar evento
            elif not is_stuck and in_stuck:
                duration = idx - start_idx
                if duration >= min_duration:
                    stuck_events.append({
                        'event_type': 'stuck_pipe',
                        'start_index': start_idx,
                        'end_index': idx - 1,
                        'duration_points': duration,
                        'start_depth': df.iloc[start_idx].get('bit_depth_feet', None),
                        'end_depth': df.iloc[idx - 1].get('bit_depth_feet', None),
                        'avg_wob': df.iloc[start_idx:idx][wob_col].mean(),
                        'avg_rop': df.iloc[start_idx:idx][rop_col].mean()
                    })
                in_stuck = False
                start_idx = None
        
        # Manejar caso donde el evento se extiende hasta el final
        if in_stuck and start_idx is not None:
            duration = len(df) - start_idx
            if duration >= min_duration:
                stuck_events.append({
                    'event_type': 'stuck_pipe',
                    'start_index': start_idx,
                    'end_index': len(df) - 1,
                    'duration_points': duration,
                    'start_depth': df.iloc[start_idx].get('bit_depth_feet', None),
                    'end_depth': df.iloc[-1].get('bit_depth_feet', None),
                    'avg_wob': df.iloc[start_idx:][wob_col].mean(),
                    'avg_rop': df.iloc[start_idx:][rop_col].mean()
                })
        
        # Registrar en log la cantidad de eventos detectados
        logger.info(f"Detected {len(stuck_events)} potential stuck pipe events")
        return stuck_events
    
    # Método estático para detectar anomalías en una columna específica
    @staticmethod
    def detect_anomalies(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Columna a analizar
        method: str = 'zscore', # Método de detección
        threshold: float = 5.0 # Umbral para detección
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalies in a specific column.
        
        Args:
            df: DataFrame with data
            column: Column to analyze
            method: Detection method ('zscore' or 'iqr')
            threshold: Threshold for anomaly detection
            
        Returns:
            List of detected anomalies
        """
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return []
        
        anomalies = []
        
        # Método Z-score
        if method == 'zscore':
            # Calcular media
            mean = df[column].mean()
            # Calcular desviación estándar
            std = df[column].std()
            # Calcular z-scores absolutos
            z_scores = np.abs((df[column] - mean) / std)
            # Crear máscara de anomalías (z-score > umbral)
            anomaly_mask = z_scores > threshold
            
        # Método IQR (Interquartile Range)
        elif method == 'iqr':
            # Calcular primer cuartil
            Q1 = df[column].quantile(0.25)
            # Calcular tercer cuartil
            Q3 = df[column].quantile(0.75)
            # Calcular rango intercuartílico
            IQR = Q3 - Q1
            # Calcular límites
            lower_bound = Q1 - threshold * IQR
            upper_bound = Q3 + threshold * IQR
            # Crear máscara de anomalías (fuera de límites)
            anomaly_mask = (df[column] < lower_bound) | (df[column] > upper_bound)
            
        # Método desconocido
        else:
            logger.error(f"Unknown anomaly detection method: {method}")
            return []
        
        # Encontrar índices de anomalías
        anomaly_indices = df[anomaly_mask].index.tolist()
        
        # Crear lista de eventos de anomalías
        for idx in anomaly_indices:
            anomalies.append({
                'event_type': 'anomaly',
                'index': idx,
                'column': column,
                'value': df.loc[idx, column],
                'depth': df.loc[idx].get('bit_depth_feet', None),
                'method': method
            })
        
        # Registrar en log la cantidad de anomalías detectadas
        logger.info(f"Detected {len(anomalies)} anomalies in '{column}' using {method} method")
        return anomalies
    
    # Método estático para detectar cambios rápidos en un parámetro
    @staticmethod
    def detect_rapid_changes(
        df: pd.DataFrame, # DataFrame con datos
        column: str, # Columna a analizar
        threshold_pct: float = 50.0 # Umbral de cambio porcentual
    ) -> List[Dict[str, Any]]:
        """
        Detect rapid changes in a parameter (potential equipment issues).
        
        Args:
            df: DataFrame with data
            column: Column to analyze
            threshold_pct: Percentage change threshold
            
        Returns:
            List of detected rapid changes
        """
        # Verificar que la columna existe
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return []
        
        # Calcular cambio porcentual entre registros consecutivos
        pct_change = df[column].pct_change() * 100
        
        # Encontrar cambios rápidos
        rapid_changes = []
        # Crear máscara de cambios rápidos (cambio absoluto > umbral)
        rapid_mask = np.abs(pct_change) > threshold_pct
        
        # Iterar sobre índices con cambios rápidos
        for idx in df[rapid_mask].index:
            # Saltar primera fila (no tiene valor previo)
            if idx > 0:
                rapid_changes.append({
                    'event_type': 'rapid_change',
                    'index': idx,
                    'column': column,
                    'previous_value': df.loc[idx - 1, column],
                    'current_value': df.loc[idx, column],
                    'change_pct': pct_change.loc[idx],
                    'depth': df.loc[idx].get('bit_depth_feet', None)
                })
        
        # Registrar en log la cantidad de cambios rápidos detectados
        logger.info(
            f"Detected {len(rapid_changes)} rapid changes in '{column}' "
            f"(threshold: {threshold_pct}%)"
        )
        return rapid_changes
    
    # Método estático para ejecutar todos los algoritmos de detección de eventos
    @staticmethod
    def detect_all_events(
        df: pd.DataFrame, # DataFrame con datos de perforación
        rop_col: str = 'rate_of_penetration_ft_per_hr', # Columna de ROP
        wob_col: str = 'weight_on_bit_klbs' # Columna de WOB
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run all event detection algorithms.
        
        Args:
            df: DataFrame with drilling data
            rop_col: ROP column name
            wob_col: WOB column name
            
        Returns:
            Dictionary with all detected events by type
        """
        # Registrar inicio de detección completa
        logger.info("Running comprehensive event detection")
        
        # Ejecutar todos los detectores y almacenar resultados
        events = {
            # Detectar conexiones de tubería
            'connections': EventDetector.detect_connections(df, rop_col=rop_col),
            # Detectar tubería atascada
            'stuck_pipe': EventDetector.detect_stuck_pipe(
                df, wob_col=wob_col, rop_col=rop_col
            ),
            # Detectar anomalías en ROP
            'rop_anomalies': EventDetector.detect_anomalies(df, rop_col, method='zscore'),
            # Detectar anomalías en WOB
            'wob_anomalies': EventDetector.detect_anomalies(df, wob_col, method='zscore')
        }
        
        # Calcular total de eventos detectados
        total_events = sum(len(event_list) for event_list in events.values())
        # Registrar en log el total
        logger.info(f"Total events detected: {total_events}")
        
        # Retornar diccionario con todos los eventos por tipo
        return events
    
    # Método estático para crear resumen de eventos detectados
    @staticmethod
    def summarize_events(events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Create a summary of detected events.
        
        Args:
            events: Dictionary of events by type
            
        Returns:
            Summary statistics
        """
        # Crear diccionario de resumen
        summary = {
            # Total de eventos de todos los tipos
            'total_events': sum(len(event_list) for event_list in events.values()),
            # Conteo por tipo de evento
            'by_type': {
                event_type: len(event_list)
                for event_type, event_list in events.items()
            }
        }
        
        # Registrar en log el resumen
        logger.info(f"Event summary: {summary['total_events']} total events")
        
        # Retornar resumen
        return summary
