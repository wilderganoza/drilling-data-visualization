/**
 * Well Visualization Page - Interactive charts for drilling data analysis
 */
import React, { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/layout';
import { Card, CardHeader, CardTitle, CardContent, Button, InlineLoader, ErrorState } from '../components/ui';
import { ROPChart, DepthTimeChart, MultiParameterChart } from '../components/charts';
import { useWell, useDepthSampleData } from '../hooks';
import { useOutlierDataset, useOutlierDatasetData } from '../hooks/useOutlierDetection';
import { minMax, mean } from '../utils/stats';

type WellVisualizationProps = {
  wellId?: number;
  embedded?: boolean;
  datasetId?: 'raw' | number;
};

export const WellVisualization: React.FC<WellVisualizationProps> = ({ wellId, embedded, datasetId = 'raw' }) => {
  const params = useParams<{ wellId: string }>();
  const parsedRouteId = Number(params.wellId);
  const wellIdFromRoute = Number.isFinite(parsedRouteId) ? parsedRouteId : 0;
  const wellIdNum = wellId ?? wellIdFromRoute;

  const { data: wellData, isLoading: wellLoading, error: wellError } = useWell(wellIdNum);
  const { data: rawDepthChartData, isLoading: rawDepthDataLoading, error: rawDepthError } = useDepthSampleData(
    datasetId === 'raw' ? wellIdNum : 0,
    50000,
  );
  const { data: processedDatasetDetail } = useOutlierDataset(
    datasetId === 'raw' ? null : datasetId,
  );
  const { data: processedDatasetData, isLoading: processedDataLoading, error: processedDataError } = useOutlierDatasetData(
    datasetId === 'raw' ? null : datasetId,
    { includeOutliers: false, pageSize: 50000 },
  );

  const depthChartData = datasetId === 'raw'
    ? rawDepthChartData
    : {
        well_id: wellIdNum,
        total_records: processedDatasetData?.records?.length ?? 0,
        data: (processedDatasetData?.records ?? []).map((record) => record.data ?? {}),
      };

  const isLoading = wellLoading || (datasetId === 'raw' ? rawDepthDataLoading : processedDataLoading);
  const queryError = wellError ?? (datasetId === 'raw' ? rawDepthError : processedDataError);
  const dataPointsCount = datasetId === 'raw'
    ? (wellData?.total_rows ?? depthChartData?.data?.length ?? 0)
    : (processedDatasetData?.total_records
      ?? processedDatasetDetail?.metrics?.processed_records
      ?? depthChartData?.data?.length
      ?? 0);

  // Sort data by depth so line charts render left-to-right
  const sortedData = useMemo(() => {
    if (!depthChartData?.data) return [];
    return [...depthChartData.data].sort((a, b) => {
      const da = Number(a.hole_depth_feet ?? a.bit_depth_feet) || 0;
      const db = Number(b.hole_depth_feet ?? b.bit_depth_feet) || 0;
      return da - db;
    });
  }, [depthChartData]);

  // Transform data for ROP chart using Depth database
  const ropData = sortedData.map((point) => ({
    depth: point.hole_depth_feet ?? point.bit_depth_feet,
    time: point.yyyy_mm_dd,
    rop: point.rate_of_penetration_ft_per_hr,
  }));

  const depthTimeData = sortedData.map((point) => {
    // Combinar YYYY/MM/DD con HH:MM:SS para obtener el timestamp completo
    const dateStr = point.yyyy_mm_dd ?? point['YYYY/MM/DD'];
    const timeStr = point.hh_mm_ss ?? point['HH:MM:SS'];
    const timestamp = dateStr && timeStr ? `${dateStr} ${timeStr}` : dateStr;

    return {
      time: timestamp ?? point.yyyy_mm_dd,
      depth: point.bit_depth_feet ?? point['Bit Depth (feet)'],
    };
  });

  const startDate = depthChartData?.data
    ? depthChartData.data
        .map((point) => {
          const dateStr = point.yyyy_mm_dd ?? point['YYYY/MM/DD'];
          const timeStr = point.hh_mm_ss ?? point['HH:MM:SS'];
          if (!dateStr) return null;
          const candidate = timeStr ? new Date(`${dateStr} ${timeStr}`) : new Date(dateStr);
          return Number.isNaN(candidate.getTime()) ? null : candidate;
        })
        .filter((d): d is Date => d !== null)
        .reduce<Date | null>((min, d) => (min === null || d < min ? d : min), null)
    : null;

  const multiParamData = sortedData.map((point) => ({
    depth: point.hole_depth_feet ?? point.bit_depth_feet,
    wob: point['Weight on Bit (klbs)'] ?? point.weight_on_bit_klbs,
    rpm: point['Rotary RPM (RPM)'] ?? point.rotary_rpm_rpm ?? point.rotary_rpm,
    pressure: point['Standpipe Pressure (psi)'] ?? point.standpipe_pressure_psi,
    hookload: point['Hook Load (klbs)'] ?? point.hook_load_klbs,
  }));

  const availableParameters = [
    { key: 'wob', name: 'Weight on Bit', color: '#3B82F6', yAxisId: 'left' },
    { key: 'rpm', name: 'Rotary RPM', color: '#10B981', yAxisId: 'right' },
    { key: 'pressure', name: 'Standpipe Pressure', color: '#F59E0B', yAxisId: 'left' },
    { key: 'hookload', name: 'Hook Load', color: '#EF4444', yAxisId: 'right' },
  ];

  // Estadísticas con guardas: datos vacíos no deben producir NaN/-Infinity
  const hasData = !!depthChartData && depthChartData.data.length > 0;
  const avgRop = mean(ropData.map((p) => Number(p.rop)).filter((v) => Number.isFinite(v)));
  const maxDepth = minMax(depthTimeData.map((p) => Number(p.depth)))?.max ?? null;

  const content = (
    <div className="space-y-6">
        {!embedded && (
          <>
            {/* Header */}
            <div className="flex items-center justify-between w-full">
              <div>
                <h1 className="text-3xl font-bold text-gray-100">
                  {wellData?.well_name || `Well ${wellIdNum}`}
                </h1>
                <p className="text-gray-400 mt-1">Real-time drilling data visualization</p>
              </div>
            </div>
          </>
        )}

        {/* Data Statistics */}
        {!isLoading && hasData && (
          <Card>
            <CardHeader>
              <CardTitle>Data Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-gray-400">Data Points</p>
                  <p className="text-2xl font-bold text-blue-500">
                    {dataPointsCount.toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Avg ROP</p>
                  <p className="text-2xl font-bold text-green-500">
                    {avgRop !== null ? `${avgRop.toFixed(2)} ft/hr` : 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Max Depth</p>
                  <p className="text-2xl font-bold text-purple-500">
                    {maxDepth !== null ? `${maxDepth.toFixed(0)} ft` : 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Start Date</p>
                  <p className="text-2xl font-bold text-orange-500">
                    {startDate ? startDate.toLocaleDateString() : 'N/A'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Loading State */}
        {isLoading && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center py-4">
                <InlineLoader message="Loading drilling data..." />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error State */}
        {!isLoading && queryError != null && (
          <Card>
            <CardContent>
              <ErrorState error={queryError} />
            </CardContent>
          </Card>
        )}

        {/* Charts */}
        {!isLoading && hasData && (
          <>
            {/* ROP Chart */}
            <ROPChart
              data={ropData}
              xAxisKey="depth"
              yAxisKey="rop"
              title="Rate of Penetration vs Depth"
              height={500}
            />

            {/* Depth vs Time Chart */}
            <DepthTimeChart
              data={depthTimeData}
              title="Drilling Progress - Depth vs Time"
              height={500}
            />

            {/* Multi-Parameter Chart */}
            <MultiParameterChart
              data={multiParamData}
              parameters={availableParameters}
              xAxisKey="depth"
              title="Drilling Parameters vs Depth"
              height={500}
            />
          </>
        )}

        {/* No Data State */}
        {!isLoading && queryError == null && !hasData && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-gray-400 text-lg">No data available for this well</p>
                <Button className="mt-4" onClick={() => window.location.reload()}>
                  Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
  );

  if (embedded) {
    return content;
  }

  return <Layout>{content}</Layout>;
};
