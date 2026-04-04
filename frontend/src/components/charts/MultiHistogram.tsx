// Importar React
import React from 'react';
// Importar componentes de Recharts para gráficos de área
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

// Interfaz para datos de histograma de un pozo
interface WellHistogramData {
  wellName: string; // Nombre del pozo
  data: number[]; // Datos numéricos del pozo
  color: string; // Color para el pozo
}

// Interfaz de props para el componente MultiHistogram
interface MultiHistogramProps {
  wells: WellHistogramData[]; // Array de pozos con sus datos
  bins?: number; // Número de bins
  xLabel?: string; // Etiqueta del eje X
  yLabel?: string; // Etiqueta del eje Y
  title?: string; // Título del gráfico
  height?: number; // Altura del gráfico
}

// Componente personalizado para tooltip del multi-histograma
const CustomTooltip = ({ active, payload }: any) => {
  // Si el tooltip está activo y tiene datos
  if (active && payload && payload.length) {
    return (
      // Contenedor del tooltip con estilos
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg">
        {/* Mostrar valor del bin */}
        <p className="text-sm text-gray-300 mb-2">
          <span className="font-semibold">Value:</span> {payload[0].payload.binCenter?.toFixed(2)}
        </p>
        {/* Mapear cada pozo y mostrar su frecuencia */}
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            <span className="font-semibold">{entry.name}:</span> {entry.value}
          </p>
        ))}
      </div>
    );
  }
  // Si no está activo, no mostrar nada
  return null;
};

// Componente MultiHistogram para comparar distribuciones de múltiples pozos
export const MultiHistogram: React.FC<MultiHistogramProps> = ({
  wells,
  bins = 20, // Valor por defecto: 20 bins
  xLabel = 'Value', // Etiqueta por defecto del eje X
  yLabel = 'Frequency', // Etiqueta por defecto del eje Y
  title,
  height = 400, // Altura por defecto: 400px
}) => {
  // Función para calcular histograma múltiple
  const calculateMultiHistogram = () => {
    // Obtener todos los valores para determinar min/max global
    const allValues = wells.flatMap(w => w.data.filter(d => d != null && !isNaN(d)));
    // Si no hay valores, retornar datos vacíos
    if (allValues.length === 0) return { data: [], ticks: [] };

    // Calcular valores mínimo y máximo globales
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    // Calcular ancho de cada bin
    const binWidth = (max - min) / bins;

    // Crear bins
    const histogramData = Array.from({ length: bins }, (_, i) => {
      // Calcular inicio, fin y centro del bin
      const binStart = min + i * binWidth;
      const binEnd = binStart + binWidth;
      const binCenter = (binStart + binEnd) / 2;
      
      // Inicializar objeto de datos del bin
      const binData: any = {
        binCenter,
        binStart,
        binEnd,
      };

      // Calcular conteo para cada pozo
      wells.forEach(well => {
        // Filtrar datos válidos del pozo
        const validData = well.data.filter(d => d != null && !isNaN(d));
        // Contar valores que caen en este bin
        const count = validData.filter(d => 
          d >= binStart && (i === bins - 1 ? d <= binEnd : d < binEnd)
        ).length;
        // Asignar conteo al pozo
        binData[well.wellName] = count;
      });

      return binData;
    });

    // Calcular 10 ticks espaciados uniformemente basados en el rango de datos
    const dataMin = histogramData.length > 0 ? Math.min(...histogramData.map(d => d.binCenter)) : 0;
    const dataMax = histogramData.length > 0 ? Math.max(...histogramData.map(d => d.binCenter)) : 100;
    const step = (dataMax - dataMin) / 9;
    const ticks = Array.from({ length: 10 }, (_, i) => dataMin + step * i);

    // Retornar datos del histograma, ticks y rango
    return { data: histogramData, ticks, min: dataMin, max: dataMax };
  };

  // Calcular datos del histograma múltiple
  const { data: histogramData, ticks, min = 0, max = 100 } = calculateMultiHistogram();

  return (
    // Contenedor principal del multi-histograma
    <div>
      {/* Mostrar título si existe */}
      {title && (
        <h3 className="text-lg font-semibold text-gray-100 mb-4">{title}</h3>
      )}
      {/* Contenedor responsivo para el gráfico */}
      <ResponsiveContainer width="100%" height={height}>
        {/* Gráfico de área con márgenes */}
        <AreaChart data={histogramData} margin={{ top: 20, right: 60, left: 50, bottom: 60 }}>
          {/* Cuadrícula cartesiana */}
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          {/* Eje X con ticks personalizados */}
          <XAxis
            type="number"
            dataKey="binCenter"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF' }}
            tickFormatter={(value) => Math.round(value).toString()}
            ticks={ticks}
            domain={[min, max]}
            allowDataOverflow={false}
            label={{
              value: xLabel,
              position: 'insideBottom',
              offset: -25,
              fill: '#9CA3AF',
            }}
          />
          {/* Eje Y con etiqueta rotada */}
          <YAxis
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF' }}
            label={{
              value: yLabel,
              angle: -90,
              position: 'insideLeft',
              fill: '#9CA3AF',
              offset: -10,
              dy: 40,
            }}
          />
          {/* Tooltip personalizado */}
          <Tooltip content={<CustomTooltip />} />
          {/* Leyenda en la parte superior */}
          <Legend
            verticalAlign="top"
            height={36}
            wrapperStyle={{ color: '#9CA3AF' }}
          />
          {/* Mapear cada pozo como un área */}
          {wells.map(well => (
            <Area
              key={well.wellName}
              type="monotone"
              dataKey={well.wellName}
              stroke={well.color}
              fill={well.color}
              fillOpacity={0.3}
              strokeWidth={2}
              dot={false}
              name={well.wellName}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
