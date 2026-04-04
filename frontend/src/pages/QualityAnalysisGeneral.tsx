import React, { useState } from 'react';
import type { CSSProperties } from 'react';
import { Layout } from '../components/layout/Layout';
import { Card, CardHeader, CardTitle, CardContent, Button, PageHeader } from '../components/ui';
import { QualityReport } from '../components/analysis';
import { useWells, useQualityReport } from '../hooks';
import { useOutlierDatasets } from '../hooks/useOutlierDetection';

const fieldStyle: CSSProperties = {
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius)',
  color: 'var(--color-text)',
  boxShadow: 'none',
};

export const QualityAnalysisGeneral: React.FC = () => {
  const { data: wells } = useWells();
  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');

  const handleOpenReport = () => {
    if (!selectedWellId) return;
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
  };

  const { data: datasets, isLoading: isDatasetsLoading } = useOutlierDatasets(selectedWellId);

  const { data: qualityData, isLoading, refetch } = useQualityReport(appliedWellId ?? null, {
    datasetId: appliedDatasetId,
    datasetLimit: 5000,
  });

  const totalRecords = qualityData?.total_records ?? 0;
  const showGenerateButton = !isLoading && totalRecords === 0;

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Quality Report"
          subtitle="Select a well to generate and view the data quality report"
        />

        <Card>
          <CardHeader>
            <CardTitle>Select Well</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                Well
              </label>
              <select
                value={selectedWellId || ''}
                onChange={(e) => setSelectedWellId(Number(e.target.value))}
                className="w-full px-3 py-2 text-sm focus:outline-none"
                style={fieldStyle}
              >
                <option value="">-- Select a well --</option>
                {wells?.wells?.map((well: any) => (
                  <option key={well.id} value={well.id}>
                    {well.well_name}
                  </option>
                ))}
              </select>

              {selectedWellId && (
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
              )}

              <div className="flex justify-end">
                <Button onClick={handleOpenReport} disabled={!selectedWellId}>
                  Open Report
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {!appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-gray-400 text-lg">Select a well to view its quality report</p>
              </div>
            </CardContent>
          </Card>
        )}

        {appliedWellId && (
          <>
            {isLoading && (
              <Card>
                <CardContent className="py-12">
                  <div className="flex items-center justify-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    <p className="ml-4 text-gray-400">Analyzing data quality...</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {!isLoading && qualityData && totalRecords > 0 && <QualityReport report={qualityData} />}

            {showGenerateButton && (
              <Card>
                <CardContent className="py-12">
                  <div className="text-center">
                    <p className="text-gray-400 text-lg">
                      {appliedDatasetId === 'raw'
                        ? 'No quality data available.'
                        : 'This processed dataset has no records to analyze.'}
                    </p>
                    <Button className="mt-4" onClick={() => refetch()} disabled={isLoading}>
                      Refresh Report
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </Layout>
  );
};
