from fastapi import APIRouter, HTTPException, Depends # Componentes de FastAPI para crear endpoints
from sqlalchemy.orm import Session # Session de SQLAlchemy para manejo de sesiones de BD
import pandas as pd # Pandas para manipulación de datos
from typing import Dict, Any # Tipos para anotaciones
from app.core.logging import get_logger # Función para obtener logger
from app.db.session import get_depth_db, db_manager # Funciones para obtener sesiones de BD
from app.db.repositories.data_repository import DataRepository # Repositorio de datos para consultas

# Importar schemas Pydantic para validación y serialización
from app.schemas.processing import (
    DataQualityReport,
    CleanDataRequest,
    TransformDataRequest,
    InterpolateRequest,
    EventDetectionRequest,
    ProcessingResponse,
    EventDetectionResponse
)

from app.constants.parameters import get_tracked_parameters # Función para obtener parámetros rastreados

# Servicios de procesamiento de datos
from app.services.data_cleaner import DataCleaner
from app.services.data_transformer import DataTransformer
from app.services.interpolator import TimeDepthInterpolator
from app.services.event_detector import EventDetector

# Obtener instancia de logger para este módulo
logger = get_logger(__name__)

# Crear router de FastAPI para endpoints de procesamiento
router = APIRouter()

# Endpoint POST /clean para limpiar datos de perforación
@router.post("/clean", response_model=ProcessingResponse, summary="Clean drilling data")
# Función asíncrona para limpiar datos removiendo outliers y llenando valores faltantes
async def clean_data(
    # Parámetro body: parámetros de limpieza
    request: CleanDataRequest,

    # Inyección de dependencia: sesión de BD de profundidad
    db: Session = Depends(get_depth_db)
):
    # Registrar en log la operación de limpieza
    logger.info(f"Cleaning data for well {request.well_id}")
    
    # Intentar limpiar los datos
    try:
        # Obtener tabla de datos de profundidad desde el gestor de BD
        table = db_manager.get_depth_table("well_data")

        # Si la tabla no existe
        if table is None:
            # Lanzar error 500
            raise HTTPException(status_code=500, detail="Database table not found")
        
        # Crear instancia del repositorio de datos
        repo = DataRepository(db, table)
        
        # Consultar muestra de datos (10000 registros)
        data = repo.query_sample(request.well_id, sample_size=10000)
        
        # Si no hay datos
        if not data:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"No data found for well {request.well_id}")
        
        # Convertir datos a DataFrame de pandas para procesamiento
        df = pd.DataFrame(data)
        
        # Guardar conteo original de registros
        original_count = len(df)
        
        # Si se solicita remover outliers y hay columnas especificadas
        if request.remove_outliers and request.columns:
            # Iterar sobre cada columna a limpiar
            for col in request.columns:
                # Verificar que la columna existe en el DataFrame
                if col in df.columns:
                    # Remover outliers usando el método especificado
                    df = DataCleaner.remove_outliers(df, col, method=request.outlier_method)
        
        # Si se solicita llenar valores faltantes y hay columnas especificadas
        if request.fill_missing and request.columns:
            # Iterar sobre cada columna a procesar
            for col in request.columns:
                # Verificar que la columna existe en el DataFrame
                if col in df.columns:
                    # Llenar valores faltantes usando el método especificado
                    df = DataCleaner.fill_missing_values(df, col, method=request.fill_method)
        
        # Aplicar limpieza estándar de datos de perforación
        df = DataCleaner.clean_drilling_data(df)
        
        # Calcular conteo de registros después de limpieza
        cleaned_count = len(df)
        
        # Calcular registros removidos
        removed_count = original_count - cleaned_count
        
        # Crear diccionario de estadísticas
        statistics = {
            # Total de registros originales
            'original_records': original_count,
        
            # Total de registros después de limpieza
            'cleaned_records': cleaned_count,
        
            # Total de registros removidos
            'removed_records': removed_count,
        
            # Porcentaje de registros removidos
            'removal_percentage': (removed_count / original_count * 100) if original_count > 0 else 0
        }
        
        # Retornar respuesta con resultado de limpieza
        return ProcessingResponse(
            # ID del pozo
            well_id=request.well_id,
        
            # Tipo de operación
            operation='clean',
        
            # Estado de éxito
            success=True,
        
            # Mensaje descriptivo
            message=f"Data cleaned successfully. Removed {removed_count} records.",
        
            # Estadísticas de la operación
            statistics=statistics
        )
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error cleaning data: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error cleaning data: {str(e)}")

