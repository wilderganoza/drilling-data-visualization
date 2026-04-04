import { apiClient } from '../client';

export interface ScalingConfig {
  method: 'none' | 'standard' | 'minmax' | 'robust' | 'maxabs';
  params?: Record<string, unknown>;
}

export interface PCAConfig {
  enabled: boolean;
  n_components?: number | null | undefined;
  whiten?: boolean;
  svd_solver?: string;
}

export type OutlierMethod =
  | 'isolation_forest'
  | 'dbscan'
  | 'local_outlier_factor'
  | 'zscore'
  | 'iqr';

export interface OutlierConfig {
  method: OutlierMethod;
  params?: Record<string, unknown>;
  mark_outliers?: boolean;
}

export interface OutlierDetectionRequest {
  well_id: number;
  dataset_name?: string | null;
  description?: string | null;
  variables: string[];
  scaling?: ScalingConfig;
  pca?: PCAConfig;
  outlier?: OutlierConfig;
  max_records?: number | null;
  include_columns?: string[] | null;
}

export interface PipelineMetrics {
  total_records: number;
  processed_records: number;
  outlier_records: number;
  outlier_percentage: number;
  variables: string[];
  dropped_records: number;
  scaled_feature_labels?: string[] | null;
  pca_component_labels?: string[] | null;
  explained_variance?: number[] | null;
  explained_variance_ratio?: number[] | null;
}

export interface ProcessedDatasetSummary {
  id: number;
  well_id: number;
  name: string;
  status: string;
  record_count: number | null;
  created_at: string;
  created_by: number | null;
  metrics?: PipelineMetrics | null;
}

export interface ProcessedDatasetDetail extends ProcessedDatasetSummary {
  description: string | null;
  updated_at: string;
  pipeline_config: Record<string, unknown>;
}

export interface OutlierDetectionResponse {
  dataset: ProcessedDatasetDetail;
}

export interface ProcessedRecordData {
  source_record_id: number | null;
  is_outlier: boolean;
  data: Record<string, unknown>;
  scaled?: Record<string, unknown> | null;
  components?: Record<string, unknown> | null;
}

export interface ProcessedDataResponse {
  dataset_id: number;
  include_outliers: boolean;
  total_records: number;
  page: number;
  page_size: number;
  records: ProcessedRecordData[];
}

const basePath = '/outliers';
const MIN_PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 5000;

export const runOutlierDetection = async (
  payload: OutlierDetectionRequest,
): Promise<OutlierDetectionResponse> => {
  const response = await apiClient.post<OutlierDetectionResponse>(`${basePath}/datasets`, payload);
  return response.data;
};

export const listProcessedDatasets = async (
  wellId: number,
): Promise<ProcessedDatasetSummary[]> => {
  const response = await apiClient.get<ProcessedDatasetSummary[]>(`${basePath}/datasets`, {
    params: { well_id: wellId },
  });
  return response.data;
};

export const getProcessedDataset = async (
  datasetId: number,
): Promise<ProcessedDatasetDetail> => {
  const response = await apiClient.get<ProcessedDatasetDetail>(`${basePath}/datasets/${datasetId}`);
  return response.data;
};

export const getProcessedDatasetData = async (
  datasetId: number,
  options?: { include_outliers?: boolean; page?: number; page_size?: number },
): Promise<ProcessedDataResponse> => {
  const requestedPageSize = options?.page_size ?? 500;
  const safePageSize = Math.min(MAX_PAGE_SIZE, Math.max(MIN_PAGE_SIZE, requestedPageSize));
  const response = await apiClient.get<ProcessedDataResponse>(`${basePath}/datasets/${datasetId}/data`, {
    params: {
      include_outliers: options?.include_outliers ?? false,
      page: options?.page ?? 1,
      page_size: safePageSize,
    },
  });
  return response.data;
};

export const deleteProcessedDataset = async (datasetId: number): Promise<void> => {
  await apiClient.delete(`${basePath}/datasets/${datasetId}`);
};
