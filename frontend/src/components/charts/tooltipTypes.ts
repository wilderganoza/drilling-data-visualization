// Tipado mínimo compartido para los tooltips custom de recharts.
// Los datos de pozo son dinámicos (columnas variables), por eso el payload
// interno es un Record de valores primitivos.
export interface TooltipEntry {
  name?: string;
  value?: number;
  color?: string;
  payload?: Record<string, string | number | null | undefined>;
}

export interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
}
