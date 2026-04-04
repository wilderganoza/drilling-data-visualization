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

interface WellData {
  wellId: number;
  wellName: string;
  data: Array<{ [key: string]: any }>;
  color: string;
}

interface MultiWellComparisonProps {
  wells: WellData[];
  xKey: string;
  yKey: string;
  xLabel?: string;
  yLabel?: string;
  title?: string;
  height?: number;
  invertYAxis?: boolean;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    // Get depth value from the first payload entry that has it
    const depthValue = payload[0]?.payload?.xValue;
    
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg">
        <p className="text-gray-300 text-sm mb-2">
          <span className="font-semibold">Depth:</span> {typeof depthValue === 'number' ? depthValue.toFixed(2) : 'N/A'} ft
        </p>
        {payload.map((entry: any, index: number) => (
          <div key={index} className="text-sm">
            <p style={{ color: entry.color }} className="font-semibold">
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
            </p>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export const MultiWellComparison: React.FC<MultiWellComparisonProps> = ({
  wells,
  xKey,
  yKey,
  xLabel,
  yLabel,
  title,
  height = 500,
  invertYAxis = false,
}) => {
  // Get all unique X values from all wells
  const allXValuesSet = new Set<number>();
  wells.forEach(well => {
    well.data.forEach(dataPoint => {
      const xValue = dataPoint[xKey];
      if (xValue != null && !isNaN(xValue)) {
        allXValuesSet.add(xValue);
      }
    });
  });
  
  if (allXValuesSet.size === 0) {
    return <div>No data available</div>;
  }
  
  const allXValues = Array.from(allXValuesSet).sort((a, b) => a - b);
  
  // Create combined data aligned by X values
  const combinedData: Array<{ [key: string]: any }> = allXValues.map(xValue => {
    const point: { [key: string]: any } = { xValue };
    
    wells.forEach(well => {
      const dataPoint = well.data.find(d => d[xKey] === xValue);
      if (dataPoint) {
        point[`${well.wellName}_${xKey}`] = dataPoint[xKey];
        point[`${well.wellName}_${yKey}`] = dataPoint[yKey];
      }
    });
    
    return point;
  });

  const minX = Math.min(...allXValues);
  const maxX = Math.max(...allXValues);
  const step = (maxX - minX) / 9; // 9 intervals = 10 ticks
  const xTicks = Array.from({ length: 10 }, (_, i) => Math.round(minX + step * i));

  // Ensure all tick values exist in combinedData
  xTicks.forEach(tickValue => {
    if (!combinedData.find(d => d.xValue === tickValue)) {
      combinedData.push({ xValue: tickValue });
    }
  });
  
  // Sort combinedData by xValue
  combinedData.sort((a, b) => (a.xValue || 0) - (b.xValue || 0));

  return (
    <div className="pb-6">
      {title && (
        <h3 className="text-lg font-semibold text-gray-100 mb-4">{title}</h3>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={combinedData} margin={{ top: 20, right: 60, left: 50, bottom: 36 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="xValue"
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
            reversed={invertYAxis}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            verticalAlign="top"
            height={36}
            wrapperStyle={{ color: '#9CA3AF' }}
          />
          {wells.map(well => (
            <Line
              key={well.wellId}
              type="monotone"
              dataKey={`${well.wellName}_${yKey}`}
              name={well.wellName}
              stroke={well.color}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ))}
          <Brush
            dataKey="xValue"
            height={28}
            stroke="#3B82F6"
            fill="#1F2937"
            travellerWidth={10}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="text-center mt-0">
        <p className="text-sm text-gray-400">{xLabel || xKey}</p>
      </div>
    </div>
  );
};
