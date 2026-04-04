// Importar React
import React from 'react';
// Importar componentes de Recharts para gráficos de barras
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';

// Interfaz de props para el componente Histogram
interface HistogramProps {
  data: number[]; // Array de datos numéricos
  bins?: number; // Número de bins (intervalos)
  xLabel?: string; // Etiqueta del eje X
  yLabel?: string; // Etiqueta del eje Y
  title?: string; // Título del gráfico
  color?: string; // Color base de las barras
  height?: number; // Altura del gráfico
}

// Componente personalizado para tooltip del histograma
const CustomTooltip = ({ active, payload }: any) => {
  // Si el tooltip está activo y tiene datos
  if (active && payload && payload.length) {
    return (
      // Contenedor del tooltip con estilos
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-lg">
        {/* Mostrar rango del bin */}
        <p className="text-sm text-gray-300">
          <span className="font-semibold">Range:</span> {payload[0].payload.range}
        </p>
        {/* Mostrar conteo */}
        <p className="text-sm text-gray-300">
          <span className="font-semibold">Count:</span> {payload[0].value}
        </p>
        {/* Mostrar frecuencia en porcentaje */}
        <p className="text-sm text-gray-300">
          <span className="font-semibold">Frequency:</span> {payload[0].payload.frequency}%
        </p>
      </div>
    );
  }
  // Si no está activo, no mostrar nada
  return null;
};

// Componente Histogram para visualizar distribución de datos
export const Histogram: React.FC<HistogramProps> = ({
  data,
  bins = 20, // Valor por defecto: 20 bins
  xLabel = 'Value', // Etiqueta por defecto del eje X
  yLabel = 'Frequency', // Etiqueta por defecto del eje Y
  title,
  color = '#3B82F6', // Color azul por defecto
  height = 400, // Altura por defecto: 400px
}) => {
  // Función para calcular el histograma
  const calculateHistogram = () => {
    // Filtrar datos válidos (no nulos y no NaN)
    const validData = data.filter(d => d != null && !isNaN(d));
    // Si no hay datos válidos, retornar array vacío
    if (validData.length === 0) return [];

    // Calcular valores mínimo y máximo
    const min = Math.min(...validData);
    const max = Math.max(...validData);
    // Calcular ancho de cada bin
    const binWidth = (max - min) / bins;

    // Crear array de bins
    const histogram = Array.from({ length: bins }, (_, i) => {
      // Calcular inicio y fin del bin
      const binStart = min + i * binWidth;
      const binEnd = binStart + binWidth;
      // Contar valores que caen en este bin (incluir el último valor en el último bin)
      const count = validData.filter(d => d >= binStart && (i === bins - 1 ? d <= binEnd : d < binEnd)).length;
      
      // Retornar objeto con información del bin
      return {
        range: `${binStart.toFixed(2)} - ${binEnd.toFixed(2)}`, // Rango formateado
        binStart, // Inicio del bin
        binEnd, // Fin del bin
        count, // Conteo de valores
        frequency: ((count / validData.length) * 100).toFixed(1), // Frecuencia en porcentaje
      };
    });

    // Retornar histograma calculado
    return histogram;
  };

  // Calcular datos del histograma
  const histogramData = calculateHistogram();

  // Función para obtener color de barra según intensidad
  const getBarColor = (value: number) => {
    // Obtener conteo máximo
    const maxCount = Math.max(...histogramData.map(d => d.count));
    // Calcular intensidad relativa
    const intensity = value / maxCount;
    
    // Retornar color según intensidad (más oscuro = mayor frecuencia)
    if (intensity > 0.7) return '#3B82F6'; // Azul oscuro
    if (intensity > 0.4) return '#60A5FA'; // Azul medio
    return '#93C5FD'; // Azul claro
  };

  return (
    // Contenedor principal del histograma
    <div className="bg-gray-900 rounded-lg p-4">
      {/* Mostrar título si existe */}
      {title && (
        <h3 className="text-lg font-semibold text-gray-100 mb-4">{title}</h3>
      )}
      {/* Contenedor responsivo para el gráfico */}
      <ResponsiveContainer width="100%" height={height}>
        {/* Gráfico de barras con márgenes */}
        <BarChart data={histogramData} margin={{ top: 20, right: 30, bottom: 60, left: 60 }}>
          {/* Cuadrícula cartesiana */}
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          {/* Eje X con etiquetas rotadas */}
          <XAxis
            dataKey="range"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 10, angle: -45, textAnchor: 'end' }}
            height={80}
            label={{
              value: xLabel,
              position: 'insideBottom',
              offset: -50,
              fill: '#9CA3AF',
            }}
          />
          {/* Eje Y con etiqueta rotada */}
          <YAxis
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            label={{
              value: yLabel,
              angle: -90,
              position: 'insideLeft',
              offset: -40,
              fill: '#9CA3AF',
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
          {/* Barras del histograma con bordes redondeados */}
          <Bar dataKey="count" name="Frequency" radius={[4, 4, 0, 0]}>
            {/* Mapear cada barra con color según intensidad */}
            {histogramData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getBarColor(entry.count)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
