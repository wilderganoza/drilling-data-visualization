import React, { useMemo, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { Card, CardHeader, CardTitle, CardContent, Button, PageHeader, SearchableSelect } from '../components/ui';
import { useWells } from '../hooks';
import { useOutlierDatasets } from '../hooks/useOutlierDetection';
import { WellVisualization } from './WellVisualization';

export const WellVisualizationGeneral: React.FC = () => {
  const { data: wells } = useWells();
  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const { data: datasets, isLoading: datasetsLoading } = useOutlierDatasets(selectedWellId);

  const wellOptions = useMemo(
    () => (wells?.wells ?? []).map((w: any) => ({ value: w.id, label: w.well_name })),
    [wells],
  );

  const datasetOptions = useMemo(() => {
    const opts: Array<{ value: string | number; label: string }> = [{ value: 'raw', label: 'Raw data (original)' }];
    (datasets ?? []).forEach((d) => opts.push({ value: d.id, label: d.name || `Dataset #${d.id}` }));
    return opts;
  }, [datasets]);

  const handleOpen = () => {
    if (!selectedWellId) return;
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Wells"
          subtitle="Select a well to visualize drilling data"
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
                      label="Data source"
                      options={datasetOptions}
                      value={selectedDatasetId}
                      onChange={(v) => setSelectedDatasetId(v === 'raw' ? 'raw' : Number(v))}
                      placeholder={datasetsLoading ? 'Loading datasets...' : 'Select data source'}
                      disabled={datasetsLoading}
                    />
                  </div>
                )}
              </div>

              <div className="flex justify-end">
                <Button onClick={handleOpen} disabled={!selectedWellId}>
                  Open Well
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {!appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p style={{ color: 'var(--color-text-muted)' }}>Select a well to start</p>
              </div>
            </CardContent>
          </Card>
        )}

        {appliedWellId && <WellVisualization wellId={appliedWellId} embedded datasetId={appliedDatasetId} />}
      </div>
    </Layout>
  );
};
