import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

interface DataQueryParams {
  wellId: number;
  minDepth?: number;
  maxDepth?: number;
  columns?: string[];
  limit?: number;
}

interface WellDataPoint {
  [key: string]: any;
}

interface WellDataResponse {
  well_id: number;
  total_records: number;
  data: WellDataPoint[];
}

const getDepthData = async (params: DataQueryParams): Promise<WellDataResponse> => {
  const { wellId, minDepth, maxDepth, columns, limit = 1000 } = params;
  const queryParams: any = { limit };
  if (minDepth !== undefined) queryParams.min_depth = minDepth;
  if (maxDepth !== undefined) queryParams.max_depth = maxDepth;
  if (columns && columns.length > 0) queryParams.columns = columns.join(',');
  const response = await apiClient.get<WellDataResponse>(
    `/data/depth/${wellId}/query`,
    { params: queryParams }
  );
  return response.data;
};

const getDepthSampleData = async (wellId: number, sampleSize: number = 1000) => {
  const response = await apiClient.get<WellDataResponse>(
    `/data/depth/sample/${wellId}`,
    { params: { sample_size: sampleSize } }
  );
  return response.data;
};

export const useDepthData = (params: DataQueryParams) => {
  return useQuery({
    queryKey: ['depthData', params],
    queryFn: () => getDepthData(params),
    enabled: params.wellId > 0,
    staleTime: 10 * 60 * 1000,
  });
};

export const useDepthSampleData = (wellId: number, sampleSize: number = 1000) => {
  return useQuery({
    queryKey: ['depthSampleData', wellId, sampleSize],
    queryFn: () => getDepthSampleData(wellId, sampleSize),
    enabled: wellId > 0,
    staleTime: 10 * 60 * 1000,
  });
};