# Endpoint POST /transform para transformar datos calculando métricas derivadas
@router.post("/transform", response_model=ProcessingResponse, summary="Transform drilling data")
# Función asíncrona para transformar datos de perforación
async def transform_data(
    # Parámetro body: parámetros de transformación
    request: TransformDataRequest,

    # Inyección de dependencia: sesión de BD de profundidad
    db: Session = Depends(get_depth_db)
):
    # Registrar en log la operación de transformación
    logger.info(f"Transforming data for well {request.well_id}")
    
    # Intentar transformar los datos
    try:
        # Obtener tabla de datos de tiempo desde el gestor de BD
        table = db_manager.get_depth_table("well_data")

        # Si la tabla no existe
        if table is None:
            # Lanzar error 500
            raise HTTPException(status_code=500, detail="Database table not found")
        
        # Crear instancia del repositorio de datos
        repo = DataRepository(db, table)
        
        # Consultar muestra de datos (10000 registros)
        data = repo.query_sample(request.well_id, sample_size=10000)
        
        # Si no hay datos
        if not data:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"No data found for well {request.well_id}")
        
        # Convertir datos a DataFrame de pandas
        df = pd.DataFrame(data)
        
        # Lista para rastrear operaciones realizadas
        operations_performed = []
        
        # Calcular ROP (Rate of Penetration) si se solicita
        if request.calculate_rop:
            # Aplicar cálculo de ROP
            df = DataTransformer.calculate_rop(df)
        
            # Agregar operación a la lista
            operations_performed.append('calculate_rop')
        
        # Calcular MSE (Mechanical Specific Energy) si se solicita
        if request.calculate_mse:
            # Aplicar cálculo de MSE con diámetro de broca
            df = DataTransformer.calculate_mse(df, bit_diameter=request.bit_diameter)
        
            # Agregar operación a la lista
            operations_performed.append('calculate_mse')
        
        # Calcular métricas de eficiencia si se solicita
        if request.calculate_efficiency:
            # Aplicar cálculo de eficiencia de perforación
            df = DataTransformer.calculate_drilling_efficiency(df)
        
            # Agregar operación a la lista
            operations_performed.append('calculate_efficiency')
        
        # Remuestrear datos si se solicita
        if request.resample:
            # Aplicar remuestreo a número objetivo de puntos
            df = DataTransformer.resample_data(df, target_points=request.target_points)
        
            # Agregar operación a la lista
            operations_performed.append('resample')
        
        # Crear diccionario de estadísticas
        statistics = {
            # Lista de operaciones realizadas
            'operations_performed': operations_performed,
        
            # Conteo final de registros
            'final_record_count': len(df),
        
            # Nuevas columnas creadas
            'new_columns': [col for col in df.columns if col not in data[0].keys()]
        }
        
        # Retornar respuesta con resultado de transformación
        return ProcessingResponse(
            # ID del pozo
            well_id=request.well_id,
        
            # Tipo de operación
            operation='transform',
        
            # Estado de éxito
            success=True,
        
            # Mensaje descriptivo
            message=f"Data transformed successfully. Performed {len(operations_performed)} operations.",
        
            # Estadísticas de la operación
            statistics=statistics
        )
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error transforming data: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error transforming data: {str(e)}")

# Endpoint POST /interpolate para interpolar datos a grilla uniforme de profundidad
@router.post("/interpolate", response_model=ProcessingResponse, summary="Interpolate to depth grid")
# Función asíncrona para interpolar datos basados en tiempo a profundidad
async def interpolate_data(
    # Parámetro body: parámetros de interpolación
    request: InterpolateRequest,

    # Inyección de dependencia: sesión de BD de profundidad
    db: Session = Depends(get_depth_db)
):
    # Registrar en log la operación de interpolación
    logger.info(f"Interpolating data for well {request.well_id}")
    
    # Intentar interpolar los datos
    try:
        # Obtener tabla de datos de tiempo desde el gestor de BD
        table = db_manager.get_depth_table("well_data")

        # Si la tabla no existe
        if table is None:
            # Lanzar error 500
            raise HTTPException(status_code=500, detail="Database table not found")
        
        # Crear instancia del repositorio de datos
        repo = DataRepository(db, table)
        
        # Consultar muestra de datos (10000 registros)
        data = repo.query_sample(request.well_id, sample_size=10000)
        
        # Si no hay datos
        if not data:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"No data found for well {request.well_id}")
        
        # Convertir datos a DataFrame de pandas
        df = pd.DataFrame(data)
        
        # Si se proporcionaron profundidades específicas, usarlas
        if request.target_depths:
            target_depths = request.target_depths
        # Si se proporcionaron min/max depth, crear grilla uniforme
        elif request.min_depth is not None and request.max_depth is not None:
            # Crear grilla uniforme de profundidad
            target_depths = TimeDepthInterpolator.create_uniform_depth_grid(request.min_depth, request.max_depth, request.depth_step)
        # Si no se proporcionaron, usar rango de datos
        else:
            # Nombre de columna de profundidad
            depth_col = 'bit_depth_feet'
          
            # Verificar que la columna existe
            if depth_col in df.columns:
                # Obtener profundidad mínima
                min_d = df[depth_col].min()
          
                # Obtener profundidad máxima
                max_d = df[depth_col].max()
          
                # Crear grilla uniforme con el rango de datos
                target_depths = TimeDepthInterpolator.create_uniform_depth_grid(min_d, max_d, request.depth_step)
            # Si no hay columna de profundidad, error
            else:
                raise HTTPException(status_code=400, detail="Cannot determine depth range")
        
        # Interpolar datos a las profundidades objetivo
        df_interpolated = TimeDepthInterpolator.interpolate_to_depth(
            # DataFrame original
            df, target_depths,
            
            # Columnas a interpolar
            value_cols=request.columns,
            
            # Método de interpolación
            method=request.method
        )
        
        # Crear diccionario de estadísticas
        statistics = {
            # Número de puntos originales
            'original_points': len(df),
            
            # Número de puntos interpolados
            'interpolated_points': len(df_interpolated),
            
            # Rango de profundidad
            'depth_range': {
                'min': min(target_depths),
                'max': max(target_depths)
            },
            
            # Método de interpolación usado
            'method': request.method
        }
        
        # Retornar respuesta con resultado de interpolación
        return ProcessingResponse(
            # ID del pozo
            well_id=request.well_id,
            
            # Tipo de operación
            operation='interpolate',
            
            # Estado de éxito
            success=True,
            
            # Mensaje descriptivo
            message=f"Data interpolated to {len(df_interpolated)} depth points.",
            
            # Estadísticas de la operación
            statistics=statistics
        )
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error interpolating data: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error interpolating data: {str(e)}")

