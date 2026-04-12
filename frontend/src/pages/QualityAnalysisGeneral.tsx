import React, { useMemo, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { Card, CardHeader, CardTitle, CardContent, Button, PageHeader, InlineLoader, SearchableSelect } from '../components/ui';
import { QualityReport } from '../components/analysis';
import { useWells, useQualityReport } from '../hooks';
import { useOutlierDatasets } from '../hooks/useOutlierDetection';

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

  const wellOptions = useMemo(
    () => (wells?.wells ?? []).map((w: any) => ({ value: w.id, label: w.well_name })),
    [wells],
  );

  const datasetOptions = useMemo(() => {
    const opts: Array<{ value: string | number; label: string }> = [{ value: 'raw', label: 'Raw data (original)' }];
    (datasets ?? []).forEach((d) => opts.push({ value: d.id, label: d.name || `Dataset #${d.id}` }));
    return opts;
  }, [datasets]);

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
                <p style={{ color: 'var(--color-text-muted)' }}>Select a well to view its quality report</p>
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
                    <InlineLoader message="Analyzing data quality..." />
                  </div>
                </CardContent>
              </Card>
            )}

            {!isLoading && qualityData && totalRecords > 0 && <QualityReport report={qualityData} />}

            {showGenerateButton && (
              <Card>
                <CardContent className="py-12">
                  <div className="text-center">
                    <p style={{ color: 'var(--color-text-muted)' }}>
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
