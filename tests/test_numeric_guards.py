"""Tests de regresión para los guards numéricos añadidos a los services.

Cubren los casos que antes lanzaban ZeroDivisionError/KeyError o producían
NaN/inf silenciosos: DataFrames vacíos, columnas constantes, índices no
contiguos y rangos invertidos.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.data_cleaner import DataCleaner
from app.services.data_transformer import DataTransformer
from app.services.event_detector import EventDetector
from app.services.interpolator import TimeDepthInterpolator


class TestDataCleaner:
    def test_remove_outliers_empty_dataframe(self):
        df = pd.DataFrame({"x": pd.Series(dtype=float)})
        result = DataCleaner.remove_outliers(df, "x", method="iqr")
        assert result.empty

    def test_remove_outliers_zscore_constant_column(self):
        df = pd.DataFrame({"x": [5.0] * 10})
        result = DataCleaner.remove_outliers(df, "x", method="zscore")
        # Con desviación cero nada es outlier: no se elimina ninguna fila
        assert len(result) == 10

    def test_fill_missing_forward_uses_non_deprecated_api(self):
        df = pd.DataFrame({"x": [1.0, np.nan, 3.0]})
        result = DataCleaner.fill_missing_values(df, "x", method="forward")
        assert result["x"].tolist() == [1.0, 1.0, 3.0]


class TestDataTransformer:
    def test_normalize_constant_column_minmax(self):
        df = pd.DataFrame({"x": [7.0] * 5})
        result = DataTransformer.normalize_column(df, "x", method="minmax")
        assert (result["x_normalized"] == 0.0).all()

    def test_normalize_constant_column_zscore(self):
        df = pd.DataFrame({"x": [7.0] * 5})
        result = DataTransformer.normalize_column(df, "x", method="zscore")
        assert (result["x_normalized"] == 0.0).all()

    def test_resample_with_zero_target_points(self):
        df = pd.DataFrame({"x": range(100)})
        # Antes: ZeroDivisionError; ahora devuelve el DataFrame sin cambios
        result = DataTransformer.resample_data(df, target_points=0)
        assert len(result) == 100

    def test_resample_with_negative_target_points(self):
        df = pd.DataFrame({"x": range(100)})
        result = DataTransformer.resample_data(df, target_points=-5)
        assert len(result) == 100


class TestEventDetector:
    def test_rapid_changes_with_non_contiguous_index(self):
        # DataFrame filtrado: índice 0, 5, 9 — antes KeyError por df.loc[idx-1]
        df = pd.DataFrame(
            {"pressure": [100.0, 100.0, 500.0]},
            index=[0, 5, 9],
        )
        events = EventDetector.detect_rapid_changes(df, "pressure", threshold_pct=50.0)
        assert len(events) == 1
        assert events[0]["previous_value"] == 100.0
        assert events[0]["current_value"] == 500.0

    def test_rapid_changes_ignores_inf_from_zero_previous(self):
        df = pd.DataFrame({"pressure": [0.0, 100.0]})
        # 0 → 100 es un cambio infinito en porcentaje; no debe reventar ni contarse
        events = EventDetector.detect_rapid_changes(df, "pressure", threshold_pct=50.0)
        assert events == []

    def test_anomalies_zscore_constant_column(self):
        df = pd.DataFrame({"x": [3.0] * 20})
        events = EventDetector.detect_anomalies(df, "x", method="zscore")
        assert events == []


class TestInterpolator:
    def test_uniform_grid_inverted_range(self):
        # Antes: np.arange devolvía [] y min()/max() fallaban aguas arriba
        assert TimeDepthInterpolator.create_uniform_depth_grid(1000.0, 500.0) == []

    def test_uniform_grid_non_positive_step(self):
        assert TimeDepthInterpolator.create_uniform_depth_grid(0.0, 100.0, step=0) == []
        assert TimeDepthInterpolator.create_uniform_depth_grid(0.0, 100.0, step=-1) == []

    def test_uniform_grid_valid_range(self):
        grid = TimeDepthInterpolator.create_uniform_depth_grid(0.0, 10.0, step=5.0)
        assert grid == [0.0, 5.0, 10.0]

    def test_interpolate_does_not_extrapolate(self):
        time_df = pd.DataFrame(
            {
                "bit_depth_feet": [100.0, 200.0, 300.0],
                "rate_of_penetration_ft_per_hr": [50.0, 60.0, 70.0],
            }
        )
        result = TimeDepthInterpolator.interpolate_to_depth(
            time_df,
            target_depths=[150.0, 1000.0],
            value_cols=["rate_of_penetration_ft_per_hr"],
        )
        inside = result.loc[result["bit_depth_feet"] == 150.0, "rate_of_penetration_ft_per_hr"]
        outside = result.loc[result["bit_depth_feet"] == 1000.0, "rate_of_penetration_ft_per_hr"]
        assert inside.iloc[0] == pytest.approx(55.0)
        # Fuera del rango medido: NaN, no un valor extrapolado inventado
        assert np.isnan(outside.iloc[0])
