"""
Event detection service - Automatically detect drilling events and anomalies.
"""
# Importamos pandas para manipular los DataFrames de datos de perforación
import pandas as pd
# Importamos numpy para operaciones numéricas (máscaras booleanas, z-scores, infinitos)
import numpy as np
# Importamos los tipos que usamos para anotar los parámetros y retornos de las funciones
from typing import List, Dict, Any, Optional
# Importamos la función para obtener el logger del módulo
from app.core.logging import get_logger

# Obtenemos la instancia de logger para este módulo
logger = get_logger(__name__)


# Definimos la clase de servicio para detección de eventos y anomalías de perforación
class EventDetector:

    # Definimos el método estático que detecta conexiones de tubería (períodos de ROP bajo)
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
        # Verificamos que la columna de ROP exista en el DataFrame
        if rop_col not in df.columns:
            logger.warning(f"ROP column '{rop_col}' not found")
            return []

        # Encontramos los períodos donde el ROP está por debajo del umbral
        low_rop = df[rop_col] < threshold

        # Recorremos la serie para armar la lista de conexiones detectadas
        connections = []
        in_connection = False # Marcamos si estamos dentro de una conexión en curso
        start_idx = None # Guardamos el índice de inicio de la conexión

        # Iteramos sobre cada punto de datos
        for idx, is_low in enumerate(low_rop):
            # Si el ROP es bajo y todavía no estábamos en conexión, iniciamos una nueva
            if is_low and not in_connection:
                in_connection = True
                start_idx = idx
            # Si el ROP vuelve a ser normal y estábamos en conexión, la cerramos
            elif not is_low and in_connection:
                # Calculamos la duración de la conexión
                duration = idx - start_idx
                # Si la duración cumple el mínimo exigido, agregamos el evento
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

        # Manejamos el caso donde la conexión se extiende hasta el final de los datos
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

        # Registramos en el log la cantidad de eventos detectados
        logger.info(f"Detected {len(connections)} connection events")
        return connections

    # Definimos el método estático que detecta eventos de tubería atascada (WOB alto pero ROP bajo)
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
        # Verificamos que las columnas requeridas existan en el DataFrame
        if wob_col not in df.columns or rop_col not in df.columns:
            logger.warning(f"Required columns not found: {wob_col}, {rop_col}")
            return []

        # Definimos la condición de tubería atascada: WOB alto pero ROP bajo
        stuck_condition = (df[wob_col] > wob_threshold) & (df[rop_col] < rop_threshold)

        stuck_events = []
        in_stuck = False # Marcamos si estamos dentro de un evento de atascamiento en curso
        start_idx = None # Guardamos el índice de inicio del evento

        # Iteramos sobre cada punto de datos
        for idx, is_stuck in enumerate(stuck_condition):
            # Si se cumple la condición y todavía no estábamos en evento, iniciamos uno nuevo
            if is_stuck and not in_stuck:
                in_stuck = True
                start_idx = idx
            # Si deja de cumplirse la condición y estábamos en evento, lo cerramos
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

        # Manejamos el caso donde el evento se extiende hasta el final de los datos
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

        # Registramos en el log la cantidad de eventos detectados
        logger.info(f"Detected {len(stuck_events)} potential stuck pipe events")
        return stuck_events

    # Definimos el método estático que detecta anomalías en una columna específica
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
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return []

        anomalies = []

        # Aplicamos el método Z-score
        if method == 'zscore':
            # Calculamos la media
            mean = df[column].mean()
            # Calculamos la desviación estándar
            std = df[column].std()
            # Con desviación cero o indefinida no hay anomalías detectables
            if not std or np.isnan(std):
                logger.info(f"Column '{column}' has zero std, no anomalies detectable")
                return []
            # Calculamos los z-scores absolutos
            z_scores = np.abs((df[column] - mean) / std)
            # Creamos la máscara de anomalías (z-score por encima del umbral)
            anomaly_mask = z_scores > threshold

        # Aplicamos el método IQR (rango intercuartílico)
        elif method == 'iqr':
            # Calculamos el primer cuartil
            Q1 = df[column].quantile(0.25)
            # Calculamos el tercer cuartil
            Q3 = df[column].quantile(0.75)
            # Calculamos el rango intercuartílico
            IQR = Q3 - Q1
            # Calculamos los límites inferior y superior
            lower_bound = Q1 - threshold * IQR
            upper_bound = Q3 + threshold * IQR
            # Creamos la máscara de anomalías (valores fuera de los límites)
            anomaly_mask = (df[column] < lower_bound) | (df[column] > upper_bound)

        # Rechazamos cualquier método que no reconozcamos
        else:
            logger.error(f"Unknown anomaly detection method: {method}")
            return []

        # Obtenemos los índices de las filas marcadas como anomalías
        anomaly_indices = df[anomaly_mask].index.tolist()

        # Armamos la lista de eventos de anomalías
        for idx in anomaly_indices:
            anomalies.append({
                'event_type': 'anomaly',
                'index': idx,
                'column': column,
                'value': df.loc[idx, column],
                'depth': df.loc[idx].get('bit_depth_feet', None),
                'method': method
            })

        # Registramos en el log la cantidad de anomalías detectadas
        logger.info(f"Detected {len(anomalies)} anomalies in '{column}' using {method} method")
        return anomalies

    # Definimos el método estático que detecta cambios rápidos en un parámetro
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
        # Verificamos que la columna exista en el DataFrame
        if column not in df.columns:
            logger.warning(f"Column '{column}' not found")
            return []

        # Trabajamos sobre índice posicional: el DataFrame puede llegar filtrado
        # con un índice no contiguo y los accesos por etiqueta idx-1 fallarían
        df_reset = df.reset_index(drop=True)

        # Calculamos el cambio porcentual entre registros consecutivos
        pct_change = df_reset[column].pct_change() * 100

        # Buscamos los cambios rápidos
        rapid_changes = []
        # Creamos la máscara de cambios rápidos (cambio absoluto finito por encima del umbral)
        rapid_mask = np.abs(pct_change.replace([np.inf, -np.inf], np.nan)) > threshold_pct

        # Iteramos sobre los índices donde hubo cambios rápidos
        for idx in df_reset[rapid_mask].index:
            # Saltamos la primera fila porque no tiene valor previo con el cual comparar
            if idx > 0:
                rapid_changes.append({
                    'event_type': 'rapid_change',
                    'index': idx,
                    'column': column,
                    'previous_value': df_reset.loc[idx - 1, column],
                    'current_value': df_reset.loc[idx, column],
                    'change_pct': pct_change.loc[idx],
                    'depth': df_reset.loc[idx].get('bit_depth_feet', None)
                })

        # Registramos en el log la cantidad de cambios rápidos detectados
        logger.info(
            f"Detected {len(rapid_changes)} rapid changes in '{column}' "
            f"(threshold: {threshold_pct}%)"
        )
        return rapid_changes

    # Definimos el método estático que ejecuta todos los algoritmos de detección de eventos
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
        # Registramos en el log el inicio de la detección completa
        logger.info("Running comprehensive event detection")

        # Ejecutamos todos los detectores y almacenamos sus resultados
        events = {
            # Detectamos conexiones de tubería
            'connections': EventDetector.detect_connections(df, rop_col=rop_col),
            # Detectamos tubería atascada
            'stuck_pipe': EventDetector.detect_stuck_pipe(
                df, wob_col=wob_col, rop_col=rop_col
            ),
            # Detectamos anomalías en el ROP
            'rop_anomalies': EventDetector.detect_anomalies(df, rop_col, method='zscore'),
            # Detectamos anomalías en el WOB
            'wob_anomalies': EventDetector.detect_anomalies(df, wob_col, method='zscore')
        }

        # Calculamos el total de eventos detectados
        total_events = sum(len(event_list) for event_list in events.values())
        # Registramos en el log el total
        logger.info(f"Total events detected: {total_events}")

        # Devolvemos el diccionario con todos los eventos por tipo
        return events

    # Definimos el método estático que crea un resumen de los eventos detectados
    @staticmethod
    def summarize_events(events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Create a summary of detected events.

        Args:
            events: Dictionary of events by type

        Returns:
            Summary statistics
        """
        # Armamos el diccionario de resumen
        summary = {
            # Total de eventos de todos los tipos
            'total_events': sum(len(event_list) for event_list in events.values()),
            # Conteo por tipo de evento
            'by_type': {
                event_type: len(event_list)
                for event_type, event_list in events.items()
            }
        }

        # Registramos en el log el resumen
        logger.info(f"Event summary: {summary['total_events']} total events")

        # Devolvemos el resumen
        return summary
