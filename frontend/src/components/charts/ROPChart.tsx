/**
 * Rate of Penetration (ROP) Chart Component
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

export interface ROPChartProps {
  data: Array<{
    depth?: number;
    time?: string;
    rop?: number;
    [key: string]: any;
  }>;
  xAxisKey?: string;
  yAxisKey?: string;
  title?: string;
  height?: number;
}

export const ROPChart: React.FC<ROPChartProps> = ({
  data,
  xAxisKey = 'depth',
  yAxisKey = 'rop',
  title = 'Rate of Penetration',
  height = 520,
}) => {
  if (!data || data.length === 0) {
    return null;
  }

  const handleDownloadData = () => {
    downloadDataAsCSV(data, 'rop_data', [xAxisKey, yAxisKey]);
  };

  // Calculate 10 evenly spaced ticks for X axis
  const xValues = data.map(d => d[xAxisKey]).filter(v => v != null);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const step = (maxX - minX) / 9; // 9 intervals = 10 ticks
  const xTicks = Array.from({ length: 10 }, (_, i) => Math.round(minX + step * i));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-gray-800 border border-gray-700 p-3 rounded-lg shadow-lg">
          <p className="text-gray-300 text-sm">
            {xAxisKey === 'depth' ? 'Depth' : 'Time'}: {payload[0].payload[xAxisKey]}
          </p>
          <p className="text-blue-400 font-semibold">
            ROP: {payload[0].value?.toFixed(2)} ft/hr
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{title}</CardTitle>
          <Button
            onClick={handleDownloadData}
            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 text-sm"
          >
            Export
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pb-6">
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 20, right: 60, left: 50, bottom: 36 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey={xAxisKey}
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
              tickMargin={14}
              height={64}
              tickFormatter={(value) => Math.round(value).toString()}
              ticks={xTicks}
              domain={['dataMin', 'dataMax']}
            />
            <YAxis
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend 
              verticalAlign="top" 
              height={36}
              wrapperStyle={{ color: '#9CA3AF' }} 
            />
            <Line
              type="monotone"
              dataKey={yAxisKey}
              stroke="#3B82F6"
              strokeWidth={2}
              dot={false}
              name={getParameterLabel('rate_of_penetration_ft_per_hr')}
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
