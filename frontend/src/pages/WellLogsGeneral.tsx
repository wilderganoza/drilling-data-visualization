import React, { useMemo, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { WellLogView } from '../components/charts/WellLogView';
import { Card, CardHeader, CardTitle, CardContent, PageHeader, InlineLoader, Button, SearchableSelect } from '../components/ui';
import { useWells, useDepthSampleData } from '../hooks';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames } from '../constants/parameterLabels';

export const WellLogsGeneral: React.FC = () => {
  const { data: wells } = useWells();
  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const { data: datasets, isLoading: isDatasetsLoading } = useOutlierDatasets(selectedWellId);
  const { data: processedDataset, isLoading: isProcessedLoading } = useOutlierDatasetData(
    appliedDatasetId === 'raw' ? null : appliedDatasetId,
    { includeOutliers: false, pageSize: 5000 }
  );
  const { data: rawDepthData, isLoading: isRawLoading } = useDepthSampleData(
    appliedDatasetId === 'raw' && appliedWellId ? appliedWellId : 0,
    50000
  );

  const dataRecords = appliedDatasetId === 'raw' ? rawDepthData?.data ?? [] : (processedDataset?.records ?? []).map((record) => record.data ?? {});
  const isDataLoading = appliedDatasetId === 'raw' ? isRawLoading : isProcessedLoading;

  const trackedParams = getAllParameterNames();

  const availableParameters = useMemo(() => {
    if (!dataRecords.length) return [] as string[];
    return trackedParams.filter((param) => param in dataRecords[0]);
  }, [dataRecords, trackedParams]);

  const wellOptions = useMemo(
    () => (wells?.wells ?? []).map((w: any) => ({ value: w.id, label: w.well_name })),
    [wells],
  );

  const datasetOptions = useMemo(() => {
    const opts: Array<{ value: string | number; label: string }> = [{ value: 'raw', label: 'Raw data (original)' }];
    (datasets ?? []).forEach((d) => opts.push({ value: d.id, label: d.name || `Dataset #${d.id}` }));
    return opts;
  }, [datasets]);

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Well Logs Viewer"
          subtitle="Multi-track well log visualization for any well"
        />

        <Card>
          <CardHeader>
            <CardTitle>Select Well</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="relative">
                  <SearchableSelect
                    label="Well"
                    options={wellOptions}
                    value={selectedWellId}
                    onChange={(v) => {
                      setSelectedWellId(Number(v));
                      setSelectedDatasetId('raw');
                    }}
                    placeholder="Select a well"
                  />
                </div>

                {selectedWellId && (
                  <div className="relative">
                    <SearchableSelect
                      label="Dataset"
                      options={datasetOptions}
                      value={selectedDatasetId}
                      onChange={(v) => setSelectedDatasetId(v === 'raw' ? 'raw' : Number(v))}
                      placeholder={isDatasetsLoading ? 'Loading datasets...' : 'Select data source'}
                      disabled={isDatasetsLoading}
                    />
                  </div>
                )}
              </div>

              <div className="flex justify-end">
                <Button
                  onClick={() => {
                    setAppliedWellId(selectedWellId);
                    setAppliedDatasetId(selectedDatasetId);
                  }}
                  disabled={!selectedWellId}
                >
                  Apply
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {!appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p style={{ color: 'var(--color-text-muted)' }}>Select a well to view logs</p>
              </div>
            </CardContent>
          </Card>
        )}

        {isDataLoading && appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center">
                <InlineLoader message="Loading well log data..." />
              </div>
            </CardContent>
          </Card>
        )}

        {!isDataLoading && appliedWellId && dataRecords.length > 0 && (
          <WellLogView
            data={dataRecords}
            depthKey="bit_depth_feet"
            availableParameters={availableParameters}
            height={800}
          />
        )}

        {!isDataLoading && appliedWellId && dataRecords.length === 0 && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p style={{ color: 'var(--color-text-muted)' }}>
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