# Endpoint POST /detect-events para detectar eventos y anomalías de perforación
@router.post("/detect-events", response_model=EventDetectionResponse, summary="Detect drilling events")
# Función asíncrona para detectar eventos de perforación
async def detect_events(
    # Parámetro body: parámetros de detección de eventos
    request: EventDetectionRequest,

    # Inyección de dependencia: sesión de BD de profundidad
    db: Session = Depends(get_depth_db)
):
    # Registrar en log la operación de detección de eventos
    logger.info(f"Detecting events for well {request.well_id}")
    
    # Intentar detectar eventos
    try:
        # Obtener tabla de datos de profundidad desde el gestor de BD
        table = db_manager.get_depth_table("well_data")

        # Si la tabla no existe
        if table is None:
            # Lanzar error 500
            raise HTTPException(status_code=500, detail="Database table not found")
        
        # Crear instancia del repositorio de datos
        repo = DataRepository(db, table)
        
        # Consultar muestra de datos (10000 registros)
        data = repo.query_sample(request.well_id, sample_size=10000)
        
        # Si no hay datos
        if not data:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"No data found for well {request.well_id}")
        
        # Convertir datos a DataFrame de pandas
        df = pd.DataFrame(data)
        
        # Detectar todos los eventos de perforación
        events = EventDetector.detect_all_events(
            # DataFrame con datos
            df,
            
            # Columna de ROP (Rate of Penetration)
            rop_col=request.rop_col,
            
            # Columna de WOB (Weight on Bit)
            wob_col=request.wob_col
        )
        
        # Crear resumen de eventos detectados
        summary = EventDetector.summarize_events(events)
        
        # Retornar respuesta con eventos detectados
        return EventDetectionResponse(
            # ID del pozo
            well_id=request.well_id,
            
            # Total de eventos detectados
            total_events=summary['total_events'],
            
            # Eventos agrupados por tipo
            events_by_type=summary['by_type'],
            
            # Lista completa de eventos
            events=events,
            
            # Resumen de eventos
            summary=summary
        )
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error detecting events: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error detecting events: {str(e)}")

