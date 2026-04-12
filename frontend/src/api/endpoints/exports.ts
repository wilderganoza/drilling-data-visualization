import apiClient from '../client';

export enum ExportCaseType {
  RAW = 'raw',
  PROCESSED = 'processed',
}

export interface ExportColumn {
  key: string;
  label: string;
  group?: string | null;
}

export interface ExportColumnsResponse {
  well_id: number;
  case_type: ExportCaseType;
  dataset_id?: number | null;
  columns: ExportColumn[];
}

export interface ExportXlsxRequest {
  well_id: number;
  case_type: ExportCaseType;
  processed_dataset_id?: number;
  columns?: string[];
  include_all_columns?: boolean;
  include_outliers?: boolean;
}

export const listExportColumns = async (params: {
  wellId: number;
  caseType: ExportCaseType;
  processedDatasetId?: number;
}): Promise<ExportColumnsResponse> => {
  const response = await apiClient.get<ExportColumnsResponse>('/exports/columns', {
    params: {
      well_id: params.wellId,
      case_type: params.caseType,
      processed_dataset_id: params.processedDatasetId,
    },
  });
  return response.data;
};

export const downloadExportXlsx = async (payload: ExportXlsxRequest): Promise<Blob> => {
  const response = await apiClient.post('/exports/xlsx', payload, {
    responseType: 'blob',
  });
  return response.data as Blob;
};
