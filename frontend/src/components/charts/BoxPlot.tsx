// Importar React
import React from 'react';

// Interfaz de props para el componente BoxPlot
interface BoxPlotProps {
  data: { [key: string]: number[] }; // Datos agrupados por categoría
  xLabel?: string; // Etiqueta del eje X
  yLabel?: string; // Etiqueta del eje Y
  title?: string; // Título del gráfico
  height?: number; // Altura del gráfico
  colors?: string[]; // Array de colores para las cajas
}

// Interfaz para estadísticas de caja (box plot)
interface BoxStats {
  name: string; // Nombre de la categoría
  min: number; // Valor mínimo (sin outliers)
  q1: number; // Primer cuartil (25%)
  median: number; // Mediana (50%)
  q3: number; // Tercer cuartil (75%)
  max: number; // Valor máximo (sin outliers)
  outliers: number[]; // Valores atípicos
  color: string; // Color de la caja
}

// Función para calcular estadísticas de box plot
const calculateBoxStats = (values: number[]): Omit<BoxStats, 'name' | 'color'> => {
  // Ordenar valores de menor a mayor
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;

  // Calcular cuartiles
  const q1 = sorted[Math.floor(n * 0.25)]; // Primer cuartil
  const median = sorted[Math.floor(n * 0.5)]; // Mediana
  const q3 = sorted[Math.floor(n * 0.75)]; // Tercer cuartil
  const iqr = q3 - q1; // Rango intercuartílico

  // Calcular límites para outliers (método de Tukey)
  const lowerFence = q1 - 1.5 * iqr; // Límite inferior
  const upperFence = q3 + 1.5 * iqr; // Límite superior

  // Identificar outliers y valores normales
  const outliers = sorted.filter(v => v < lowerFence || v > upperFence);
  const nonOutliers = sorted.filter(v => v >= lowerFence && v <= upperFence);

  // Retornar estadísticas calculadas
  return {
    min: nonOutliers[0] || sorted[0], // Mínimo sin outliers
    q1,
    median,
    q3,
    max: nonOutliers[nonOutliers.length - 1] || sorted[sorted.length - 1], // Máximo sin outliers
    outliers,
  };
};

