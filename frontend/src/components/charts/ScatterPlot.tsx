// Importar React
import React from 'react';
// Importar componentes de Recharts para gráficos de dispersión
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  TooltipProps,
} from 'recharts';

// Interfaz de props para el componente ScatterPlot
interface ScatterPlotProps {
  data: Array<{ [key: string]: any }>; // Array de datos
  xKey: string; // Clave para eje X
  yKey: string; // Clave para eje Y
  xLabel?: string; // Etiqueta del eje X
  yLabel?: string; // Etiqueta del eje Y
  title?: string; // Título del gráfico
  color?: string; // Color de los puntos
  height?: number; // Altura del gráfico
  showTrendLine?: boolean; // Mostrar línea de tendencia
  xScale?: 'linear' | 'log'; // Escala del eje X
  yScale?: 'linear' | 'log'; // Escala del eje Y
  maxPoints?: number; // Máximo de puntos a mostrar
  interactive?: boolean; // Habilitar interactividad
}

// Interfaz de props para tooltip personalizado
interface CustomTooltipProps {
  active?: boolean; // Si el tooltip está activo
  payload?: any[]; // Datos del tooltip
  xKey: string; // Clave del eje X
  yKey: string; // Clave del eje Y
  xLabel?: string; // Etiqueta del eje X
  yLabel?: string; // Etiqueta del eje Y
}

// Componente personalizado para tooltip del scatter plot
const CustomTooltip = ({ active, payload, xKey, yKey, xLabel, yLabel }: CustomTooltipProps) => {
  // Si el tooltip está activo y tiene datos
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      // Contenedor del tooltip con estilos
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg">
        {/* Mostrar valor del eje X */}
        <p className="text-sm text-gray-300">
          <span className="font-semibold">{xLabel || xKey}:</span>{' '}
          {typeof data[xKey] === 'number' ? data[xKey].toFixed(2) : String(data[xKey])}
        </p>
        {/* Mostrar valor del eje Y */}
        <p className="text-sm text-gray-300">
          <span className="font-semibold">{yLabel || yKey}:</span>{' '}
          {typeof data[yKey] === 'number' ? data[yKey].toFixed(2) : String(data[yKey])}
        </p>
      </div>
    );
  }
  // Si no está activo, no mostrar nada
  return null;
};

