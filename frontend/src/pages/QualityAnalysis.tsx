/**
 * Quality Analysis Page - Data quality assessment and reporting
 */
import React, { useState } from 'react';
import type { CSSProperties } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/layout';
import { Card, CardContent, Button, PageHeader } from '../components/ui';
import { QualityReport } from '../components/analysis';
import { useWell, useQualityReport } from '../hooks';
import { useOutlierDatasets } from '../hooks/useOutlierDetection';

const fieldStyle: CSSProperties = {
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius)',
  color: 'var(--color-text)',
  boxShadow: 'none',
};

export const QualityAnalysis: React.FC = () => {
  const { wellId } = useParams<{ wellId: string }>();
  const wellIdNum = wellId ? parseInt(wellId) : 0;
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');

  const { data: wellData, isLoading: wellLoading } = useWell(wellIdNum);
  const { data: datasets, isLoading: isDatasetsLoading } = useOutlierDatasets(Number.isFinite(wellIdNum) ? wellIdNum : null);
  const { data: qualityData, isLoading: qualityLoading, refetch } = useQualityReport(wellIdNum, {
    datasetId: appliedDatasetId,
    datasetLimit: 10000,
  });

  const isLoading = wellLoading || qualityLoading;
  const selectedDatasetSummary = appliedDatasetId === 'raw'
    ? null
    : datasets?.find((dataset) => dataset.id === appliedDatasetId) ?? null;
  const totalRecords = qualityData?.total_records ?? 0;
  const showEmptyState = !isLoading && totalRecords === 0;

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Data Quality Analysis"
          subtitle={`${wellData?.well_name || `Well ${wellId}`} - Comprehensive quality assessment`}
          actions={(
            <Button onClick={() => refetch()} disabled={isLoading}>
              {isLoading ? 'Analyzing…' : 'Refresh Report'}
            </Button>
          )}
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
                disabled={!Number.isFinite(wellIdNum) || wellIdNum <= 0}
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
                  Loading datasets…
                </p>
              )}
              {!isDatasetsLoading && datasets && datasets.length === 0 && (
                <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  No processed datasets available for this well yet.
                </p>
              )}
            </div>

            {selectedDatasetSummary && (
              <div className="rounded-md border p-3 text-sm" style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}>
                <p className="font-semibold mb-1">Dataset summary</p>
                <div className="grid grid-cols-2 gap-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  <span>Records: {selectedDatasetSummary.record_count ?? '—'}</span>
                  <span>Status: {selectedDatasetSummary.status}</span>
                  <span>Created: {new Date(selectedDatasetSummary.created_at).toLocaleString()}</span>
                  <span>Outliers: {selectedDatasetSummary.metrics?.outlier_records ?? '—'}</span>
                </div>
              </div>
            )}
            <div className="flex justify-end">
              <Button
                onClick={() => setAppliedDatasetId(selectedDatasetId)}
                disabled={!Number.isFinite(wellIdNum) || wellIdNum <= 0}
              >
                Open Report
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
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

        {/* Quality Report */}
        {!isLoading && !showEmptyState && qualityData && <QualityReport report={qualityData} />}

        {/* No Data State */}
        {showEmptyState && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-gray-400 text-lg">
                  {appliedDatasetId === 'raw'
                    ? 'No quality data available.'
                    : 'This processed dataset has no records to analyze.'}
                </p>
                <Button className="mt-4" onClick={() => refetch()}>
                  Refresh Report
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};
