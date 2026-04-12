/**
 * Multi-Parameter Chart Component for drilling parameters
 */
import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush,
} from 'recharts';
import { Card, CardHeader, CardTitle, CardContent, Button } from '../ui';
import { getParameterLabel } from '../../constants/parameterLabels';
import { downloadDataAsCSV } from '../../utils/downloadUtils';

export interface MultiParameterChartProps {
  data: Array<{
    [key: string]: any;
  }>;
  parameters: Array<{
    key: string;
    name: string;
    color: string;
    yAxisId?: string;
  }>;
  xAxisKey?: string;
  title?: string;
  height?: number;
}

export const MultiParameterChart: React.FC<MultiParameterChartProps> = ({
  data,
  parameters,
  xAxisKey = 'depth',
  title = 'Drilling Parameters',
  height = 520,
}) => {
  if (!data || data.length === 0) {
    return null;
  }

  const handleDownloadData = () => {
    const columns = [xAxisKey, ...parameters.map(p => p.key)];
    downloadDataAsCSV(data, 'multi_parameter_data', columns);
  };

  // Calculate 10 evenly spaced ticks for X axis
  const xValues = data.map(d => Number(d[xAxisKey])).filter(v => Number.isFinite(v));
  const minX = xValues.length ? Math.min(...xValues) : 0;
  const maxX = xValues.length ? Math.max(...xValues) : 0;
  const step = maxX > minX ? (maxX - minX) / 9 : 1; // 9 intervals = 10 ticks
  const xTicks = Array.from({ length: 10 }, (_, i) => Math.round(minX + step * i));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-gray-800 border border-gray-700 p-3 rounded-lg shadow-lg">
          <p className="text-gray-300 text-sm mb-2">
            {xAxisKey === 'depth' ? 'Depth' : 'Time'}: {payload[0].payload[xAxisKey]}
          </p>
          {payload.map((entry: any, index: number) => (
            <p key={index} style={{ color: entry.color }} className="font-semibold text-sm">
              {entry.name}: {entry.value?.toFixed(2)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleDownloadData}
        >
          Export
        </Button>
      </CardHeader>
      <CardContent className="pb-6">
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 20, right: 60, left: 50, bottom: 36 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey={xAxisKey}
              type="number"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
              tickMargin={14}
              height={64}
              tickFormatter={(value) => {
                if (xAxisKey === 'time') {
                  const date = new Date(value);
                  const day = String(date.getDate()).padStart(2, '0');
                  const month = String(date.getMonth() + 1).padStart(2, '0');
                  const year = String(date.getFullYear()).slice(-2);
                  return `${day}/${month}/${year}`;
                }
                return Math.round(value).toString();
              }}
              ticks={xTicks}
              domain={['dataMin', 'dataMax']}
            />
            <YAxis
              yAxisId="wob"
              orientation="left"
              stroke="#3B82F6"
              tick={{ fill: '#3B82F6', fontSize: 12 }}
              width={45}
              domain={['auto', 'auto']}
            />
            <YAxis
              yAxisId="hookload"
              orientation="left"
              stroke="#EF4444"
              tick={{ fill: '#EF4444', fontSize: 12 }}
              width={45}
              domain={['auto', 'auto']}
            />
            <YAxis
              yAxisId="rpm"
              orientation="right"
              stroke="#10B981"
              tick={{ fill: '#10B981', fontSize: 12 }}
              width={40}
              domain={['auto', 'auto']}
            />
            <YAxis
              yAxisId="pressure"
              orientation="right"
              stroke="#F59E0B"
              tick={{ fill: '#F59E0B', fontSize: 12 }}
              width={50}
              domain={['auto', 'auto']}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend 
              verticalAlign="top" 
              height={36}
              wrapperStyle={{ color: '#9CA3AF' }} 
            />
            <Line
              type="monotone"
              dataKey="wob"
              stroke="#3B82F6"
              strokeWidth={2}
              dot={false}
              name={getParameterLabel('weight_on_bit_klbs')}
              yAxisId="wob"
            />
            <Line
              type="monotone"
              dataKey="rpm"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              name={getParameterLabel('rotary_rpm_rpm')}
              yAxisId="rpm"
            />
            <Line
              type="monotone"
              dataKey="pressure"
              stroke="#F59E0B"
              strokeWidth={2}
              dot={false}
              name={getParameterLabel('standpipe_pressure_psi')}
              yAxisId="pressure"
            />
            <Line
              type="monotone"
              dataKey="hookload"
              stroke="#EF4444"
              strokeWidth={2}
              dot={false}
              name={getParameterLabel('hook_load_klbs')}
              yAxisId="hookload"
            />
            <Brush
              dataKey={xAxisKey}
              height={28}
              stroke="#3B82F6"
              fill="#1F2937"
              travellerWidth={10}
            />
          </LineChart>
        </ResponsiveContainer>
        <div className="text-center mt-0">
          <p className="text-sm text-gray-400">{xAxisKey === 'depth' ? 'Depth (ft)' : 'Time'}</p>
        </div>
      </CardContent>
    </Card>
  );
};
