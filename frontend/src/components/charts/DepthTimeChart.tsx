/**
 * Depth vs Time Chart Component
 */
import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Brush,
} from 'recharts';
import { Card, CardHeader, CardTitle, CardContent, Button } from '../ui';
import { downloadDataAsCSV } from '../../utils/downloadUtils';

export interface DepthTimeChartProps {
  data: Array<{
    time?: string;
    depth?: number;
    [key: string]: any;
  }>;
  title?: string;
  height?: number;
}

export const DepthTimeChart: React.FC<DepthTimeChartProps> = ({
  data,
  title = 'Depth vs Time',
  height = 520,
}) => {
  if (!data || data.length === 0) {
    return null;
  }

  const handleDownloadData = () => {
    downloadDataAsCSV(data, 'depth_time_data', ['time', 'depth']);
  };

  // Calculate 10 evenly spaced ticks for X axis (time) using actual data points
  const validData = data.filter(d => d.time != null);
  const step = Math.floor(validData.length / 9); // 9 intervals = 10 ticks
  const timeTicks = Array.from({ length: 10 }, (_, i) => {
    const index = Math.min(i * step, validData.length - 1);
    return validData[index]?.time;
  }).filter((t): t is string => t != null);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-gray-800 border border-gray-700 p-3 rounded-lg shadow-lg">
          <p className="text-gray-300 text-sm">Time: {payload[0].payload.time}</p>
          <p className="text-green-400 font-semibold">
            Depth: {payload[0].value?.toFixed(2)} ft
          </p>
        </div>
      );
    }
    return null;
  };

  const brushHeight = 28;
  const brushY = Math.max(height - 62, 0);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between w-full">
          <CardTitle>{title}</CardTitle>
          <Button
            onClick={handleDownloadData}
            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 text-sm"
          >
            Export
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-4 pb-4">
        <div className="text-center -mb-10">
          <p className="text-sm text-gray-400">Time</p>
        </div>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 50, right: 60, left: 50, bottom: 62 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="time"
              orientation="top"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
              tickFormatter={(value) => {
                const date = new Date(value);
                const day = String(date.getDate()).padStart(2, '0');
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const year = String(date.getFullYear()).slice(-2);
                return `${day}/${month}/${year}`;
              }}
              ticks={timeTicks}
              domain={['dataMin', 'dataMax']}
            />
            <YAxis
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
              tickFormatter={(value) => Math.round(value).toString()}
              reversed={true}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="depth"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              name="Bit Depth (ft)"
            />
            <Brush
              dataKey="time"
              y={brushY}
              height={brushHeight}
              stroke="#10B981"
              fill="#1F2937"
              travellerWidth={10}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
};
