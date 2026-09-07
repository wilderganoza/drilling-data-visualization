"""Outlier detection service that orchestrates scaling, PCA and anomaly removal."""
# Habilitamos las anotaciones de tipo diferidas (necesario para los tipos usados solo en anotaciones)
from __future__ import annotations

# Importamos los tipos de fecha/hora que normalizamos al serializar los registros
from datetime import date, datetime, time, timedelta
# Importamos los tipos genéricos que usamos en las anotaciones de esta clase
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Importamos numpy para operar arreglos numéricos (máscaras, estadísticas, conversión de tipos nativos)
import numpy as np
# Importamos pandas para construir y manipular el dataframe de datos crudos
import pandas as pd
# Importamos stats de scipy para el cálculo de z-scores en la detección de outliers
from scipy import stats
# Importamos update de SQLAlchemy para actualizar el dataset existente por SQL masivo al reemplazarlo
from sqlalchemy import update as sa_update
# Importamos Session para tipar la sesión de base de datos que recibimos por inyección
from sqlalchemy.orm import Session
# Importamos Table para tipar la tabla de datos del pozo (reflejada dinámicamente)
from sqlalchemy.sql.schema import Table

# Importamos los algoritmos de detección de outliers de scikit-learn (no se difieren: este módulo ya se
# carga a nivel de import en app/web/outliers.py y app/web/cases.py, así que sklearn se carga en el
# arranque de la app de todas formas — no hay beneficio en diferir estos imports dentro de las funciones)
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
# Importamos los distintos escaladores de scikit-learn que ofrecemos en el wizard de preprocesamiento
from sklearn.preprocessing import (
    MaxAbsScaler,
    MinMaxScaler,
    RobustScaler,
    StandardScaler,
)

# Importamos settings para los límites por defecto y máximos de registros a consultar
from app.core.config import settings
# Importamos el logger de la app para dejar trazas del pipeline
from app.core.logging import get_logger
# Importamos el modelo ProcessedDataset y utcnow para persistir/actualizar datasets procesados
from app.models.legacy import ProcessedDataset, utcnow
# Importamos el repositorio de datos crudos del pozo
from app.repositories.data_repository import DataRepository
# Importamos el repositorio de datasets procesados (persistencia de resultados del pipeline)
from app.repositories.processed_dataset_repository import ProcessedDatasetRepository
# Importamos los esquemas Pydantic que definen las peticiones/respuestas de la API de outliers
from app.schemas.outliers import (
    OutlierConfig,
    OutlierDetectionRequest,
    OutlierDetectionResponse,
    OutlierMethod,
    OutlierPreviewResponse,
    PCAConfig,
    PcaPreviewResponse,
    PcaPreviewScore,
    PipelineMetrics,
    ProcessedDataResponse,
    ProcessedDatasetDetail,
    ProcessedDatasetSummary,
    ProcessedRecordData,
    ScalingConfig,
    ScalingMethod,
    ScalingPreviewResponse,
    ScalingPreviewRowData,
)

# Creamos el logger de este módulo
logger = get_logger(__name__)


# Declaramos la excepción propia que señala fallos en la ejecución del pipeline
class OutlierDetectionError(Exception):
    """Raised when pipeline execution fails."""


