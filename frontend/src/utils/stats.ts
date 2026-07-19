// Utilidades estadísticas iterativas.
// Math.min(...arr) / Math.max(...arr) desbordan la pila con arrays grandes
// (las muestras llegan a 50k-100k puntos), por eso todo aquí itera.

export interface MinMax {
  min: number;
  max: number;
}

// Mínimo y máximo de un array en una sola pasada. Devuelve null si el array
// está vacío o no contiene ningún valor finito.
export function minMax(values: readonly number[]): MinMax | null {
  let min = Infinity;
  let max = -Infinity;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min === Infinity) return null;
  return { min, max };
}

// Máximo valor absoluto finito; null si no hay valores finitos.
export function maxAbs(values: readonly number[]): number | null {
  let result: number | null = null;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    const abs = Math.abs(v);
    if (result === null || abs > result) result = abs;
  }
  return result;
}

// Media aritmética de los valores finitos; null si no hay ninguno.
export function mean(values: readonly number[]): number | null {
  let sum = 0;
  let count = 0;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    sum += v;
    count += 1;
  }
  return count > 0 ? sum / count : null;
}
