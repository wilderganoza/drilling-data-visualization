import React, { useMemo, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { ScatterPlot } from '../components/charts/ScatterPlot';
import { Card, CardHeader, CardTitle, CardContent, Button, PageHeader, InlineLoader, SearchableSelect } from '../components/ui';
import { useWells, useDepthSampleData } from '../hooks';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames, getParameterLabel } from '../constants/parameterLabels';

const scaleOptions = [
  { value: 'linear', label: 'Linear' },
  { value: 'log', label: 'Logarithmic' },
];

const maxPointsOptions = [
  { value: 1000, label: '1,000' },
  { value: 2000, label: '2,000' },
  { value: 5000, label: '5,000' },
  { value: 10000, label: '10,000' },
  { value: 20000, label: '20,000' },
];

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
  const [includeZeros, setIncludeZeros] = useState<boolean>(true);

  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const [appliedXParameter, setAppliedXParameter] = useState<string>('bit_depth_feet');
  const [appliedYParameter, setAppliedYParameter] = useState<string>('rate_of_penetration_ft_per_hr');
  const [appliedXScale, setAppliedXScale] = useState<'linear' | 'log'>('linear');
  const [appliedYScale, setAppliedYScale] = useState<'linear' | 'log'>('linear');
  const [appliedMaxPoints, setAppliedMaxPoints] = useState<number>(1000);
  const [appliedShowTrendLine, setAppliedShowTrendLine] = useState<boolean>(false);
  const [appliedIncludeZeros, setAppliedIncludeZeros] = useState<boolean>(true);

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
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
    setAppliedXParameter(xParameter);
    setAppliedYParameter(yParameter);
    setAppliedXScale(xScale);
    setAppliedYScale(yScale);
    setAppliedMaxPoints(maxPoints);
    setAppliedShowTrendLine(showTrendLine);
    setAppliedIncludeZeros(includeZeros);
  };

  const trackedParams = getAllParameterNames();

  const availableParameters = depthData?.data && depthData.data.length > 0
    ? trackedParams.filter(param => param in depthData.data[0])
    : trackedParams;

  const scatterData = depthData?.data || [];

  const wellOptions = useMemo(
    () => (wells?.wells ?? []).map((w: any) => ({ value: w.id, label: w.well_name })),
    [wells],
  );

  const datasetOptions = useMemo(() => {
    const opts: Array<{ value: string | number; label: string }> = [{ value: 'raw', label: 'Raw data (original)' }];
    (datasets ?? []).forEach((d) => opts.push({ value: d.id, label: d.name || `Dataset #${d.id}` }));
    return opts;
  }, [datasets]);

  const parameterOptions = useMemo(
    () => availableParameters.map((p) => ({ value: p, label: getParameterLabel(p) })),
    [availableParameters],
  );

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

                <div className="relative">
                  <SearchableSelect
                    label="Data Source"
                    options={datasetOptions}
                    value={selectedDatasetId}
                    onChange={(v) => setSelectedDatasetId(v === 'raw' ? 'raw' : Number(v))}
                    placeholder={datasetsLoading ? 'Loading datasets...' : 'Select data source'}
                    disabled={datasetsLoading}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="relative">
                  <SearchableSelect
                    label="X-Axis Parameter"
                    options={parameterOptions}
                    value={xParameter}
                    onChange={(v) => setXParameter(String(v))}
                  />
                </div>
                <div className="relative">
                  <SearchableSelect
                    label="Y-Axis Parameter"
                    options={parameterOptions}
                    value={yParameter}
                    onChange={(v) => setYParameter(String(v))}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="relative">
                  <SearchableSelect
                    label="X-Axis Scale"
                    options={scaleOptions}
                    value={xScale}
                    onChange={(v) => setXScale(String(v) as 'linear' | 'log')}
                  />
                </div>
                <div className="relative">
                  <SearchableSelect
                    label="Y-Axis Scale"
                    options={scaleOptions}
                    value={yScale}
                    onChange={(v) => setYScale(String(v) as 'linear' | 'log')}
                  />
                </div>
                <div className="relative">
                  <SearchableSelect
                    label="Max Points to Plot"
                    options={maxPointsOptions}
                    value={maxPoints}
                    onChange={(v) => setMaxPoints(Number(v))}
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <label
                  className="flex items-center gap-2 text-sm cursor-pointer"
                  style={{ color: 'var(--color-text)' }}
                >
                  <input
                    type="checkbox"
                    checked={showTrendLine}
                    onChange={e => setShowTrendLine(e.target.checked)}
                    style={{ accentColor: 'var(--color-primary)' }}
                  />
                  Show trend line
                </label>

                <label
                  className="flex items-center gap-2 text-sm"
                  style={{
                    color: xScale === 'log' || yScale === 'log' ? 'var(--color-text-muted)' : 'var(--color-text)',
                    cursor: xScale === 'log' || yScale === 'log' ? 'not-allowed' : 'pointer',
                    opacity: xScale === 'log' || yScale === 'log' ? 0.5 : 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={xScale === 'log' || yScale === 'log' ? true : includeZeros}
                    onChange={e => setIncludeZeros(e.target.checked)}
                    disabled={xScale === 'log' || yScale === 'log'}
                    style={{ accentColor: 'var(--color-primary)' }}
                  />
                  Include zeros
                </label>
              </div>

              <div className="flex justify-end">
                <Button onClick={handleApply} disabled={!selectedWellId}>
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
                <p style={{ color: 'var(--color-text-muted)' }}>Select a well and parameters, then click Apply to generate the crossplot</p>
              </div>
            </CardContent>
          </Card>
        )}

        {appliedWellId && isLoading && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center py-4">
                <InlineLoader message="Loading crossplot data..." />
              </div>
            </CardContent>
          </Card>
        )}

        {appliedWellId && !isLoading && depthData && (
          <Card>
            <CardHeader>
              <CardTitle>Crossplot</CardTitle>
              <Button
                variant="secondary"
                size="sm"
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
              >
                Export
              </Button>
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
                includeZeros={appliedIncludeZeros}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};
