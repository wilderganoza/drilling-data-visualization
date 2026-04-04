import React, { useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { Card, CardHeader, CardTitle, CardContent, Button } from '../components/ui';
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

  const handleOpen = () => {
    if (!selectedWellId) return;
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-100">Wells</h1>
            <p className="text-gray-400 mt-1">Select a well to visualize drilling data</p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Select Well</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <select
                value={selectedWellId || ''}
                onChange={e => setSelectedWellId(Number(e.target.value))}
                className="w-full bg-gray-800 text-white px-4 py-3 rounded-lg border border-gray-700"
              >
                <option value="">-- Select a well --</option>
                {wells?.wells?.map((well: any) => (
                  <option key={well.id} value={well.id}>
                    {well.well_name}
                  </option>
                ))}
              </select>

              {selectedWellId && (
                <div className="space-y-2">
                  <label className="block text-sm text-gray-400">Data source</label>
                  <select
                    value={selectedDatasetId === 'raw' ? 'raw' : String(selectedDatasetId)}
                    onChange={(event) => {
                      const value = event.target.value;
                      setSelectedDatasetId(value === 'raw' ? 'raw' : Number(value));
                    }}
                    className="w-full bg-gray-800 text-white px-4 py-3 rounded-lg border border-gray-700"
                  >
                    <option value="raw">Raw data (original)</option>
                    {datasets?.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.name || `Dataset #${dataset.id}`}
                      </option>
                    ))}
                  </select>
                  {datasetsLoading && (
                    <p className="text-xs text-gray-400">Loading clean cases...</p>
                  )}
                </div>
              )}

              <div className="flex justify-end">
                <Button
                  onClick={handleOpen}
                  disabled={!selectedWellId}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
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
                <p className="text-gray-400 text-lg">Select a well to start</p>
              </div>
            </CardContent>
          </Card>
        )}

        {appliedWellId && <WellVisualization wellId={appliedWellId} embedded datasetId={appliedDatasetId} />}
      </div>
    </Layout>
  );
};