# Endpoint GET /quality-report/{well_id} para generar reporte de calidad de datos
@router.get("/quality-report/{well_id}", response_model=DataQualityReport, summary="Get data quality report")
# Función asíncrona para generar reporte de calidad de datos
async def get_quality_report(
    # Parámetro de ruta: ID del pozo
    well_id: int,
    
    # Inyección de dependencia: sesión de BD de profundidad
    db: Session = Depends(get_depth_db)
):
    # Registrar en log la generación de reporte de calidad
    logger.info(f"Generating quality report for well {well_id}")
    
    # Intentar generar reporte de calidad
    try:
        # Obtener tabla de datos de profundidad desde el gestor de BD
        table = db_manager.get_depth_table("well_data")
  
        # Si la tabla no existe
        if table is None:
            # Lanzar error 500
            raise HTTPException(status_code=500, detail="Database table not found")
        
        # Crear instancia del repositorio de datos
        repo = DataRepository(db, table)
        
        # Consultar muestra grande de datos (50000 registros) para análisis
        data = repo.query_sample(well_id, sample_size=50000)
        
        # Si no hay datos
        if not data:
            # Lanzar error 404
            raise HTTPException(status_code=404, detail=f"No data found for well {well_id}")
        
        # Convertir datos a DataFrame de pandas
        df = pd.DataFrame(data)
        
        # Obtener lista de parámetros rastreados desde constantes
        tracked_params = get_tracked_parameters()
        
        # Obtener todas las columnas numéricas del DataFrame
        all_numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        # Filtrar columnas de sistema (id, well_id)
        all_numeric_cols = [col for col in all_numeric_cols if col not in ['id', 'well_id']]
        
        # Tratar ceros como valores nulos
        missing_values = {col: int(df[col].isna().sum() + (df[col] == 0).sum()) for col in all_numeric_cols}
        
        # Diccionario para almacenar outliers detectados
        outliers_detected = {}
        
        # Diccionario para almacenar rangos de datos
        data_ranges = {}
        
        # Analizar solo los parámetros rastreados que existen en el DataFrame
        for col in tracked_params:
            # Si la columna no existe, saltar
            if col not in df.columns:
                continue
            
            # Calcular primer cuartil (Q1)
            Q1 = df[col].quantile(0.25)
            
            # Calcular tercer cuartil (Q3)
            Q3 = df[col].quantile(0.75)
            
            # Calcular rango intercuartílico
            IQR = Q3 - Q1
            
            # Calcular límite inferior (Q1 - 1.5*IQR)
            lower = Q1 - 1.5 * IQR
            
            # Calcular límite superior (Q3 + 1.5*IQR)
            upper = Q3 + 1.5 * IQR
            
            # Contar valores fuera de los límites (outliers)
            outliers = ((df[col] < lower) | (df[col] > upper)).sum()
            
            # Almacenar conteo de outliers
            outliers_detected[col] = int(outliers)
            
            # Contar valores nulos (NaN + ceros)
            null_count = df[col].isna().sum() + (df[col] == 0).sum()
            
            # Calcular porcentaje de nulos
            null_percentage = (null_count / len(df)) * 100
            
            # Reemplazar ceros con NA y eliminar NAs para cálculos
            col_data = df[col].replace(0, pd.NA).dropna()
            
            # Almacenar rangos y estadísticas de la columna
            data_ranges[col] = {
                # Valor mínimo
                'min': float(col_data.min()) if len(col_data) > 0 else 0.0,
            
                # Valor máximo
                'max': float(col_data.max()) if len(col_data) > 0 else 0.0,
            
                # Media
                'mean': float(col_data.mean()) if len(col_data) > 0 else 0.0,
            
                # Desviación estándar
                'std': float(col_data.std()) if len(col_data) > 0 else 0.0,
            
                # Percentil 25
                'p25': float(col_data.quantile(0.25)) if len(col_data) > 0 else 0.0,
            
                # Percentil 50 (mediana)
                'p50': float(col_data.quantile(0.50)) if len(col_data) > 0 else 0.0,
            
                # Percentil 75
                'p75': float(col_data.quantile(0.75)) if len(col_data) > 0 else 0.0,
            
                # Porcentaje de valores nulos
                'null_pct': float(null_percentage)
            }
        
        # Total de celdas en el DataFrame
        total_cells = len(df) * len(all_numeric_cols)
        
        # Total de celdas con valores faltantes
        missing_cells = sum(missing_values.values())
        
        # Total de celdas con outliers
        outlier_cells = sum(outliers_detected.values())
        
        # Calcular score: 100 - (penalización por faltantes) - (penalización por outliers)
        quality_score = max(0, 100 - (missing_cells / total_cells * 50) - (outlier_cells / total_cells * 50))
        
        # Retornar reporte de calidad de datos
        return DataQualityReport(
            # ID del pozo
            well_id=well_id,
        
            # Total de registros analizados
            total_records=len(df),
        
            # Número de columnas analizadas
            columns_analyzed=len(all_numeric_cols),
        
            # Diccionario de valores faltantes por columna
            missing_values=missing_values,
        
            # Diccionario de outliers detectados por columna
            outliers_detected=outliers_detected,
        
            # Diccionario de rangos y estadísticas por columna
            data_ranges=data_ranges,
        
            # Score de calidad (0-100)
            quality_score=round(quality_score, 2)
        )
        
    # Re-lanzar excepciones HTTP sin modificar
    except HTTPException:
        raise
    # Capturar cualquier otra excepción
    except Exception as e:
        # Registrar error en log
        logger.error(f"Error generating quality report: {e}")
        
        # Lanzar excepción HTTP 500 con detalle del error
        raise HTTPException(status_code=500, detail=f"Error generating quality report: {str(e)}")
