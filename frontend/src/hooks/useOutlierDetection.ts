import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteProcessedDataset,
  getProcessedDataset,
  getProcessedDatasetData,
  listAllProcessedDatasets,
  listProcessedDatasets,
  rerunOutlierDetection,
  runOutlierDetection,
  OutlierDetectionRequest,
  OutlierDetectionResponse,
  ProcessedDataResponse,
  ProcessedDatasetDetail,
  ProcessedDatasetSummary,
} from '../api/endpoints/outliers';

const DATASET_LIST_KEY = ['outliers', 'datasets'];

export const useOutlierDatasets = (wellId: number | null) => {
  return useQuery<ProcessedDatasetSummary[]>({
    queryKey: [...DATASET_LIST_KEY, wellId],
    queryFn: () => {
      if (!wellId) {
        return Promise.resolve([]);
      }
      return listProcessedDatasets(wellId);
    },
    enabled: Boolean(wellId),
    staleTime: 5 * 60 * 1000,
  });
};

export const useOutlierDataset = (datasetId: number | null) => {
  return useQuery<ProcessedDatasetDetail | null>({
    queryKey: ['outliers', 'dataset', datasetId],
    queryFn: () => {
      if (!datasetId) {
        return Promise.resolve(null);
      }
      return getProcessedDataset(datasetId);
    },
    enabled: Boolean(datasetId),
    staleTime: 5 * 60 * 1000,
  });
};

export const useOutlierDatasetData = (
  datasetId: number | null,
  options: { includeOutliers?: boolean; page?: number; pageSize?: number } = {},
) => {
  const normalizedPageSize = Math.min(5000, Math.max(10, options.pageSize ?? 500));
  return useQuery<ProcessedDataResponse | null>({
    queryKey: [
      'outliers',
      'dataset-data',
      datasetId,
      options.includeOutliers ?? false,
      options.page ?? 1,
      normalizedPageSize,
    ],
    queryFn: () => {
      if (!datasetId) {
        return Promise.resolve(null);
      }
      return getProcessedDatasetData(datasetId, {
        include_outliers: options.includeOutliers,
        page: options.page,
        page_size: normalizedPageSize,
      });
    },
    enabled: Boolean(datasetId),
    staleTime: 1 * 60 * 1000,
  });
};

export const useRunOutlierDetection = () => {
  const queryClient = useQueryClient();
  return useMutation<
    OutlierDetectionResponse,
    Error,
    { payload: OutlierDetectionRequest; replaceDatasetId?: number | null }
  >({
    mutationFn: ({ payload, replaceDatasetId }) =>
      replaceDatasetId
        ? rerunOutlierDetection(replaceDatasetId, payload)
        : runOutlierDetection(payload),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: [...DATASET_LIST_KEY, response.dataset.well_id] });
      queryClient.invalidateQueries({ queryKey: ['outliers', 'datasets-all'] });
      queryClient.invalidateQueries({ queryKey: ['outliers', 'dataset', response.dataset.id] });
      queryClient.invalidateQueries({ queryKey: ['outliers', 'dataset-data'] });
    },
  });
};

export const useAllOutlierDatasets = () => {
  return useQuery<ProcessedDatasetSummary[]>({
    queryKey: ['outliers', 'datasets-all'],
    queryFn: () => listAllProcessedDatasets(),
    staleTime: 60 * 1000,
  });
};

export const useDeleteOutlierDatasetById = () => {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (datasetId) => deleteProcessedDataset(datasetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outliers', 'datasets-all'] });
      queryClient.invalidateQueries({ queryKey: DATASET_LIST_KEY });
    },
  });
};

export const useDeleteOutlierDataset = () => {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { datasetId: number; wellId: number }>({
    mutationFn: ({ datasetId }) => deleteProcessedDataset(datasetId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: [...DATASET_LIST_KEY, variables.wellId] });
    },
  });
};
