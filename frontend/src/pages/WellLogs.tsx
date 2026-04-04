import React, { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/layout/Layout';
import { WellLogView } from '../components/charts/WellLogView';
import { useDepthSampleData } from '../hooks';
import { Card, CardContent, PageHeader } from '../components/ui';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames } from '../constants/parameterLabels';

const fieldStyle: CSSProperties = {
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius)',
  color: 'var(--color-text)',
  boxShadow: 'none',
};

export const WellLogs: React.FC = () => {
  const { wellId } = useParams<{ wellId: string }>();
  const numericWellId = Number(wellId);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const { data: datasets, isLoading: isDatasetsLoading } = useOutlierDatasets(Number.isFinite(numericWellId) ? numericWellId : null);
  const { data: processedDataset, isLoading: isProcessedLoading } = useOutlierDatasetData(
    appliedDatasetId === 'raw' ? null : appliedDatasetId,
    { includeOutliers: false, pageSize: 5000 }
  );
  const { data: rawDepthData, isLoading: isRawLoading } = useDepthSampleData(
    appliedDatasetId === 'raw' && Number.isFinite(numericWellId) ? numericWellId : 0,
    50000
  );

  const dataRecords = appliedDatasetId === 'raw' ? rawDepthData?.data ?? [] : (processedDataset?.records ?? []).map((record) => record.data ?? {});
  const isDataLoading = appliedDatasetId === 'raw' ? isRawLoading : isProcessedLoading;

  // Get only the 28 tracked parameters from parameterLabels
  const trackedParams = getAllParameterNames();
  const availableParameters = useMemo(() => {
    if (!dataRecords.length) return [] as string[];
    return trackedParams.filter((param) => param in dataRecords[0]);
  }, [dataRecords, trackedParams]);

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Well Logs"
          subtitle="Multi-track well log visualization"
        />

        <Card>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                Dataset
              </label>
              <select
                value={selectedDatasetId === 'raw' ? 'raw' : String(selectedDatasetId)}
                onChange={(event) => {
                  const value = event.target.value;
                  setSelectedDatasetId(value === 'raw' ? 'raw' : Number(value));
                }}
                className="w-full px-3 py-2 text-sm focus:outline-none"
                style={fieldStyle}
                disabled={!Number.isFinite(numericWellId)}
              >
                <option value="raw">Raw data (original)</option>
                {datasets?.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name || `Dataset #${dataset.id}`}
                  </option>
                ))}
              </select>
              {isDatasetsLoading && (
                <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  Loading datasets...
                </p>
              )}
              {!isDatasetsLoading && datasets && datasets.length === 0 && (
                <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  No processed datasets available for this well yet.
                </p>
              )}
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => setAppliedDatasetId(selectedDatasetId)}
                disabled={!Number.isFinite(numericWellId)}
              >
                Apply
              </Button>
            </div>
          </CardContent>
        </Card>

        {isDataLoading && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                <p className="ml-4 text-gray-400">Loading well log data...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {!isDataLoading && dataRecords.length > 0 && (
          <WellLogView
            data={dataRecords}
            depthKey="bit_depth_feet"
            availableParameters={availableParameters}
            height={800}
          />
        )}

        {!isDataLoading && dataRecords.length === 0 && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-gray-400 text-lg">
                  {appliedDatasetId === 'raw'
                    ? 'No data available for this well.'
                    : 'This processed dataset has no records to display.'}
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};

