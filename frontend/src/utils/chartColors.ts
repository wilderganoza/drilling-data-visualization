/**
 * Utility functions for getting chart colors dynamically from CSS variables
 */

export const getChartColors = () => {
  const root = document.documentElement;
  const getColor = (varName: string) => 
    getComputedStyle(root).getPropertyValue(varName).trim();

  return {
    // Chart palette (8 colors)
    chart1: getColor('--color-chart-1'),
    chart2: getColor('--color-chart-2'),
    chart3: getColor('--color-chart-3'),
    chart4: getColor('--color-chart-4'),
    chart5: getColor('--color-chart-5'),
    chart6: getColor('--color-chart-6'),
    chart7: getColor('--color-chart-7'),
    chart8: getColor('--color-chart-8'),
    
    // Chart elements
    line: getColor('--color-chart-line'),
    axis: getColor('--color-chart-axis'),
    
    // Tooltip
    tooltipBg: getColor('--color-tooltip-bg'),
    tooltipBorder: getColor('--color-tooltip-border'),
    
    // Text
    text: getColor('--color-text'),
    textMuted: getColor('--color-text-muted'),
    
    // Status colors
    primary: getColor('--color-primary'),
    success: getColor('--color-success'),
    warning: getColor('--color-warning'),
    danger: getColor('--color-danger'),
  };
};

export const getChartPalette = (): string[] => {
  const colors = getChartColors();
  return [
    colors.chart1,
    colors.chart2,
    colors.chart3,
    colors.chart4,
    colors.chart5,
    colors.chart6,
    colors.chart7,
    colors.chart8,
  ];
};

/**
 * Get a color from the chart palette by index (cycles through if index > 7)
 */
export const getChartColor = (index: number): string => {
  const palette = getChartPalette();
  return palette[index % palette.length];
};