# Definimos el servicio que orquesta todo el flujo de detección de outliers y su persistencia
class OutlierDetectionService:
    """Encapsulates the outlier detection workflow and persistence."""

    # Inicializamos el servicio con la sesión de BD y la tabla de datos del pozo (para escalado/PCA/detección)
    def __init__(self, session: Session, well_data_table: Table):
        self.session = session
        self.well_data_table = well_data_table
        # Creamos el repositorio de datos crudos apuntando a la tabla del pozo (depth o time)
        self.data_repo = DataRepository(session, well_data_table)
        # Creamos el repositorio de datasets procesados (independiente de la tabla de origen)
        self.datasets_repo = ProcessedDatasetRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_pipeline(
        self,
        request: OutlierDetectionRequest,
        *,
        created_by: Optional[int] = None,
        replace_dataset_id: Optional[int] = None,
    ) -> OutlierDetectionResponse:
        """Execute the pipeline and persist results.

        When ``replace_dataset_id`` is provided, the existing dataset is
        updated in place (records replaced, config/metrics overwritten).
        """
        # Dejamos traza de la ejecución del pipeline con los parámetros principales de la petición
        logger.info(
            "Running outlier detection: well_id=%s, variables=%s, method=%s",
            request.well_id,
            request.variables,
            request.outlier.method,
        )

        # Consultamos los datos crudos del pozo (muestra limitada por configuración)
        raw_records = self._fetch_raw_data(request)
        if not raw_records:
            raise OutlierDetectionError("No data available for the selected well")

        # Construimos el dataframe y verificamos que las variables pedidas existan en las columnas disponibles
        df = pd.DataFrame(raw_records)
        available_columns = set(df.columns)
        missing = [col for col in request.variables if col not in available_columns]
        if missing:
            raise OutlierDetectionError(
                f"Variables not found in dataset: {', '.join(missing)}"
            )

        # Validamos también las columnas adicionales a incluir (no usadas en el modelo, solo guardadas)
        include_columns = request.include_columns or []
        include_missing = [col for col in include_columns if col not in available_columns]
        if include_missing:
            raise OutlierDetectionError(
                f"Included columns not found in dataset: {', '.join(include_missing)}"
            )

        # Convertimos las variables seleccionadas a numérico y descartamos filas con valores no numéricos
        numeric_df = self._prepare_numeric_dataframe(df, request.variables)
        total_records = len(df)
        numeric_records = len(numeric_df)
        dropped_due_to_nan = total_records - numeric_records
        if numeric_records == 0:
            raise OutlierDetectionError("All selected variables contain non-numeric data")

        # Standard order: outlier detection (raw data) -> scaling (fit on
        # inliers) -> PCA (fit on inliers). Outliers are still transformed
        # through the fitted scaler/PCA so they get scaled/component values
        # too (for display when mark_outliers keeps them), but they never
        # skew the scaler/PCA statistics themselves.
        # Detectamos los outliers sobre los datos crudos (antes de escalar)
        raw_values = numeric_df.values
        outlier_mask = self._detect_outliers(raw_values, request.outlier)
        inlier_mask = ~outlier_mask
        inlier_count = int(inlier_mask.sum())
        outlier_count = int(outlier_mask.sum())
        if inlier_count == 0:
            raise OutlierDetectionError("Pipeline flagged all rows as outliers")

        # Ajustamos el escalador solo con los inliers, pero transformamos todas las filas
        fit_source = raw_values[inlier_mask]
        scaled_array = self._apply_scaling(raw_values, request.scaling, fit_values=fit_source)
        scaled_fit_source = scaled_array[inlier_mask]
        # Ajustamos y aplicamos PCA de la misma manera (fit solo en inliers, transform en todas las filas)
        (
            feature_array,
            feature_labels,
            explained_variance,
            explained_variance_ratio,
        ) = self._apply_pca(scaled_array, request.pca, request.variables, fit_values=scaled_fit_source)

        # Generamos un nombre de dataset si el usuario no proporcionó uno
        dataset_name = request.dataset_name or self._generate_dataset_name(request)

        # Guardamos la configuración completa del pipeline para poder reproducirlo/mostrarlo después
        pipeline_config = {
            "variables": request.variables,
            "scaling": request.scaling.model_dump(),
            "pca": request.pca.model_dump(),
            "outlier": request.outlier.model_dump(),
            "max_records": request.max_records,
            "include_columns": include_columns,
        }

        # Si nos pidieron reemplazar un dataset existente, lo actualizamos en su lugar; si no, creamos uno nuevo
        if replace_dataset_id is not None:
            existing = self.datasets_repo.get_by_id(replace_dataset_id)
            if existing is None:
                raise OutlierDetectionError(
                    f"Dataset {replace_dataset_id} not found for replacement"
                )
            try:
                # Evict the dataset from the session so the delete-orphan
                # cascade on its records relationship cannot fire when we
                # subsequently modify the row via bulk SQL.
                # Expulsamos el dataset de la sesión para que el cascade delete-orphan no dispare al modificarlo por SQL masivo
                self.session.expunge(existing)
                # Borramos los registros previos del dataset antes de insertar los nuevos
                self.datasets_repo.delete_records(replace_dataset_id)
                # Actualizamos la fila del dataset (metadatos y config) por SQL masivo, dejándola en estado "processing"
                self.session.execute(
                    sa_update(ProcessedDataset)
                    .where(ProcessedDataset.id == replace_dataset_id)
                    .values(
                        well_id=request.well_id,
                        domain="time" if getattr(request, "domain", "depth") == "time" else "depth",
                        name=dataset_name,
                        description=request.description,
                        pipeline_config=pipeline_config,
                        metrics=None,
                        record_count=None,
                        status="processing",
                        updated_at=utcnow(),
                    )
                )
                self.session.flush()
                # Recargamos el dataset ya actualizado
                dataset = self.datasets_repo.get_by_id(replace_dataset_id)
                if dataset is None:
                    raise OutlierDetectionError(
                        f"Dataset {replace_dataset_id} vanished during replacement"
                    )
            except OutlierDetectionError:
                raise
            except Exception as exc:
                # Revertimos la transacción si algo falló al preparar el reemplazo
                self.session.rollback()
                logger.exception("Failed to prepare dataset for replacement")
                raise OutlierDetectionError(
                    f"Failed to replace dataset {replace_dataset_id}: {exc}"
                ) from exc
        else:
            # Creamos un dataset nuevo en estado "processing"
            dataset = self.datasets_repo.create_dataset(
                well_id=request.well_id,
                domain=getattr(request, "domain", "depth"),
                name=dataset_name,
                description=request.description,
                pipeline_config=pipeline_config,
                metrics=None,
                created_by=created_by,
                status="processing",
            )

        try:
            # Armamos las columnas a persistir (variables del modelo + columnas adicionales, sin duplicados)
            storage_columns = list(dict.fromkeys(request.variables + include_columns))
            # Construimos el payload de registros (datos crudos, escalados, componentes PCA y flag de outlier)
            records_payload = self._build_records_payload(
                df.loc[numeric_df.index],
                storage_columns,
                outlier_mask=outlier_mask,
                include_outliers=request.outlier.mark_outliers,
                scaled_array=scaled_array,
                scaled_labels=list(numeric_df.columns),
                component_array=feature_array if request.pca.enabled else None,
                component_labels=feature_labels if request.pca.enabled else None,
            )

            # Insertamos los registros procesados en el dataset
            inserted = self.datasets_repo.add_records(dataset.id, records_payload)

            # Armamos las métricas finales del pipeline para guardarlas junto al dataset
            metrics = PipelineMetrics(
                total_records=total_records,
                processed_records=numeric_records,
                outlier_records=outlier_count,
                outlier_percentage=(outlier_count / numeric_records * 100) if numeric_records else 0.0,
                variables=request.variables,
                dropped_records=dropped_due_to_nan,
                scaled_feature_labels=list(numeric_df.columns),
                pca_component_labels=feature_labels if request.pca.enabled else None,
                explained_variance=explained_variance,
                explained_variance_ratio=explained_variance_ratio,
            )

            # Guardamos las métricas finales y marcamos el dataset como completado
            self.datasets_repo.update_metrics(
                dataset,
                metrics=metrics.model_dump(),
                record_count=inlier_count if not request.outlier.mark_outliers else inserted,
                status="completed",
            )
            self.session.commit()
        except Exception as exc:
            # Revertimos todo si falló la persistencia de los registros o las métricas
            self.session.rollback()
            logger.exception("Failed to persist processed dataset")
            raise OutlierDetectionError(f"Failed to persist processed dataset: {exc}") from exc

        # Recargamos el dataset ya persistido para devolver su estado final
        refreshed_dataset = self.datasets_repo.get_by_id(dataset.id)
        if refreshed_dataset is None:
            raise OutlierDetectionError("Failed to load processed dataset after saving")

        # Devolvemos el detalle del dataset procesado
        detail = self._to_detail(refreshed_dataset)
        return OutlierDetectionResponse(dataset=detail)

    def preview_pipeline(self, request: OutlierDetectionRequest) -> OutlierPreviewResponse:
        """Run the same sklearn-based pipeline without persisting results.

        Used by the frontend preview so the metrics shown during configuration
        always match the metrics of a persisted case.
        """
        # Dejamos traza de la ejecución en modo preview (no persiste nada)
        logger.info(
            "Preview outlier detection: well_id=%s, variables=%s, method=%s",
            request.well_id,
            request.variables,
            request.outlier.method,
        )

        # Consultamos los datos crudos del pozo
        raw_records = self._fetch_raw_data(request)
        if not raw_records:
            raise OutlierDetectionError("No data available for the selected well")

        # Construimos el dataframe y verificamos que las variables pedidas existan
        df = pd.DataFrame(raw_records)
        available_columns = set(df.columns)
        missing = [col for col in request.variables if col not in available_columns]
        if missing:
            raise OutlierDetectionError(
                f"Variables not found in dataset: {', '.join(missing)}"
            )

        # Convertimos las variables a numérico y descartamos filas no numéricas
        numeric_df = self._prepare_numeric_dataframe(df, request.variables)
        total_records = len(df)
        numeric_records = len(numeric_df)
        dropped_due_to_nan = total_records - numeric_records
        if numeric_records == 0:
            raise OutlierDetectionError("All selected variables contain non-numeric data")

        # Detectamos los outliers sobre los datos crudos
        # Detectamos outliers, escalamos y calculamos PCA igual que en run_pipeline pero sin persistir nada
        raw_values = numeric_df.values
        outlier_mask = self._detect_outliers(raw_values, request.outlier)
        inlier_mask = ~outlier_mask
        outlier_count = int(outlier_mask.sum())

        # Si todo quedó marcado como outlier, usamos todos los valores como fuente de ajuste (evitamos fit vacío)
        fit_source = raw_values[inlier_mask] if inlier_mask.any() else raw_values
        scaled_array = self._apply_scaling(raw_values, request.scaling, fit_values=fit_source)
        scaled_fit_source = scaled_array[inlier_mask] if inlier_mask.any() else scaled_array
        (
            feature_array,
            feature_labels,
            explained_variance,
            explained_variance_ratio,
        ) = self._apply_pca(scaled_array, request.pca, request.variables, fit_values=scaled_fit_source)

        # Armamos las métricas del pipeline (iguales a las que se guardarían en un run real)
        metrics = PipelineMetrics(
            total_records=total_records,
            processed_records=numeric_records,
            outlier_records=outlier_count,
            outlier_percentage=(outlier_count / numeric_records * 100) if numeric_records else 0.0,
            variables=request.variables,
            dropped_records=dropped_due_to_nan,
            scaled_feature_labels=list(numeric_df.columns),
            pca_component_labels=feature_labels if request.pca.enabled else None,
            explained_variance=explained_variance,
            explained_variance_ratio=explained_variance_ratio,
        )

        # Return PCA components (or scaled features when PCA disabled) so the
        # frontend scatter plot visualizes the same feature space the model saw.
        # Elegimos qué matriz mostrar en el scatter plot: componentes PCA si está habilitado, si no, los valores escalados
        component_matrix = feature_array if request.pca.enabled else scaled_array
        component_labels = (
            feature_labels if request.pca.enabled else list(numeric_df.columns)
        )
        # Convertimos la matriz a listas nativas, reemplazando valores no finitos por 0 para que serialice bien
        components = [
            [float(v) if np.isfinite(v) else 0.0 for v in row]
            for row in component_matrix.tolist()
        ]
        is_outlier = [bool(v) for v in outlier_mask.tolist()]

        # Devolvemos la respuesta de preview con métricas, componentes y la máscara de outliers
        return OutlierPreviewResponse(
            metrics=metrics,
            component_labels=component_labels,
            components=components,
            is_outlier=is_outlier,
        )

    def preview_scaling(self, request: OutlierDetectionRequest) -> ScalingPreviewResponse:
        """Return raw and sklearn-scaled values per row for the wizard preview."""
        # Consultamos los datos crudos del pozo
        raw_records = self._fetch_raw_data(request)
        if not raw_records:
            raise OutlierDetectionError("No data available for the selected well")

        # Construimos el dataframe y verificamos que las variables pedidas existan
        df = pd.DataFrame(raw_records)
        available_columns = set(df.columns)
        missing = [col for col in request.variables if col not in available_columns]
        if missing:
            raise OutlierDetectionError(
                f"Variables not found in dataset: {', '.join(missing)}"
            )

        # Convertimos a numérico; si no queda ninguna fila válida, no hay nada que previsualizar
        numeric_df = self._prepare_numeric_dataframe(df, request.variables)
        if numeric_df.empty:
            raise OutlierDetectionError("All selected variables contain non-numeric data")

        # Detectamos outliers para poder ajustar el escalador solo con los inliers
        raw_values = numeric_df.values
        outlier_mask = self._detect_outliers(raw_values, request.outlier)
        inlier_mask = ~outlier_mask
        fit_source = raw_values[inlier_mask] if inlier_mask.any() else raw_values
        scaled_array = self._apply_scaling(raw_values, request.scaling, fit_values=fit_source)

        # Armamos fila por fila el par de valores crudo/escalado para cada variable, para mostrar en el wizard
        rows: List[ScalingPreviewRowData] = []
        for pos, (source_idx, series) in enumerate(numeric_df.iterrows()):
            raw_map: Dict[str, Optional[float]] = {}
            scaled_map: Dict[str, Optional[float]] = {}
            for col_idx, variable in enumerate(request.variables):
                raw_val = series.get(variable)
                raw_map[variable] = (
                    float(raw_val) if raw_val is not None and np.isfinite(raw_val) else None
                )
                scaled_val = scaled_array[pos, col_idx]
                scaled_map[variable] = (
                    float(scaled_val) if np.isfinite(scaled_val) else None
                )
            rows.append(
                ScalingPreviewRowData(
                    index=int(source_idx) + 1,
                    raw=raw_map,
                    scaled=scaled_map,
                )
            )

        # Devolvemos la comparación fila a fila entre valores crudos y escalados
        return ScalingPreviewResponse(
            variables=request.variables,
            total_rows=len(rows),
            rows=rows,
        )

    def preview_pca(self, request: OutlierDetectionRequest) -> PcaPreviewResponse:
        """Return sklearn PCA scores and explained variance for the wizard preview."""
        # Consultamos los datos crudos del pozo
        raw_records = self._fetch_raw_data(request)
        if not raw_records:
            raise OutlierDetectionError("No data available for the selected well")

        # Construimos el dataframe y verificamos que las variables pedidas existan
        df = pd.DataFrame(raw_records)
        available_columns = set(df.columns)
        missing = [col for col in request.variables if col not in available_columns]
        if missing:
            raise OutlierDetectionError(
                f"Variables not found in dataset: {', '.join(missing)}"
            )

        # Convertimos a numérico; si no queda ninguna fila válida, no hay nada que previsualizar
        numeric_df = self._prepare_numeric_dataframe(df, request.variables)
        if numeric_df.empty:
            raise OutlierDetectionError("All selected variables contain non-numeric data")

        # Detectamos outliers y escalamos ajustando solo con los inliers
        raw_values = numeric_df.values
        outlier_mask = self._detect_outliers(raw_values, request.outlier)
        inlier_mask = ~outlier_mask
        fit_source = raw_values[inlier_mask] if inlier_mask.any() else raw_values
        scaled_array = self._apply_scaling(raw_values, request.scaling, fit_values=fit_source)
        scaled_fit_source = scaled_array[inlier_mask] if inlier_mask.any() else scaled_array

        # Forzamos PCA habilitado para la previsualización, aunque el request lo tenga deshabilitado
        pca_config = request.pca if request.pca.enabled else PCAConfig(enabled=True)
        (
            feature_array,
            feature_labels,
            explained_variance,
            explained_variance_ratio,
        ) = self._apply_pca(scaled_array, pca_config, request.variables, fit_values=scaled_fit_source)

        # Armamos los puntajes de PCA fila por fila para el wizard
        scores: List[PcaPreviewScore] = []
        for pos, source_idx in enumerate(numeric_df.index.tolist()):
            row_vals = [
                float(v) if np.isfinite(v) else 0.0 for v in feature_array[pos].tolist()
            ]
            scores.append(PcaPreviewScore(index=int(source_idx) + 1, components=row_vals))

        # Devolvemos los componentes, la varianza explicada y los puntajes por fila
        return PcaPreviewResponse(
            component_labels=feature_labels,
            explained_variance=explained_variance or [],
            explained_variance_ratio=explained_variance_ratio or [],
            scores=scores,
        )

    # Listamos los datasets procesados de un pozo específico, convertidos a su resumen
    def list_datasets(self, well_id: int) -> List[ProcessedDatasetSummary]:
        datasets = self.datasets_repo.list_by_well(well_id)
        return [self._to_summary(ds) for ds in datasets]

    # Listamos todos los datasets procesados (todos los pozos), convertidos a su resumen
    def list_all_datasets(self) -> List[ProcessedDatasetSummary]:
        datasets = self.datasets_repo.list_all()
        return [self._to_summary(ds) for ds in datasets]

    # Obtenemos el detalle de un dataset por id, o None si no existe
    def get_dataset(self, dataset_id: int) -> Optional[ProcessedDatasetDetail]:
        dataset = self.datasets_repo.get_by_id(dataset_id)
        if not dataset:
            return None
        return self._to_detail(dataset)

    # Obtenemos los registros paginados de un dataset (con o sin outliers según se pida)
    def get_dataset_data(
        self,
        dataset_id: int,
        *,
        include_outliers: bool,
        page: int,
        page_size: int,
    ) -> ProcessedDataResponse:
        # Contamos el total de registros que cumplen el filtro, para la paginación
        total_records = self.datasets_repo.count_records(
            dataset_id,
            include_outliers=include_outliers,
        )
        # Consultamos la página de registros solicitada
        records = self.datasets_repo.list_records(
            dataset_id,
            include_outliers=include_outliers,
            page=page,
            page_size=page_size,
        )
        # Convertimos cada registro ORM al esquema de respuesta de la API
        payload = [
            ProcessedRecordData(
                source_record_id=record.source_record_id,
                is_outlier=record.is_outlier,
                data=record.data or {},
                scaled=record.scaled_data or None,
                components=record.component_scores or None,
            )
            for record in records
        ]
        return ProcessedDataResponse(
            dataset_id=dataset_id,
            include_outliers=include_outliers,
            total_records=total_records,
            page=page,
            page_size=page_size,
            records=payload,
        )

    # Borramos un dataset procesado; confirmamos la transacción solo si realmente se borró alguna fila
    def delete_dataset(self, dataset_id: int) -> bool:
        deleted_rows = self.datasets_repo.delete_dataset(dataset_id)
        if deleted_rows:
            self.session.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    # Consultamos una muestra de datos crudos del pozo, respetando el límite pedido y el máximo permitido
    def _fetch_raw_data(self, request: OutlierDetectionRequest) -> List[Dict[str, Any]]:
        limit = request.max_records or settings.DEFAULT_QUERY_LIMIT
        limit = min(limit, settings.MAX_QUERY_LIMIT)
        return self.data_repo.query_sample(request.well_id, sample_size=limit)

    # Convertimos las columnas seleccionadas a numérico y descartamos las filas que queden con algún NaN
    def _prepare_numeric_dataframe(self, df: pd.DataFrame, variables: Sequence[str]) -> pd.DataFrame:
        numeric_df = df[list(variables)].apply(pd.to_numeric, errors="coerce")
        valid_mask = numeric_df.notna().all(axis=1)
        numeric_df = numeric_df.loc[valid_mask]
        return numeric_df

    def _apply_scaling(
        self,
        values: np.ndarray,
        config: ScalingConfig,
        fit_values: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Fit the scaler on ``fit_values`` (defaults to ``values``) and
        transform ``values``. Callers that already removed outliers pass the
        inlier-only subset as ``fit_values`` so outliers don't skew the
        scaler's statistics, while still getting scaled output for every row.
        """
        # Si no se pidió escalado, devolvemos los valores tal cual
        if config.method == ScalingMethod.none:
            return values

        # Instanciamos el escalador de sklearn correspondiente al método pedido
        scaler: Any
        params = {**config.params}
        if config.method == ScalingMethod.standard:
            scaler = StandardScaler(**params)
        elif config.method == ScalingMethod.minmax:
            scaler = MinMaxScaler(**params)
        elif config.method == ScalingMethod.robust:
            scaler = RobustScaler(**params)
        elif config.method == ScalingMethod.maxabs:
            scaler = MaxAbsScaler(**params)
        else:
            raise OutlierDetectionError(f"Unsupported scaling method: {config.method}")

        # Ajustamos el escalador con fit_values (o con values si no nos pasaron una fuente distinta) y transformamos todo
        fit_source = fit_values if fit_values is not None and len(fit_values) else values
        scaler.fit(fit_source)
        return scaler.transform(values)

    def _apply_pca(
        self,
        values: np.ndarray,
        config: PCAConfig,
        variable_labels: Sequence[str],
        fit_values: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, List[str], Optional[List[float]], Optional[List[float]]]:
        # Si PCA está deshabilitado, devolvemos los valores originales como si fueran las "features" finales
        if not config.enabled:
            return values, list(variable_labels), None, None

        # Armamos los parámetros de PCA, descartando los que vinieron en None (para dejar los defaults de sklearn)
        params = {
            "n_components": config.n_components,
            "whiten": config.whiten,
            "svd_solver": config.svd_solver,
        }
        params = {k: v for k, v in params.items() if v is not None}

        # Ajustamos PCA con fit_values y transformamos todos los valores; capturamos cualquier fallo de sklearn
        try:
            pca = PCA(**params)
            fit_source = fit_values if fit_values is not None and len(fit_values) else values
            pca.fit(fit_source)
            transformed = pca.transform(values)
        except Exception as exc:
            raise OutlierDetectionError(f"PCA failed: {exc}") from exc

        # Nombramos los componentes (PC1, PC2, ...) y extraemos la varianza explicada si está disponible
        component_labels = [f"PC{i+1}" for i in range(transformed.shape[1])]
        explained_variance = (
            pca.explained_variance_.tolist() if hasattr(pca, "explained_variance_") else None
        )
        explained_ratio = (
            pca.explained_variance_ratio_.tolist() if hasattr(pca, "explained_variance_ratio_") else None
        )
        return transformed, component_labels, explained_variance, explained_ratio

    # Aplicamos el método de detección de outliers configurado y devolvemos la máscara booleana (True = outlier)
    def _detect_outliers(self, values: np.ndarray, config: OutlierConfig) -> np.ndarray:
        method = config.method
        params = {**config.params}

        if method in (
            OutlierMethod.isolation_forest,
            OutlierMethod.dbscan,
            OutlierMethod.local_outlier_factor,
        ):
            # Distance/split-based methods need comparable feature scales to
            # behave sensibly. Standardize ad-hoc for detection only (mirrors
            # ROP's _inlier_mask) — outlier detection now runs on raw data,
            # before the wizard's own Scaling step, so it can't rely on that.
            # Estandarizamos ad-hoc solo para la detección (media 0, desviación 1), evitando dividir entre cero
            mu = values.mean(axis=0)
            sd = values.std(axis=0)
            sd = np.where(sd == 0, 1.0, sd)
            values = (values - mu) / sd

        if method == OutlierMethod.isolation_forest:
            # Ejecutamos Isolation Forest: aísla puntos anómalos con árboles aleatorios
            contamination = params.pop("contamination", 0.05)
            model = IsolationForest(contamination=contamination, random_state=42, **params)
            predictions = model.fit_predict(values)
            return predictions == -1

        if method == OutlierMethod.dbscan:
            # Ejecutamos DBSCAN: los puntos que no caen en ningún cluster denso quedan marcados como ruido (-1)
            eps = params.pop("eps", 0.5)
            min_samples = params.pop("min_samples", 5)
            model = DBSCAN(eps=eps, min_samples=min_samples, **params)
            labels = model.fit_predict(values)
            return labels == -1

        if method == OutlierMethod.local_outlier_factor:
            # Ejecutamos Local Outlier Factor: compara la densidad local de cada punto contra sus vecinos
            n_neighbors = params.pop("n_neighbors", 20)
            lof = LocalOutlierFactor(n_neighbors=n_neighbors, novelty=False, **params)
            labels = lof.fit_predict(values)
            return labels == -1

        if method == OutlierMethod.zscore:
            # Marcamos como outlier cualquier fila donde alguna variable supere el umbral de z-score
            threshold = float(params.pop("threshold", 3.0))
            z_scores = np.abs(stats.zscore(values, axis=0, nan_policy="omit"))
            z_scores = np.nan_to_num(z_scores)
            return (z_scores > threshold).any(axis=1)

        if method == OutlierMethod.iqr:
            # Si no hay datos, devolvemos una máscara vacía
            if values.size == 0:
                return np.zeros(0, dtype=bool)
            # Marcamos como outlier cualquier fila fuera del rango intercuartil (Q1/Q3 ± multiplicador·IQR)
            multiplier = float(params.pop("multiplier", 1.5))
            q1 = np.percentile(values, 25, axis=0)
            q3 = np.percentile(values, 75, axis=0)
            iqr = q3 - q1
            lower_bound = q1 - multiplier * iqr
            upper_bound = q3 + multiplier * iqr
            mask = ((values < lower_bound) | (values > upper_bound)).any(axis=1)
            return mask

        # Si el método no coincide con ninguno de los soportados, lo señalamos como error
        raise OutlierDetectionError(f"Unsupported outlier method: {method}")

    # Armamos la lista de registros a persistir: datos crudos + valores escalados + componentes PCA + flag de outlier
    def _build_records_payload(
        self,
        df: pd.DataFrame,
        columns: Iterable[str],
        *,
        outlier_mask: np.ndarray,
        include_outliers: bool,
        scaled_array: Optional[np.ndarray] = None,
        scaled_labels: Optional[Sequence[str]] = None,
        component_array: Optional[np.ndarray] = None,
        component_labels: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        # Nos quedamos solo con las columnas pedidas que realmente existen en el dataframe
        store_columns = [col for col in columns if col in df.columns]
        records: List[Dict[str, Any]] = []

        # Extraemos los ids originales de fila (si existen) para enlazar cada registro procesado con su fuente
        ids = df["id"].tolist() if "id" in df.columns else [None] * len(df)

        # Recorremos cada fila del dataframe y armamos su payload de persistencia
        for idx, (row_index, row) in enumerate(df.iterrows()):
            is_outlier = bool(outlier_mask[idx])
            # Si es outlier y no se pidió incluirlos, saltamos esta fila
            if is_outlier and not include_outliers:
                continue

            # Construimos el diccionario de datos crudos, omitiendo columnas ausentes o con NaN
            record_data: Dict[str, Any] = {}
            for column in store_columns:
                if column not in row:
                    continue
                raw_value = row[column]
                if pd.isna(raw_value):
                    continue
                native_value = self._to_native(raw_value)
                if native_value is not None:
                    record_data[column] = native_value

            # Armamos el payload de valores escalados si el pipeline aplicó escalado
            scaled_payload: Optional[Dict[str, Any]] = None
            if scaled_array is not None and scaled_labels is not None:
                scaled_row = scaled_array[idx]
                scaled_payload = {
                    label: self._to_native(scaled_row[col_idx])
                    for col_idx, label in enumerate(scaled_labels)
                }

            # Armamos el payload de componentes PCA si el pipeline aplicó PCA
            components_payload: Optional[Dict[str, Any]] = None
            if component_array is not None and component_labels is not None:
                component_row = component_array[idx]
                components_payload = {
                    label: self._to_native(component_row[col_idx])
                    for col_idx, label in enumerate(component_labels)
                }

            # Resolvemos el id de registro original, tolerando ids inválidos o ausentes
            source_record_id: Optional[int] = None
            try:
                raw_id = ids[idx]
                if raw_id is not None and not pd.isna(raw_id):
                    source_record_id = int(raw_id)
            except (TypeError, ValueError):
                source_record_id = None

            record_payload = {
                "source_record_id": source_record_id,
                "data": record_data,
                "is_outlier": is_outlier,
                "scaled": scaled_payload,
                "components": components_payload,
            }
            records.append(record_payload)

        # Devolvemos todos los registros armados, listos para insertar
        return records

    # Convertimos cualquier valor (numpy, pandas, colecciones) a un tipo nativo de Python serializable en JSON
    @staticmethod
    def _to_native(value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, (np.generic,)):  # numpy scalar
            return OutlierDetectionService._to_native(value.item())

        if isinstance(value, np.ndarray):
            return [OutlierDetectionService._to_native(item) for item in value.tolist()]

        if isinstance(value, dict):
            return {
                str(key): OutlierDetectionService._to_native(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [OutlierDetectionService._to_native(item) for item in value]

        if isinstance(value, float):
            # Convertimos NaN/infinito a None porque JSON no los admite
            if np.isnan(value) or np.isinf(value):
                return None
            return value

        if isinstance(value, (datetime, date, time)):
            return value.isoformat()

        if isinstance(value, (timedelta, pd.Timedelta)):
            return value.total_seconds()

        if isinstance(value, np.timedelta64):
            return float(value / np.timedelta64(1, "s"))

        if isinstance(value, pd.Timestamp):
            return value.isoformat()

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")

        # Cualquier otro tipo ya nativo lo devolvemos tal cual
        return value

    # Generamos un nombre de dataset por defecto combinando el método de detección con una marca de tiempo
    @staticmethod
    def _generate_dataset_name(request: OutlierDetectionRequest) -> str:
        timestamp = utcnow().strftime("%Y%m%d-%H%M%S")
        return f"{request.outlier.method.value}-{timestamp}"

    # Convertimos un dataset ORM a su resumen para las vistas de listado
    def _to_summary(self, dataset: ProcessedDataset) -> ProcessedDatasetSummary:
        metrics = None
        if dataset.metrics:
            try:
                metrics = PipelineMetrics(**dataset.metrics)
            except Exception:  # pragma: no cover - resilience against legacy data
                # Toleramos datasets legacy cuyas métricas no calcen con el esquema actual
                logger.warning("Unable to parse metrics for dataset %s", dataset.id)

        return ProcessedDatasetSummary(
            id=dataset.id,
            well_id=dataset.well_id,
            name=dataset.name,
            status=dataset.status,
            record_count=dataset.record_count,
            created_at=dataset.created_at,
            created_by=dataset.created_by,
            metrics=metrics,
        )

    # Convertimos un dataset ORM a su vista de detalle (incluye descripción y config completa del pipeline)
    def _to_detail(self, dataset: ProcessedDataset) -> ProcessedDatasetDetail:
        metrics = None
        if dataset.metrics:
            try:
                metrics = PipelineMetrics(**dataset.metrics)
            except Exception:
                # Toleramos datasets legacy cuyas métricas no calcen con el esquema actual
                logger.warning("Unable to parse metrics for dataset %s", dataset.id)

        return ProcessedDatasetDetail(
            id=dataset.id,
            well_id=dataset.well_id,
            name=dataset.name,
            description=dataset.description,
            status=dataset.status,
            record_count=dataset.record_count,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            pipeline_config=dataset.pipeline_config or {},
            metrics=metrics,
        )
