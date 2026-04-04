// Importar useQuery de TanStack Query para manejo de estado del servidor
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { getProcessedDatasetData } from '../api/endpoints/outliers';
import { getAllParameterNames } from '../constants/parameterLabels';

// Interfaz para respuesta de reporte de calidad
interface QualityReportResponse {
  well_id: number; // ID del pozo
  total_records: number; // Total de registros analizados
  columns_analyzed: number; // Número de columnas analizadas
  missing_values: { // Valores faltantes por columna
    [key: string]: number;
  };
  outliers_detected: { // Outliers detectados por columna
    [key: string]: number;
  };
  data_ranges: { // Rangos de datos por columna
    [key: string]: {
      min: number; // Valor mínimo
      max: number; // Valor máximo
      mean: number; // Promedio
      std: number; // Desviación estándar
      p25?: number;
      p50?: number;
      p75?: number;
      null_pct?: number;
    };
  };
  quality_score: number; // Puntuación de calidad general
}

// Función para obtener reporte de calidad de datos
const getQualityReport = async (wellId: number): Promise<QualityReportResponse> => {
  // Realizar petición GET al endpoint de reporte de calidad
  const response = await apiClient.get<QualityReportResponse>(
    `/processing/quality-report/${wellId}`
  );
  // Retornar datos de la respuesta
  return response.data;
};

const buildReportFromDataset = (records: Array<Record<string, unknown>>, wellId: number): QualityReportResponse => {
  const total_records = records.length;
  const trackedParams = new Set(getAllParameterNames());
  const columnSet = new Set<string>();
  records.forEach((record) => {
    Object.keys(record).forEach((key) => columnSet.add(key));
  });

  const all_numeric_cols = Array.from(columnSet).filter((column) => {
    if (column === 'id' || column === 'well_id') return false;
    return records.some((record) => {
      const value = record[column];
      return typeof value === 'number' && Number.isFinite(value);
    });
  });

  const missing_values: Record<string, number> = {};
  const outliers_detected: Record<string, number> = {};
  const data_ranges: QualityReportResponse['data_ranges'] = {};

  all_numeric_cols.forEach((column) => {
    let missing = 0;
    records.forEach((record) => {
      const value = record[column];
      if (value === null || value === undefined || value === '' || value === 0) {
        missing += 1;
      }
    });
    missing_values[column] = missing;
  });

  all_numeric_cols.forEach((column) => {
    if (!trackedParams.has(column)) {
      return;
    }

    const colValues = records
      .map((record) => record[column])
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));

    if (!colValues.length) {
      return;
    }

    const sorted = [...colValues].sort((a, b) => a - b);
    const q1 = sorted[Math.floor((sorted.length - 1) * 0.25)];
    const q3 = sorted[Math.floor((sorted.length - 1) * 0.75)];
    const iqr = q3 - q1;
    const lower = q1 - 1.5 * iqr;
    const upper = q3 + 1.5 * iqr;
    const outliers = colValues.filter((value) => value < lower || value > upper).length;

    const nonZeroValues = sorted.filter((value) => value !== 0);
    const valuesForStats = nonZeroValues.length > 0 ? nonZeroValues : sorted;
    const mean = valuesForStats.reduce((sum, value) => sum + value, 0) / valuesForStats.length;
    const variance = valuesForStats.reduce((sum, value) => sum + (value - mean) ** 2, 0) / valuesForStats.length;
    const percentile = (p: number) => {
      if (valuesForStats.length === 1) return valuesForStats[0];
      const index = (valuesForStats.length - 1) * p;
      const lowerIndex = Math.floor(index);
      const upperIndex = Math.ceil(index);
      if (lowerIndex === upperIndex) return valuesForStats[lowerIndex];
      return valuesForStats[lowerIndex] + (valuesForStats[upperIndex] - valuesForStats[lowerIndex]) * (index - lowerIndex);
    };

    outliers_detected[column] = outliers;
    data_ranges[column] = {
      min: valuesForStats[0] ?? 0,
      max: valuesForStats[valuesForStats.length - 1] ?? 0,
      mean,
      std: Math.sqrt(variance),
      p25: valuesForStats.length >= 4 ? percentile(0.25) : undefined,
      p50: percentile(0.5),
      p75: valuesForStats.length >= 4 ? percentile(0.75) : undefined,
      null_pct: total_records > 0 ? (missing_values[column] / total_records) * 100 : 0,
    };
  });

  const total_cells = total_records * all_numeric_cols.length;
  const missing_cells = Object.values(missing_values).reduce((sum, value) => sum + value, 0);
  const outlier_cells = Object.values(outliers_detected).reduce((sum, value) => sum + value, 0);
  const quality_score = total_cells > 0
    ? Math.max(0, 100 - (missing_cells / total_cells * 50) - (outlier_cells / total_cells * 50))
    : 0;

  return {
    well_id: wellId,
    total_records,
    columns_analyzed: all_numeric_cols.length,
    missing_values,
    outliers_detected,
    data_ranges,
    quality_score: Number.isFinite(quality_score) ? quality_score : 0,
  };
};

interface UseQualityReportOptions {
  datasetId?: 'raw' | number;
  datasetLimit?: number;
}

// Hook para obtener reporte de calidad usando React Query
export const useQualityReport = (wellId: number | null, options: UseQualityReportOptions = {}) => {
  const datasetId = options.datasetId ?? 'raw';
  const datasetLimit = options.datasetLimit ?? 5000;

  return useQuery({
    queryKey: ['quality', wellId, datasetId], // Clave única para la consulta
    enabled: Boolean(wellId && wellId > 0), // Solo ejecutar si wellId es válido
    staleTime: 15 * 60 * 1000, // Datos considerados frescos por 15 minutos
    queryFn: async () => {
      if (!wellId || wellId <= 0) {
        throw new Error('Invalid wellId');
      }

      if (datasetId === 'raw' || datasetId === undefined) {
        return getQualityReport(wellId);
      }

      const processedResponse = await getProcessedDatasetData(datasetId, {
        include_outliers: false,
        page: 1,
        page_size: datasetLimit,
      });
      const processedRecords = (processedResponse.records ?? []).map((record) => record.data ?? {});
      return buildReportFromDataset(processedRecords, wellId);
    },
  });
};
