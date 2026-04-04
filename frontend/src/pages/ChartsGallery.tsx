import React, { useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { ScatterPlot } from '../components/charts/ScatterPlot';
import { Card, CardHeader, CardTitle, CardContent, Button, Select, PageHeader } from '../components/ui';
import { useWells, useDepthSampleData } from '../hooks';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames, getParameterLabel } from '../constants/parameterLabels';

export const ChartsGallery: React.FC = () => {
  const { data: wells } = useWells();
  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [xParameter, setXParameter] = useState<string>('bit_depth_feet');
  const [yParameter, setYParameter] = useState<string>('rate_of_penetration_ft_per_hr');
  const [xScale, setXScale] = useState<'linear' | 'log'>('linear');
  const [yScale, setYScale] = useState<'linear' | 'log'>('linear');
  const [maxPoints, setMaxPoints] = useState<number>(1000);
  const [showTrendLine, setShowTrendLine] = useState<boolean>(false);
  
  // Applied selections (for generating the plot)
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const [appliedXParameter, setAppliedXParameter] = useState<string>('bit_depth_feet');
  const [appliedYParameter, setAppliedYParameter] = useState<string>('rate_of_penetration_ft_per_hr');
  const [appliedXScale, setAppliedXScale] = useState<'linear' | 'log'>('linear');
  const [appliedYScale, setAppliedYScale] = useState<'linear' | 'log'>('linear');
  const [appliedMaxPoints, setAppliedMaxPoints] = useState<number>(1000);
  const [appliedShowTrendLine, setAppliedShowTrendLine] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  
  const { data: datasets, isLoading: datasetsLoading } = useOutlierDatasets(selectedWellId);
  const { data: rawDepthData, isLoading: isRawLoading } = useDepthSampleData(
    appliedDatasetId === 'raw' ? appliedWellId || 0 : 0,
    50000
  );
  const { data: processedDataset, isLoading: isProcessedLoading } = useOutlierDatasetData(
    appliedDatasetId === 'raw' ? null : appliedDatasetId,
    { includeOutliers: false, pageSize: 50000 }
  );
  const processedRows = (processedDataset?.records ?? []).map((record) => record.data ?? {});
  const depthData = appliedDatasetId === 'raw'
    ? rawDepthData
    : { data: processedRows };
  const isLoading = appliedDatasetId === 'raw' ? isRawLoading : isProcessedLoading;

  const handleApply = () => {
    setIsGenerating(true);
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
    setAppliedXParameter(xParameter);
    setAppliedYParameter(yParameter);
    setAppliedXScale(xScale);
    setAppliedYScale(yScale);
    setAppliedMaxPoints(maxPoints);
    setAppliedShowTrendLine(showTrendLine);
    // Reset generating state after a short delay to show the chart
    setTimeout(() => setIsGenerating(false), 500);
  };

  // Get all 28 tracked parameters from parameterLabels
  const trackedParams = getAllParameterNames();

  // Use only tracked parameters that exist in the data
  const availableParameters = depthData?.data && depthData.data.length > 0
    ? trackedParams.filter(param => param in depthData.data[0])
    : trackedParams;

  const scatterData = depthData?.data || [];

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader 
          title="Crossplots" 
          subtitle="Scatter plot analysis for parameter correlation" 
        />

        <Card>
          <CardHeader>
            <CardTitle>Select Well and Parameters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Well</label>
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
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Data Source</label>
                <select
                  value={selectedDatasetId === 'raw' ? 'raw' : String(selectedDatasetId)}
                  onChange={e => {
                    const value = e.target.value;
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
                  <p className="mt-1 text-xs text-gray-400">Loading clean cases...</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">X-Axis Parameter</label>
                  <select
                    value={xParameter}
                    onChange={e => setXParameter(e.target.value)}
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-700"
                  >
                    {availableParameters.map(param => (
                      <option key={param} value={param}>
                        {getParameterLabel(param)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Y-Axis Parameter</label>
                  <select
                    value={yParameter}
                    onChange={e => setYParameter(e.target.value)}
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-700"
                  >
                    {availableParameters.map(param => (
                      <option key={param} value={param}>
                        {getParameterLabel(param)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">X-Axis Scale</label>
                  <select
                    value={xScale}
                    onChange={e => setXScale(e.target.value as 'linear' | 'log')}
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-700"
                  >
                    <option value="linear">Linear</option>
                    <option value="log">Logarithmic</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Y-Axis Scale</label>
                  <select
                    value={yScale}
                    onChange={e => setYScale(e.target.value as 'linear' | 'log')}
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-700"
                  >
                    <option value="linear">Linear</option>
                    <option value="log">Logarithmic</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Max Points to Plot</label>
                <select
                  value={maxPoints}
                  onChange={e => setMaxPoints(Number(e.target.value))}
                  className="w-full bg-gray-800 text-white px-3 py-2 rounded border border-gray-700"
                >
                  <option value={1000}>1,000</option>
                  <option value={2000}>2,000</option>
                  <option value={5000}>5,000</option>
                  <option value={10000}>10,000</option>
                  <option value={20000}>20,000</option>
                </select>
              </div>

              <label className="flex items-center gap-3 text-sm text-gray-300 select-none">
                <input
                  type="checkbox"
                  checked={showTrendLine}
                  onChange={e => setShowTrendLine(e.target.checked)}
                  className="h-4 w-4 accent-blue-600"
                />
                Show trend line
              </label>

              <div className="flex justify-end pt-0">
                <Button
                  onClick={handleApply}
                  disabled={!selectedWellId}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Apply Selection
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {!appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-gray-400 text-lg">Select a well and parameters, then click Apply to generate the crossplot</p>
              </div>
            </CardContent>
          </Card>
        )}

        {isGenerating && appliedWellId && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                <p className="ml-4 text-gray-400">Generating crossplot...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {!isGenerating && appliedWellId && depthData && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Crossplot</CardTitle>
                <Button
                  onClick={() => {
                    const columns = [appliedXParameter, appliedYParameter];
                    const csv = [columns.join(',')];
                    scatterData.forEach(row => {
                      csv.push(columns.map(col => row[col] ?? '').join(','));
                    });
                    const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'crossplot_data.csv';
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 text-sm"
                >
                  Export
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <ScatterPlot
                data={scatterData}
                xKey={appliedXParameter}
                yKey={appliedYParameter}
                xLabel={getParameterLabel(appliedXParameter)}
                yLabel={getParameterLabel(appliedYParameter)}
                title={`${getParameterLabel(appliedYParameter)} vs ${getParameterLabel(appliedXParameter)}`}
                height={500}
                showTrendLine={appliedShowTrendLine}
                xScale={appliedXScale}
                yScale={appliedYScale}
                maxPoints={appliedMaxPoints}
                interactive={false}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};