// Componente ScatterPlot para visualizar relaciones entre dos variables
export const ScatterPlot: React.FC<ScatterPlotProps> = ({
  data,
  xKey,
  yKey,
  xLabel,
  yLabel,
  title,
  color = '#3B82F6', // Color azul por defecto
  height = 400, // Altura por defecto: 400px
  showTrendLine = false, // No mostrar línea de tendencia por defecto
  xScale = 'linear', // Escala lineal por defecto para X
  yScale = 'linear', // Escala lineal por defecto para Y
  maxPoints = 10000, // Máximo 10000 puntos por defecto
  interactive = true, // Interactivo por defecto
}) => {
  // Filtrar datos válidos para el gráfico
  const plotData = data.filter((d) => {
    const x = d?.[xKey];
    const y = d?.[yKey];

    // Validar que sean números
    if (typeof x !== 'number' || typeof y !== 'number') return false;
    // Validar que no sean NaN
    if (Number.isNaN(x) || Number.isNaN(y)) return false;

    // Si la escala es logarítmica, validar valores positivos
    if (xScale === 'log' && x <= 0) return false;
    if (yScale === 'log' && y <= 0) return false;

    return true;
  });

  // Muestrear datos si exceden el máximo de puntos
  const sampledPlotData = (() => {
    // Si hay menos puntos que el máximo, retornar todos
    if (plotData.length <= maxPoints) return plotData;
    // Calcular paso de muestreo
    const step = Math.ceil(plotData.length / maxPoints);
    const sampled: typeof plotData = [];
    // Tomar cada n-ésimo punto
    for (let i = 0; i < plotData.length; i += step) {
      sampled.push(plotData[i]);
    }
    return sampled;
  })();

  // Extraer valores de X e Y de los datos muestreados
  const xValues = sampledPlotData.map((d) => d[xKey] as number);
  const yValues = sampledPlotData.map((d) => d[yKey] as number);

  // Calcular dominio para escala logarítmica en X
  const xDomainLog: [number, number] | undefined =
    xScale === 'log' && xValues.length > 0
      ? [Math.min(...xValues), Math.max(...xValues)]
      : undefined;

  // Calcular dominio para escala logarítmica en Y
  const yDomainLog: [number, number] | undefined =
    yScale === 'log' && yValues.length > 0
      ? [Math.min(...yValues), Math.max(...yValues)]
      : undefined;

  // Función para calcular línea de tendencia (regresión lineal)
  const calculateTrendLine = () => {
    // Si no se debe mostrar o hay muy pocos datos, retornar null
    if (!showTrendLine || sampledPlotData.length < 2) return null;

    const validData = sampledPlotData;
    const n = validData.length;
    
    // Calcular sumas necesarias para regresión lineal
    const sumX = validData.reduce((sum, d) => sum + d[xKey], 0);
    const sumY = validData.reduce((sum, d) => sum + d[yKey], 0);
    const sumXY = validData.reduce((sum, d) => sum + d[xKey] * d[yKey], 0);
    const sumX2 = validData.reduce((sum, d) => sum + d[xKey] * d[xKey], 0);

    // Calcular pendiente e intercepto de la línea de tendencia
    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;

    // Obtener valores mínimo y máximo de X
    const minX = Math.min(...validData.map(d => d[xKey]));
    const maxX = Math.max(...validData.map(d => d[xKey]));

    // Retornar dos puntos que definen la línea de tendencia
    return [
      { [xKey]: minX, [yKey]: slope * minX + intercept },
      { [xKey]: maxX, [yKey]: slope * maxX + intercept },
    ];
  };

  // Calcular datos de la línea de tendencia
  const trendLineData = calculateTrendLine();

  return (
    // Contenedor principal (deshabilitar interacción si no es interactivo)
    <div style={!interactive ? { pointerEvents: 'none' } : undefined}>
      {/* Mostrar título si existe */}
      {title && (
        <h3 className="text-lg font-semibold text-gray-100 mb-4">{title}</h3>
      )}

      {/* Mostrar mensaje de advertencia si no hay datos válidos para escala log */}
      {plotData.length === 0 && (xScale === 'log' || yScale === 'log') && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-4">
          <p className="text-sm text-gray-300">
            No hay puntos válidos para mostrar en escala logarítmica.
          </p>
          <p className="text-xs text-gray-500 mt-1">
            La escala log requiere valores &gt; 0. Prueba cambiando a escala linear o eligiendo
            parámetros con valores positivos.
          </p>
        </div>
      )}

      {/* Contenedor responsivo para el gráfico */}
      <ResponsiveContainer width="100%" height={height}>
        {/* Gráfico de dispersión con márgenes */}
        <ScatterChart margin={{ top: 20, right: 60, left: 50, bottom: 60 }}>
          {/* Cuadrícula cartesiana */}
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          {/* Eje X con escala configurable */}
          <XAxis
            type="number"
            dataKey={xKey}
            name={xLabel || xKey}
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF' }}
            scale={xScale === 'log' ? 'log' : 'auto'}
            domain={xScale === 'log' ? xDomainLog || ['auto', 'auto'] : undefined}
            label={{
              value: xLabel || xKey,
              position: 'insideBottom',
              offset: -25,
              fill: '#9CA3AF',
            }}
          />
          {/* Eje Y con escala configurable */}
          <YAxis
            type="number"
            dataKey={yKey}
            name={yLabel || yKey}
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF' }}
            scale={yScale === 'log' ? 'log' : 'auto'}
            domain={yScale === 'log' ? yDomainLog || ['auto', 'auto'] : undefined}
            label={{
              value: yLabel || yKey,
              angle: -90,
              position: 'insideLeft',
              offset: -10,
              fill: '#9CA3AF',
            }}
          />
          {/* Mostrar tooltip y leyenda solo si es interactivo */}
          {interactive && (
            <>
              <Tooltip content={<CustomTooltip xKey={xKey} yKey={yKey} xLabel={xLabel} yLabel={yLabel} />} />
              <Legend
                verticalAlign="top"
                height={36}
                wrapperStyle={{ color: '#9CA3AF' }}
              />
            </>
          )}
          {/* Puntos de dispersión */}
          <Scatter
            name={`${yLabel || yKey} vs ${xLabel || xKey}`}
            data={sampledPlotData}
            fill={color}
            fillOpacity={0.6}
            isAnimationActive={false}
          />
          {/* Línea de tendencia si está habilitada */}
          {trendLineData && (
            <Scatter
              name="Trend Line"
              data={trendLineData}
              fill="#EF4444"
              line={{ stroke: '#EF4444', strokeWidth: 2 }}
              shape="circle"
              fillOpacity={0}
              isAnimationActive={false}
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
};
