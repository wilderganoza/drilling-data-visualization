import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  downloadExportXlsx,
  ExportCaseType,
  ExportColumnsResponse,
  listExportColumns,
} from '../api/endpoints/exports';

export const useExportColumns = (
  wellId: number | null,
  caseType: ExportCaseType | null,
  processedDatasetId: number | null,
) => {
  return useQuery<ExportColumnsResponse>({
    queryKey: ['exports', 'columns', wellId, caseType, processedDatasetId],
    queryFn: () =>
      listExportColumns({
        wellId: wellId!,
        caseType: caseType!,
        processedDatasetId:
          caseType === ExportCaseType.PROCESSED ? processedDatasetId ?? undefined : undefined,
      }),
    enabled: Boolean(
      wellId &&
        caseType &&
        (caseType === ExportCaseType.RAW || (caseType === ExportCaseType.PROCESSED && processedDatasetId)),
    ),
    staleTime: 5 * 60 * 1000,
  });
};

export const useExportXlsx = () => {
  return useCallback(
    (payload: Parameters<typeof downloadExportXlsx>[0]) => downloadExportXlsx(payload),
    [],
  );
};
