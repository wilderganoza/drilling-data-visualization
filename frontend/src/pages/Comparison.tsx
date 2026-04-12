import React, { useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { MultiWellComparison } from '../components/charts/MultiWellComparison';
import { MultiHistogram } from '../components/charts/MultiHistogram';
import { Card, CardHeader, CardTitle, CardContent, Button, PageHeader, InlineLoader, SearchableSelect } from '../components/ui';
import { useWells, useDepthSampleData } from '../hooks';
import { useOutlierDatasets, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { getAllParameterNames, getParameterLabel } from '../constants/parameterLabels';

const WELL_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'];

export const Comparison: React.FC = () => {
  const { data: wells } = useWells(0, 1000); // Load all wells (API max)
  const [selectedWellIds, setSelectedWellIds] = useState<Array<number | null>>([null, null, null, null, null]);
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<Array<'raw' | number>>(['raw', 'raw', 'raw', 'raw', 'raw']);
  const [appliedWellIds, setAppliedWellIds] = useState<Array<number | null>>([null, null, null, null, null]);
  const [appliedDatasetIds, setAppliedDatasetIds] = useState<Array<'raw' | number>>(['raw', 'raw', 'raw', 'raw', 'raw']);
  const [comparisonParameter, setComparisonParameter] = useState<string>('rate_of_penetration_ft_per_hr');

  const handleApply = () => {
    setAppliedWellIds([...selectedWellIds]);
    setAppliedDatasetIds([...selectedDatasetIds]);
  };

  // Get all 28 tracked parameters from parameterLabels
  const availableParameters = getAllParameterNames();

  // Dataset selectors (one per selected well slot)
  const selDs1 = useOutlierDatasets(selectedWellIds[0]);
  const selDs2 = useOutlierDatasets(selectedWellIds[1]);
  const selDs3 = useOutlierDatasets(selectedWellIds[2]);
  const selDs4 = useOutlierDatasets(selectedWellIds[3]);
  const selDs5 = useOutlierDatasets(selectedWellIds[4]);
  const selectedDatasetQueries = [selDs1, selDs2, selDs3, selDs4, selDs5];

  // Data queries (one per applied well slot)
  const well1Data = useDepthSampleData(appliedWellIds[0] || 0, 50000);
  const well2Data = useDepthSampleData(appliedWellIds[1] || 0, 50000);
  const well3Data = useDepthSampleData(appliedWellIds[2] || 0, 50000);
  const well4Data = useDepthSampleData(appliedWellIds[3] || 0, 50000);
  const well5Data = useDepthSampleData(appliedWellIds[4] || 0, 50000);

  const clean1 = useOutlierDatasetData(
    typeof appliedDatasetIds[0] === 'number' ? appliedDatasetIds[0] : null,
    { includeOutliers: false, pageSize: 5000 },
  );
  const clean2 = useOutlierDatasetData(
    typeof appliedDatasetIds[1] === 'number' ? appliedDatasetIds[1] : null,
    { includeOutliers: false, pageSize: 5000 },
  );
  const clean3 = useOutlierDatasetData(
    typeof appliedDatasetIds[2] === 'number' ? appliedDatasetIds[2] : null,
    { includeOutliers: false, pageSize: 5000 },
  );
  const clean4 = useOutlierDatasetData(
    typeof appliedDatasetIds[3] === 'number' ? appliedDatasetIds[3] : null,
    { includeOutliers: false, pageSize: 5000 },
  );
  const clean5 = useOutlierDatasetData(
    typeof appliedDatasetIds[4] === 'number' ? appliedDatasetIds[4] : null,
    { includeOutliers: false, pageSize: 5000 },
  );

  const allWellQueries = [well1Data, well2Data, well3Data, well4Data, well5Data];
  const allCleanQueries = [clean1, clean2, clean3, clean4, clean5];

  const wellsData = appliedWellIds
    .map((wellId, index) => {
      if (!wellId) return null;
      const datasetChoice = appliedDatasetIds[index] ?? 'raw';
      const rawRecords = allWellQueries[index].data?.data ?? [];
      const cleanRecords = (allCleanQueries[index].data?.records ?? []).map((record) => record.data ?? {});
      const records = datasetChoice === 'raw' ? rawRecords : cleanRecords;
      if (!records || records.length === 0) return null;

      return {
        wellId,
        wellName: wells?.wells?.find(w => w.id === wellId)?.well_name || `Well ${wellId}`,
        data: records,
        color: WELL_COLORS[index % WELL_COLORS.length],
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  const isLoading = appliedWellIds.some((wellId, index) => {
    if (!wellId) return false;
    const datasetChoice = appliedDatasetIds[index] ?? 'raw';
    return datasetChoice === 'raw' ? allWellQueries[index]?.isLoading : allCleanQueries[index]?.isLoading;
  });

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader 
          title="Well Comparison" 
          subtitle="Compare drilling performance across multiple wells" 
        />

        <Card>
          <CardHeader>
            <CardTitle>Select Wells to Compare (Max 5)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[0, 1, 2, 3, 4].map((index) => (
                <div key={index} className="space-y-2 relative">
                  <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-text-muted)' }}>
                    Well {index + 1}
                    {selectedWellIds[index] && (
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: WELL_COLORS[index % WELL_COLORS.length] }}
                      />
                    )}
                  </div>
                  <SearchableSelect
                    options={(wells?.wells ?? []).map((w) => ({ value: w.id, label: w.well_name }))}
                    value={selectedWellIds[index]}
                    onChange={(v) => {
                      const newWellId = Number(v);
                      const newSelectedWellIds = [...selectedWellIds];
                      const newSelectedDatasetIds = [...selectedDatasetIds];

                      const existingIndex = newSelectedWellIds.findIndex((id, idx) => id === newWellId && idx !== index);
                      if (existingIndex !== -1) {
                        newSelectedWellIds[existingIndex] = null;
                        newSelectedDatasetIds[existingIndex] = 'raw';
                      }

                      newSelectedWellIds[index] = newWellId;
                      newSelectedDatasetIds[index] = 'raw';
                      setSelectedWellIds(newSelectedWellIds);
                      setSelectedDatasetIds(newSelectedDatasetIds);
                    }}
                    placeholder="Select a well..."
                  />

                  {selectedWellIds[index] && (
                    <SearchableSelect
                      options={[
                        { value: 'raw', label: 'Raw data (original)' },
                        ...(selectedDatasetQueries[index].data ?? []).map((d) => ({
                          value: d.id,
                          label: d.name || `Dataset #${d.id}`,
                        })),
                      ]}
                      value={selectedDatasetIds[index]}
                      onChange={(v) => {
                        const next = [...selectedDatasetIds];
                        next[index] = v === 'raw' ? 'raw' : Number(v);
                        setSelectedDatasetIds(next);
                      }}
                    />
                  )}
                </div>
              ))}

              <div className="relative">
                <SearchableSelect
                  label="Comparison Parameter"
                  options={availableParameters.map((p) => ({ value: p, label: getParameterLabel(p) }))}
                  value={comparisonParameter}
                  onChange={(v) => setComparisonParameter(String(v))}
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end">
              <Button
                onClick={handleApply}
                disabled={!selectedWellIds.some((id) => id !== null)}
              >
                Apply Selection
              </Button>
            </div>
          </CardContent>
        </Card>

        {!appliedWellIds.some((id) => id !== null) && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p style={{ color: 'var(--color-text-muted)' }}>Select wells to start comparison</p>
              </div>
            </CardContent>
          </Card>
        )}

        {isLoading && appliedWellIds.some((id) => id !== null) && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center py-4">
                <InlineLoader message="Loading well data..." />
              </div>
            </CardContent>
          </Card>
        )}

        {!isLoading && wellsData.length > 0 && (
          <>
            {/* Multi-Well Comparison Chart */}
            <Card>
              <CardHeader>
                <CardTitle>
                  {getParameterLabel(comparisonParameter)} vs Depth
                </CardTitle>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    const exportData: Array<{ [key: string]: any }> = [];
                    wellsData.forEach(well => {
                      well.data.forEach(dataPoint => {
                        exportData.push({
                          well_name: well.wellName,
                          bit_depth_feet: dataPoint.bit_depth_feet,
                          [comparisonParameter]: dataPoint[comparisonParameter],
                        });
                      });
                    });
                    const columns = ['well_name', 'bit_depth_feet', comparisonParameter];
                    const csv = [columns.join(',')];
                    exportData.forEach(row => {
                      csv.push(columns.map(col => row[col] ?? '').join(','));
                    });
                    const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'multi_well_comparison.csv';
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Export
                </Button>
              </CardHeader>
              <CardContent>
                <MultiWellComparison
                  wells={wellsData}
                  xKey="bit_depth_feet"
                  yKey={comparisonParameter}
                  xLabel="Depth (ft)"
                  yLabel={getParameterLabel(comparisonParameter)}
                  title=""
                  height={500}
                  invertYAxis={false}
                />
              </CardContent>
            </Card>

            {/* Multi-Histogram Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>
                  {getParameterLabel(comparisonParameter)} Distribution by Well
                </CardTitle>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    const histogramWells = wellsData.map(well => ({
                      wellName: well.wellName,
                      data: well.data.map(d => d[comparisonParameter]).filter(v => v != null && !isNaN(v)),
                    }));
                    const allValues = histogramWells.flatMap(w => w.data);
                    const min = Math.min(...allValues);
                    const max = Math.max(...allValues);
                    const bins = 20;
                    const binWidth = (max - min) / bins;
                    const exportData: any[] = [];
                    for (let i = 0; i < bins; i++) {
                      const binStart = min + i * binWidth;
                      const binEnd = binStart + binWidth;
                      const binCenter = (binStart + binEnd) / 2;
                      const row: any = { bin_center: binCenter, bin_start: binStart, bin_end: binEnd };
                      histogramWells.forEach(well => {
                        const count = well.data.filter(d => d >= binStart && (i === bins - 1 ? d <= binEnd : d < binEnd)).length;
                        row[`${well.wellName}_count`] = count;
                      });
                      exportData.push(row);
                    }
                    const columns = ['bin_center', 'bin_start', 'bin_end', ...histogramWells.map(w => `${w.wellName}_count`)];
                    const csv = [columns.join(',')];
                    exportData.forEach(row => {
                      csv.push(columns.map(col => row[col] ?? '').join(','));
                    });
                    const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'multi_histogram_distribution.csv';
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Export
                </Button>
              </CardHeader>
              <CardContent>
                <MultiHistogram
                  wells={wellsData.map(well => ({
                    wellName: well.wellName,
                    data: well.data.map(d => d[comparisonParameter]).filter(v => v != null && !isNaN(v)),
                    color: well.color,
                  }))}
                  xLabel={getParameterLabel(comparisonParameter)}
                  yLabel="Frequency"
                  title=""
                  height={500}
                  bins={20}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Comparison Statistics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                        <th className="text-left py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Well</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Data Points</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Min</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>P25</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>P50</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>P75</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Max</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Mean</th>
                        <th className="text-right py-2 px-3" style={{ color: 'var(--color-text-muted)' }}>Std Dev</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wellsData.map(well => {
                        const values = well.data
                          .map(d => d[comparisonParameter])
                          .filter(v => v != null && !isNaN(v))
                          .sort((a, b) => a - b);
                        
                        const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
                        const stdDev = Math.sqrt(
                          values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length
                        );
                        
                        const getPercentile = (arr: number[], p: number) => {
                          const index = (p / 100) * (arr.length - 1);
                          const lower = Math.floor(index);
                          const upper = Math.ceil(index);
                          const weight = index % 1;
                          
                          if (lower === upper) return arr[lower];
                          return arr[lower] * (1 - weight) + arr[upper] * weight;
                        };
                        
                        const p25 = getPercentile(values, 25);
                        const p50 = getPercentile(values, 50);
                        const p75 = getPercentile(values, 75);

                        return (
                          <tr key={well.wellId} style={{ borderBottom: '1px solid var(--color-border)' }}>
                            <td className="py-2 px-3" style={{ color: well.color }}>
                              {well.wellName}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {values.length.toLocaleString()}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {Math.min(...values).toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {p25.toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {p50.toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {p75.toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {Math.max(...values).toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {mean.toFixed(2)}
                            </td>
                            <td className="text-right py-2 px-3 text-muted-cell">
                              {stdDev.toFixed(2)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
};