// Componente BoxPlot para visualizar distribución de datos con cajas y bigotes
export const BoxPlot: React.FC<BoxPlotProps> = ({
  data,
  xLabel = 'Category', // Etiqueta por defecto del eje X
  yLabel = 'Value', // Etiqueta por defecto del eje Y
  title,
  height = 400, // Altura por defecto: 400px
  colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'], // Colores por defecto
}) => {
  // Calcular estadísticas para cada categoría
  const boxStats: BoxStats[] = Object.entries(data).map(([name, values], index) => ({
    name,
    ...calculateBoxStats(values),
    color: colors[index % colors.length], // Asignar color cíclicamente
  }));

  // Obtener todos los valores para calcular escala
  const allValues = Object.values(data).flat();
  const yMin = Math.min(...allValues); // Valor mínimo global
  const yMax = Math.max(...allValues); // Valor máximo global
  const yRange = yMax - yMin; // Rango de valores
  const padding = yRange * 0.1; // Padding del 10%

  // Configuración de dimensiones del gráfico
  const chartHeight = height - 100;
  const boxWidth = 60; // Ancho de cada caja
  const spacing = 100; // Espaciado entre cajas
  const chartWidth = boxStats.length * spacing + 100; // Ancho total

  // Función para escalar valores al sistema de coordenadas SVG
  const scaleY = (value: number) => {
    return chartHeight - ((value - (yMin - padding)) / (yRange + 2 * padding)) * chartHeight;
  };

  return (
    // Contenedor principal del box plot
    <div>
      {/* Mostrar título si existe */}
      {title && (
        <h3 className="text-lg font-semibold text-gray-100 mb-4">{title}</h3>
      )}
      {/* Contenedor del SVG */}
      <div style={{ width: '100%', height: height }}>
        {/* SVG responsivo con viewBox */}
        <svg width="100%" height={height} viewBox={`0 0 ${chartWidth} ${height}`} preserveAspectRatio="xMidYMid meet">
          {/* Etiqueta del eje X */}
          <text
            x={chartWidth / 2}
            y={height - 20}
            textAnchor="middle"
            fill="#9CA3AF"
            fontSize="12"
          >
            {xLabel}
          </text>

          {/* Etiqueta del eje Y (rotada) */}
          <text
            x={30}
            y={height / 2}
            textAnchor="middle"
            fill="#9CA3AF"
            fontSize="14"
            fontWeight="bold"
            transform={`rotate(-90, 20, ${height / 2})`}
          >
            {yLabel}
          </text>

          {/* Grupo principal con transformación */}
          <g transform={`translate(60, 40)}`}>
            {/* Mapear cada caja del box plot */}
            {boxStats.map((box, index) => {
              // Calcular posición X de la caja
              const x = index * spacing + spacing / 2;

              return (
                <g key={box.name}>
                  {/* Línea inferior (min a Q1) */}
                  <line
                    x1={x}
                    y1={scaleY(box.min)}
                    x2={x}
                    y2={scaleY(box.q1)}
                    stroke={box.color}
                    strokeWidth="2"
                    strokeDasharray="4"
                  />

                  {/* Rectángulo de la caja (Q1 a Q3) */}
                  <rect
                    x={x - boxWidth / 2}
                    y={scaleY(box.q3)}
                    width={boxWidth}
                    height={scaleY(box.q1) - scaleY(box.q3)}
                    fill={box.color}
                    fillOpacity="0.3"
                    stroke={box.color}
                    strokeWidth="2"
                  />

                  {/* Línea de la mediana */}
                  <line
                    x1={x - boxWidth / 2}
                    y1={scaleY(box.median)}
                    x2={x + boxWidth / 2}
                    y2={scaleY(box.median)}
                    stroke={box.color}
                    strokeWidth="3"
                  />

                  {/* Línea superior (Q3 a max) */}
                  <line
                    x1={x}
                    y1={scaleY(box.q3)}
                    x2={x}
                    y2={scaleY(box.max)}
                    stroke={box.color}
                    strokeWidth="2"
                    strokeDasharray="4"
                  />

                  {/* Tapa inferior (min) */}
                  <line
                    x1={x - 10}
                    y1={scaleY(box.min)}
                    x2={x + 10}
                    y2={scaleY(box.min)}
                    stroke={box.color}
                    strokeWidth="2"
                  />

                  {/* Tapa superior (max) */}
                  <line
                    x1={x - 10}
                    y1={scaleY(box.max)}
                    x2={x + 10}
                    y2={scaleY(box.max)}
                    stroke={box.color}
                    strokeWidth="2"
                  />

                  {/* Outliers como círculos */}
                  {box.outliers.map((outlier, i) => (
                    <circle
                      key={i}
                      cx={x}
                      cy={scaleY(outlier)}
                      r="3"
                      fill={box.color}
                      opacity="0.6"
                    />
                  ))}

                  {/* Etiqueta de la categoría */}
                  <text
                    x={x}
                    y={chartHeight + 20}
                    textAnchor="middle"
                    fill="#9CA3AF"
                    fontSize="12"
                  >
                    {box.name}
                  </text>
                </g>
              );
            })}

            {/* Líneas de cuadrícula del eje Y */}
            {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
              // Calcular valor y posición Y para cada línea de cuadrícula
              const value = yMin - padding + (yRange + 2 * padding) * fraction;
              const y = scaleY(value);
              return (
                <g key={fraction}>
                  {/* Línea de cuadrícula horizontal */}
                  <line
                    x1={-10}
                    y1={y}
                    x2={boxStats.length * spacing}
                    y2={y}
                    stroke="#374151"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  {/* Etiqueta del valor */}
                  <text
                    x={-15}
                    y={y + 4}
                    textAnchor="end"
                    fill="#9CA3AF"
                    fontSize="10"
                  >
                    {value.toFixed(1)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* Panel de estadísticas debajo del gráfico */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        {/* Mapear cada caja para mostrar sus estadísticas */}
        {boxStats.map((box) => (
          <div key={box.name} className="bg-gray-800 rounded p-3">
            {/* Nombre de la categoría con color */}
            <p className="font-semibold text-gray-300 mb-2" style={{ color: box.color }}>
              {box.name}
            </p>
            {/* Estadísticas de la caja */}
            <div className="space-y-1 text-xs text-gray-400">
              <p>Min: {box.min.toFixed(2)}</p>
              <p>Q1: {box.q1.toFixed(2)}</p>
              <p>Median: {box.median.toFixed(2)}</p>
              <p>Q3: {box.q3.toFixed(2)}</p>
              <p>Max: {box.max.toFixed(2)}</p>
              <p>Outliers: {box.outliers.length}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
