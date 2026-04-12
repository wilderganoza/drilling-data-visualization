import React, { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/layout/Layout';
import { WellLogView } from '../components/charts/WellLogView';
import { useDepthSampleData } from '../hooks';
import { Card, CardContent, PageHeader, InlineLoader, SearchableSelect, Button } from '../components/ui';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames } from '../constants/parameterLabels';

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
              <SearchableSelect
                label="Dataset"
                options={[
                  { value: 'raw', label: 'Raw data (original)' },
                  ...(datasets ?? []).map((d) => ({ value: d.id, label: d.name || `Dataset #${d.id}` })),
                ]}
                value={selectedDatasetId}
                onChange={(v) => setSelectedDatasetId(v === 'raw' ? 'raw' : Number(v))}
                disabled={!Number.isFinite(numericWellId)}
                placeholder={isDatasetsLoading ? 'Loading datasets...' : 'Select dataset'}
              />
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
              <div className="flex items-center justify-center py-4">
                <InlineLoader message="Loading well log data..." />
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

