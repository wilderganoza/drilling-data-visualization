import React, { useEffect, useMemo, useState, useCallback } from 'react';
import type { CSSProperties } from 'react';
import { Layout } from '../components/layout/Layout';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  PageHeader,
} from '../components/ui';
import { useWells, useDepthSampleData } from '../hooks';
import {
  useOutlierDataset,
  useOutlierDatasets,
  useOutlierDatasetData,
  useRunOutlierDetection,
} from '../hooks/useOutlierDetection';
import { getProcessedDataset } from '../api/endpoints/outliers';
import type {
  OutlierDetectionRequest,
  OutlierMethod,
  ScalingConfig,
  PCAConfig,
  OutlierConfig,
} from '../api/endpoints/outliers';
import { useAppStore } from '../store/appStore';
import { getParameterLabel } from '../constants/parameterLabels';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

const fieldStyle: CSSProperties = {
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius)',
  color: 'var(--color-text)',
  boxShadow: 'none',
};

const checkboxStyle: CSSProperties = {
  accentColor: 'var(--color-primary)',
};

const chartAxisColor = '#9CA3AF';
const chartGridColor = '#374151';

const tooltipContentStyle: CSSProperties = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '0.5rem',
};

const scalingMethods: Array<{ label: string; value: ScalingConfig['method'] }> = [
  { label: 'None', value: 'none' },
  { label: 'Standard Scaler', value: 'standard' },
  { label: 'Min-Max Scaler', value: 'minmax' },
  { label: 'Robust Scaler', value: 'robust' },
  { label: 'MaxAbs Scaler', value: 'maxabs' },
];

const outlierMethods: Array<{ label: string; value: OutlierMethod }> = [
  { label: 'Isolation Forest', value: 'isolation_forest' },
  { label: 'DBSCAN', value: 'dbscan' },
  { label: 'Local Outlier Factor', value: 'local_outlier_factor' },
  { label: 'Z-Score Threshold', value: 'zscore' },
  { label: 'IQR Threshold', value: 'iqr' },
];

const defaultOutlierVariables = [
  'weight_on_bit_klbs',
  'rate_of_penetration_ft_per_hr',
  'rotary_rpm_rpm',
  'standpipe_pressure_psi',
  'differential_pressure_psi',
  'hook_load_klbs',
  'bit_depth_feet',
];

const requiredMetadataColumns = ['hh_mm_ss', 'id', 'well_id', 'yyyy_mm_dd'];

const formatNumber = (value: number | null | undefined, fractionDigits = 2) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return value.toLocaleString(undefined, { maximumFractionDigits: fractionDigits });
};

const formatDateTime = (value: string | null) => {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
};

const formatPercent = (value: number) => {
  if (!Number.isFinite(value)) return 'N/A';
  if (value >= 99.95) return '100%';
  if (value <= 0.05) return '0%';
  return value >= 10 ? `${Math.round(value)}%` : `${value.toFixed(1)}%`;
};

type ColumnCompletenessStats = {
  present: number;
  missing: number;
  percent: number;
};

type ValueEntry = {
  value: number;
  isOutlier: boolean;
};

type HistogramBin = {
  label: string;
  inliers: number;
  outliers: number;
  center: number;
  density: number;
};

type DensityComparisonBin = {
  label: string;
  center: number;
  preDensity: number;
  postDensity: number;
};

type VariableDiagnostics = {
  variable: string;
  sampleSize: number;
  min: number;
  max: number;
  q1: number;
  median: number;
  q3: number;
  lowerWhisker: number;
  upperWhisker: number;
  mean: number;
  std: number;
  outlierRatio: number;
  outlierCount: number;
  histogram: HistogramBin[];
  violin: Array<{ center: number; positive: number; negative: number; label: string }>;
};

type ScalingStats = {
  min: number;
  max: number;
  range: number;
  mean: number;
  std: number;
  median: number;
  iqr: number;
  maxAbs: number;
  q1: number;
  q3: number;
};

type ScalingPreviewRow = {
  index: number;
  raw: Record<string, number | null>;
  scaled: Record<string, number | null>;
};

type ScalingPreviewData = {
  rows: ScalingPreviewRow[];
  stats: Record<string, ScalingStats>;
  totalRows: number;
  variableOrder: string[];
  rawMatrix: number[][];
  scaledMatrix: number[][];
  numericRowIndices: number[];
};

type PcaPreviewData = {
  componentLabels: string[];
  explainedVariance: number[];
  explainedVarianceRatio: number[];
  scores: Array<{ index: number; components: number[] }>;
};

type OutlierPreviewRow = {
  index: number;
  score: number;
  isOutlier: boolean;
  raw: Record<string, number | null>;
  scaled: Record<string, number | null>;
  components?: number[];
};

type OutlierPreviewData = {
  method: OutlierMethod;
  rows: OutlierPreviewRow[];
  totalRows: number;
  outlierCount: number;
  threshold?: number;
  contamination?: number;
  componentLabels?: string[];
};

type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error';

type AsyncState<T> = {
  status: AsyncStatus;
  data: T | null;
  error: string | null;
};

const createIdleAsyncState = <T,>(): AsyncState<T> => ({
  status: 'idle',
  data: null,
  error: null,
});

const computeQuantile = (sorted: number[], q: number) => {
  if (!sorted.length) return NaN;
  if (sorted.length === 1) return sorted[0];
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (base + 1 < sorted.length) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
};

const computeBoxPlotStats = (sortedValues: number[]) => {
  const q1 = computeQuantile(sortedValues, 0.25);
  const median = computeQuantile(sortedValues, 0.5);
  const q3 = computeQuantile(sortedValues, 0.75);
  const iqr = q3 - q1;
  const lowerFence = q1 - 1.5 * iqr;
  const upperFence = q3 + 1.5 * iqr;
  const withinFence = sortedValues.filter((value) => value >= lowerFence && value <= upperFence);
  const lowerWhisker = withinFence.length ? withinFence[0] : sortedValues[0];
  const upperWhisker = withinFence.length
    ? withinFence[withinFence.length - 1]
    : sortedValues[sortedValues.length - 1];
  const outlierCount = sortedValues.length - withinFence.length;

  return {
    q1,
    median,
    q3,
    lowerWhisker,
    upperWhisker,
    outlierCount,
  };
};

const computeHistogramBins = (entries: ValueEntry[], requestedBins = 12): HistogramBin[] => {
  if (!entries.length) {
    return [];
  }

  const values = entries.map((entry) => entry.value);
  const min = Math.min(...values);
  const max = Math.max(...values);

  if (min === max) {
    const outliers = entries.filter((entry) => entry.isOutlier).length;
    const inliers = entries.length - outliers;
    return [
      {
        label: min.toFixed(2),
        inliers,
        outliers,
        center: min,
        density: 1,
      },
    ];
  }

  const range = max - min;
  const safeBinCount = Math.max(6, Math.min(requestedBins, Math.floor(entries.length / 2) || requestedBins));
  const step = range / safeBinCount;

  const bins = Array.from({ length: safeBinCount }, (_, index) => ({
    start: min + index * step,
    end: index === safeBinCount - 1 ? max : min + (index + 1) * step,
    inliers: 0,
    outliers: 0,
  }));

  entries.forEach((entry) => {
    let idx = Math.floor((entry.value - min) / step);
    if (idx >= bins.length) {
      idx = bins.length - 1;
    }
    if (entry.isOutlier) {
      bins[idx].outliers += 1;
    } else {
      bins[idx].inliers += 1;
    }
  });

  return bins.map((bin) => {
    const total = bin.inliers + bin.outliers;
    return {
      label: `${bin.start.toFixed(2)} - ${bin.end.toFixed(2)}`,
      inliers: bin.inliers,
      outliers: bin.outliers,
      center: (bin.start + bin.end) / 2,
      density: total / entries.length,
    };
  });
};

const buildDensityComparisonBins = (
  preValues: number[],
  postValues: number[],
  requestedBins = 24,
): DensityComparisonBin[] => {
  if (preValues.length === 0 || postValues.length === 0) {
    return [];
  }

  const min = Math.min(...preValues, ...postValues);
  const max = Math.max(...preValues, ...postValues);

  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [];
  }

  if (min === max) {
    return [
      {
        label: min.toFixed(2),
        center: min,
        preDensity: 1,
        postDensity: 1,
      },
    ];
  }

  const binCount = Math.max(8, requestedBins);
  const step = (max - min) / binCount;
  const preCounts = Array.from({ length: binCount }, () => 0);
  const postCounts = Array.from({ length: binCount }, () => 0);

  const toIndex = (value: number) => {
    let idx = Math.floor((value - min) / step);
    if (idx < 0) idx = 0;
    if (idx >= binCount) idx = binCount - 1;
    return idx;
  };

  preValues.forEach((value) => {
    preCounts[toIndex(value)] += 1;
  });
  postValues.forEach((value) => {
    postCounts[toIndex(value)] += 1;
  });

  return Array.from({ length: binCount }, (_, index) => {
    const start = min + step * index;
    const end = index === binCount - 1 ? max : start + step;
    return {
      label: `${start.toFixed(2)} - ${end.toFixed(2)}`,
      center: (start + end) / 2,
      preDensity: preCounts[index] / preValues.length,
      postDensity: postCounts[index] / postValues.length,
    };
  });
};

const computeScaledValue = (method: ScalingConfig['method'], value: number, stats: ScalingStats) => {
  switch (method) {
    case 'standard':
      return stats.std > 0 ? (value - stats.mean) / stats.std : 0;
    case 'minmax':
      return stats.range > 0 ? (value - stats.min) / stats.range : 0;
    case 'robust':
      return stats.iqr > 0 ? (value - stats.median) / stats.iqr : 0;
    case 'maxabs':
      return stats.maxAbs > 0 ? value / stats.maxAbs : 0;
    default:
      return value;
  }
};

const varianceTooltipFormatter = (
  value: number | string | (number | string)[] | undefined,
): [string, string] => {
  const numeric = Array.isArray(value)
    ? Number(value[0] ?? 0)
    : typeof value === 'number'
      ? value
      : Number(value ?? 0);
  const safeNumber = Number.isFinite(numeric) ? numeric : 0;
  return [`${safeNumber.toFixed(2)}%`, 'Explained variance'];
};

const varianceLabelFormatter = (label: string | number | React.ReactNode): string =>
  `Component ${String(label ?? '')}`;

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const buildScalingPreviewData = (
  sample: Array<Record<string, unknown>>,
  variables: string[],
  scalingMethod: ScalingConfig['method'],
): ScalingPreviewData => {
  if (!sample.length) {
    throw new Error('Sample data is empty. Try reloading the well.');
  }

  if (variables.length === 0) {
    throw new Error('Select at least one numeric variable before calculating.');
  }

  const stats: Record<string, ScalingStats> = {};
  const valueMap = new Map<string, number[]>();
  variables.forEach((variable) => valueMap.set(variable, []));

  sample.forEach((row) => {
    variables.forEach((variable) => {
      const value = row?.[variable];
      if (isFiniteNumber(value)) {
        valueMap.get(variable)?.push(value);
      }
    });
  });

  let variablesWithData = 0;

  valueMap.forEach((values, variable) => {
    if (!values.length) {
      return;
    }

    const sorted = [...values].sort((a, b) => a - b);
    const min = sorted[0];
    const max = sorted[sorted.length - 1];
    const range = max - min;
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
    const std = Math.sqrt(variance);
    const median = computeQuantile(sorted, 0.5);
    const q1 = computeQuantile(sorted, 0.25);
    const q3 = computeQuantile(sorted, 0.75);
    const iqr = q3 - q1;
    const maxAbs = Math.max(...values.map((value) => Math.abs(value)));

    stats[variable] = {
      min,
      max,
      range,
      mean,
      std,
      median,
      iqr,
      maxAbs,
      q1,
      q3,
    };

    variablesWithData += 1;
  });

  if (variablesWithData === 0) {
    throw new Error('The selected variables do not contain numeric values in the sampled rows.');
  }

  const rows: ScalingPreviewRow[] = sample.map((row, index) => {
    const raw: Record<string, number | null> = {};
    const scaled: Record<string, number | null> = {};

    variables.forEach((variable) => {
      const rawValue = row?.[variable];
      if (isFiniteNumber(rawValue)) {
        raw[variable] = rawValue;
        const statsForVariable = stats[variable];
        scaled[variable] = statsForVariable
          ? computeScaledValue(scalingMethod, rawValue, statsForVariable)
          : rawValue;
      } else {
        raw[variable] = null;
        scaled[variable] = null;
      }
    });

    return {
      index: index + 1,
      raw,
      scaled,
    };
  });

  const rawMatrix: number[][] = [];
  const scaledMatrix: number[][] = [];
  const numericRowIndices: number[] = [];

  rows.forEach((row, index) => {
    const rawValues = variables.map((variable) => row.raw[variable]);
    if (rawValues.every((value): value is number => typeof value === 'number')) {
      rawMatrix.push(rawValues);
      scaledMatrix.push(variables.map((variable) => row.scaled[variable] as number));
      numericRowIndices.push(index);
    }
  });

  return {
    rows,
    stats,
    totalRows: sample.length,
    variableOrder: variables.slice(),
    rawMatrix,
    scaledMatrix,
    numericRowIndices,
  };
};

const dotProduct = (left: number[], right: number[]) =>
  left.reduce((sum, value, index) => sum + value * (right[index] ?? 0), 0);

const matrixVectorMultiply = (matrix: number[][], vector: number[]) =>
  matrix.map((row) => dotProduct(row, vector));

const vectorNorm = (vector: number[]) => Math.sqrt(dotProduct(vector, vector));

const normalizeVector = (vector: number[]) => {
  const norm = vectorNorm(vector);
  if (!Number.isFinite(norm) || norm === 0) {
    return vector.map(() => 0);
  }
  return vector.map((value) => value / norm);
};

const computePrincipalEigenvector = (matrix: number[][], iterations = 200) => {
  const size = matrix.length;
  let vector = normalizeVector(Array.from({ length: size }, (_, index) => (index % 2 === 0 ? 1 : 0.5)));
  if (vector.every((value) => value === 0)) {
    vector = normalizeVector(Array.from({ length: size }, () => 1));
  }

  for (let index = 0; index < iterations; index += 1) {
    const multiplied = matrixVectorMultiply(matrix, vector);
    const normalized = normalizeVector(multiplied);
    if (normalized.every((value) => value === 0)) {
      break;
    }
    vector = normalized;
  }

  const multiplied = matrixVectorMultiply(matrix, vector);
  const eigenvalue = dotProduct(vector, multiplied);

  return {
    eigenvalue: Number.isFinite(eigenvalue) ? eigenvalue : 0,
    eigenvector: vector,
  };
};

const buildPcaPreviewData = (
  scalingData: ScalingPreviewData,
  pca: PCAConfig,
): PcaPreviewData => {
  if (scalingData.scaledMatrix.length < 2) {
    throw new Error('At least two numeric rows are required to calculate PCA preview.');
  }

  const featureCount = scalingData.variableOrder.length;
  if (featureCount === 0) {
    throw new Error('Select at least one numeric variable before calculating PCA.');
  }

  const maxComponents = Math.min(featureCount, scalingData.scaledMatrix.length);
  const requestedComponents = pca.n_components ?? maxComponents;
  const componentCount = Math.max(1, Math.min(maxComponents, requestedComponents));

  const means = Array.from({ length: featureCount }, (_, column) =>
    scalingData.scaledMatrix.reduce((sum, row) => sum + (row[column] ?? 0), 0) / scalingData.scaledMatrix.length,
  );

  const centered = scalingData.scaledMatrix.map((row) =>
    row.map((value, column) => value - means[column]),
  );

  const denominator = Math.max(1, centered.length - 1);
  const covariance = Array.from({ length: featureCount }, (_, row) =>
    Array.from({ length: featureCount }, (_, column) =>
      centered.reduce((sum, values) => sum + values[row] * values[column], 0) / denominator,
    ),
  );

  const totalVariance = covariance.reduce((sum, row, index) => sum + (row[index] ?? 0), 0);
  const working = covariance.map((row) => row.slice());
  const eigenvalues: number[] = [];
  const eigenvectors: number[][] = [];

  for (let component = 0; component < componentCount; component += 1) {
    const { eigenvalue, eigenvector } = computePrincipalEigenvector(working);
    const safeEigenvalue = eigenvalue > 0 ? eigenvalue : 0;

    eigenvalues.push(safeEigenvalue);
    eigenvectors.push(eigenvector);

    for (let row = 0; row < featureCount; row += 1) {
      for (let column = 0; column < featureCount; column += 1) {
        working[row][column] -= safeEigenvalue * eigenvector[row] * eigenvector[column];
      }
    }
  }

  const scores = centered.map((row, rowIndex) => {
    const components = eigenvectors.map((vector, componentIndex) => {
      const projection = dotProduct(row, vector);
      if (pca.whiten) {
        const eigenvalue = eigenvalues[componentIndex];
        return eigenvalue > 1e-12 ? projection / Math.sqrt(eigenvalue) : 0;
      }
      return projection;
    });
    return {
      index: scalingData.numericRowIndices[rowIndex] + 1,
      components,
    };
  });

  const explainedVariance = eigenvalues.map((value) => Math.max(0, value));
  const explainedVarianceRatio = explainedVariance.map((value) =>
    totalVariance > 0 ? value / totalVariance : 0,
  );
  const componentLabels = explainedVariance.map((_, index) => `PC${index + 1}`);

  return {
    componentLabels,
    explainedVariance,
    explainedVarianceRatio,
    scores,
  };
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const euclideanDistance = (left: number[], right: number[]) =>
  Math.sqrt(left.reduce((sum, value, index) => sum + (value - (right[index] ?? 0)) ** 2, 0));

const buildOutlierPreviewData = (
  scalingData: ScalingPreviewData,
  outlier: OutlierConfig,
  pcaData?: PcaPreviewData | null,
): OutlierPreviewData => {
  const useComponents = Boolean(pcaData?.scores?.length);
  const featureMatrix = useComponents
    ? (pcaData?.scores.map((row) => row.components) ?? [])
    : scalingData.scaledMatrix;

  if (featureMatrix.length < 3) {
    throw new Error('At least three numeric rows are required to preview outlier detection.');
  }

  const rowCount = featureMatrix.length;
  const dimensions = featureMatrix[0]?.length ?? 0;
  if (dimensions === 0) {
    throw new Error('No numeric dimensions available for outlier detection preview.');
  }

  const method = outlier.method;
  const scores = Array.from({ length: rowCount }, () => 0);
  const flags = Array.from({ length: rowCount }, () => false);
  let thresholdValue: number | undefined;

  if (method === 'dbscan') {
    const eps = Math.max(1e-6, Number(outlier.params?.eps ?? 0.5));
    const minSamples = Math.max(1, Math.round(Number(outlier.params?.min_samples ?? 5)));

    for (let row = 0; row < rowCount; row += 1) {
      let neighbors = 0;
      for (let column = 0; column < rowCount; column += 1) {
        if (row === column) continue;
        if (euclideanDistance(featureMatrix[row], featureMatrix[column]) <= eps) {
          neighbors += 1;
        }
      }
      scores[row] = neighbors;
      flags[row] = neighbors < minSamples;
    }
    thresholdValue = minSamples;
  } else if (method === 'zscore') {
    const means = Array.from({ length: dimensions }, (_, dim) =>
      featureMatrix.reduce((sum, row) => sum + row[dim], 0) / rowCount,
    );
    const stds = Array.from({ length: dimensions }, (_, dim) => {
      const variance =
        featureMatrix.reduce((sum, row) => sum + (row[dim] - means[dim]) ** 2, 0) /
        Math.max(1, rowCount - 1);
      return Math.sqrt(variance);
    });
    const threshold = Math.max(0.1, Number(outlier.params?.threshold ?? 3));
    thresholdValue = threshold;

    for (let row = 0; row < rowCount; row += 1) {
      const maxAbsZ = featureMatrix[row].reduce((max, value, dim) => {
        const std = stds[dim];
        const z = std > 1e-12 ? Math.abs((value - means[dim]) / std) : 0;
        return Math.max(max, z);
      }, 0);
      scores[row] = maxAbsZ;
      flags[row] = maxAbsZ > threshold;
    }
  } else if (method === 'iqr') {
    const multiplier = Math.max(0.1, Number(outlier.params?.multiplier ?? 1.5));
    thresholdValue = multiplier;

    const fences = Array.from({ length: dimensions }, (_, dim) => {
      const sorted = featureMatrix.map((row) => row[dim]).sort((a, b) => a - b);
      const q1 = computeQuantile(sorted, 0.25);
      const q3 = computeQuantile(sorted, 0.75);
      const iqr = q3 - q1;
      return {
        lower: q1 - multiplier * iqr,
        upper: q3 + multiplier * iqr,
      };
    });

    for (let row = 0; row < rowCount; row += 1) {
      let violations = 0;
      for (let dim = 0; dim < dimensions; dim += 1) {
        const value = featureMatrix[row][dim];
        if (value < fences[dim].lower || value > fences[dim].upper) {
          violations += 1;
        }
      }
      scores[row] = violations;
      flags[row] = violations > 0;
    }
  } else {
    const contamination = clamp(Number(outlier.params?.contamination ?? 0.05), 0.001, 0.49);
    const neighbors =
      method === 'local_outlier_factor'
        ? Math.max(2, Math.round(Number(outlier.params?.n_neighbors ?? 20)))
        : Math.max(2, Math.round(Math.sqrt(rowCount)));

    for (let row = 0; row < rowCount; row += 1) {
      const distances: number[] = [];
      for (let column = 0; column < rowCount; column += 1) {
        if (row === column) continue;
        distances.push(euclideanDistance(featureMatrix[row], featureMatrix[column]));
      }
      distances.sort((a, b) => a - b);
      const nearest = distances.slice(0, Math.min(neighbors, distances.length));
      const meanDistance =
        nearest.reduce((sum, value) => sum + value, 0) / Math.max(1, nearest.length);
      scores[row] = meanDistance;
    }

    const sortedScores = [...scores].sort((a, b) => a - b);
    const cutoffIndex = Math.max(0, Math.floor((1 - contamination) * (sortedScores.length - 1)));
    const scoreThreshold = sortedScores[cutoffIndex] ?? sortedScores[sortedScores.length - 1] ?? 0;
    thresholdValue = scoreThreshold;
    for (let row = 0; row < rowCount; row += 1) {
      flags[row] = scores[row] >= scoreThreshold;
    }
  }

  const rows: OutlierPreviewRow[] = scalingData.numericRowIndices.map((sourceIndex, row) => ({
    index: sourceIndex + 1,
    score: scores[row] ?? 0,
    isOutlier: flags[row] ?? false,
    raw: scalingData.rows[sourceIndex]?.raw ?? {},
    scaled: scalingData.rows[sourceIndex]?.scaled ?? {},
    components: pcaData?.scores[row]?.components,
  }));

  return {
    method,
    rows,
    totalRows: rows.length,
    outlierCount: rows.filter((item) => item.isOutlier).length,
    threshold: thresholdValue,
    contamination:
      typeof outlier.params?.contamination === 'number'
        ? Number(outlier.params.contamination)
        : undefined,
    componentLabels: pcaData?.componentLabels,
  };
};

type WizardStepKey = 'well' | 'variables' | 'scaling' | 'pca' | 'outlier' | 'review';

const wizardSteps: Array<{ key: WizardStepKey; title: string; description: string }> = [
  {
    key: 'well',
    title: 'Well & dataset',
    description: 'Select a well, set the required dataset name, and load data.',
  },
  {
    key: 'variables',
    title: 'Variables',
    description: 'Select analysis variables and preview their distributions.',
  },
  {
    key: 'scaling',
    title: 'Scaling',
    description: 'Set the scaling method and validate transformed values.',
  },
  {
    key: 'pca',
    title: 'PCA',
    description: 'Configure required PCA settings and inspect component behavior.',
  },
  {
    key: 'outlier',
    title: 'Outlier detection',
    description: 'Set outlier method parameters and preview anomaly labels.',
  },
  {
    key: 'review',
    title: 'Review & run',
    description: 'Review the full setup and run the pipeline.',
  },
];

export const OutlierDetection: React.FC = () => {
  const {
    data: wellsResponse,
    isLoading: wellsLoading,
    error: wellsError,
    refetch: refetchWells,
  } = useWells();
  const wells = wellsResponse?.wells ?? [];
  const addToast = useAppStore((state) => state.addToast);

  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [datasetName, setDatasetName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedVariables, setSelectedVariables] = useState<string[]>([]);
  const [visualizationEnabled, setVisualizationEnabled] = useState(false);
  const [visualizedVariable, setVisualizedVariable] = useState<string>('');
  const [includeOutliersPreview, setIncludeOutliersPreview] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null);
  const [selectedCaseDatasetId, setSelectedCaseDatasetId] = useState<number | null>(null);
  const [hydratingFromCase, setHydratingFromCase] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [previewTab, setPreviewTab] = useState<'records' | 'scaled' | 'components'>('records');
  const [previewPage, setPreviewPage] = useState(1);
  const [previewPageSize, setPreviewPageSize] = useState(20);

  const [scalingConfig, setScalingConfig] = useState<ScalingConfig>({ method: 'standard', params: {} });
  const [pcaConfig, setPcaConfig] = useState<PCAConfig>({ enabled: true, n_components: undefined, whiten: false, svd_solver: 'auto' });
  const [outlierConfig, setOutlierConfig] = useState<OutlierConfig>({
    method: 'isolation_forest',
    params: { contamination: 0.05 },
    mark_outliers: true,
  });
  const [formErrors, setFormErrors] = useState<string[]>([]);

  const appliedWell = useMemo(
    () => wells.find((well) => well.id === appliedWellId) ?? null,
    [wells, appliedWellId],
  );
  const { data: existingCases, isLoading: existingCasesLoading } = useOutlierDatasets(selectedWellId);

  const allRowsLimit =
    typeof appliedWell?.total_rows === 'number' && appliedWell.total_rows > 0
      ? appliedWell.total_rows
      : 100000;

  const { data: depthData } = useDepthSampleData(appliedWellId ?? 0, allRowsLimit);
  const availableColumns = useMemo(() => {
    if (!depthData?.data?.length) return [] as string[];
    return Object.keys(depthData.data[0]).sort();
  }, [depthData]);

  const sampleRows = useMemo(() => depthData?.data ?? [], [depthData?.data]);
  const selectableVariableColumns = useMemo(
    () => availableColumns.filter((column) => !requiredMetadataColumns.includes(column)),
    [availableColumns],
  );
  const autoIncludedColumns = useMemo(
    () => availableColumns.filter((column) => !selectedVariables.includes(column)),
    [availableColumns, selectedVariables],
  );

  const selectedVariableDiagnostics = useMemo<VariableDiagnostics[]>(() => {
    if (!sampleRows.length || selectedVariables.length === 0) {
      return [];
    }

    return selectedVariables
      .map((variable) => {
        const values = sampleRows
          .map((row) => row?.[variable])
          .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
          .sort((a, b) => a - b);

        if (values.length < 2) {
          return null;
        }

        const sampleSize = values.length;
        const min = values[0];
        const max = values[values.length - 1];
        const mean = values.reduce((sum, value) => sum + value, 0) / sampleSize;
        const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / sampleSize;
        const std = Math.sqrt(variance);
        const boxStats = computeBoxPlotStats(values);
        const entries: ValueEntry[] = values.map((value) => ({ value, isOutlier: false }));
        const histogram = computeHistogramBins(entries);
        const violin = histogram.map((bin) => ({
          center: bin.center,
          positive: bin.density,
          negative: -bin.density,
          label: bin.label,
        }));

        return {
          variable,
          sampleSize,
          min,
          max,
          q1: boxStats.q1,
          median: boxStats.median,
          q3: boxStats.q3,
          lowerWhisker: boxStats.lowerWhisker,
          upperWhisker: boxStats.upperWhisker,
          mean,
          std,
          outlierRatio: sampleSize > 0 ? boxStats.outlierCount / sampleSize : 0,
          outlierCount: boxStats.outlierCount,
          histogram,
          violin,
        } satisfies VariableDiagnostics;
      })
      .filter((item): item is VariableDiagnostics => Boolean(item));
  }, [sampleRows, selectedVariables]);

  const activeVariableDiagnostics = useMemo(
    () =>
      selectedVariableDiagnostics.find((diag) => diag.variable === visualizedVariable) ??
      selectedVariableDiagnostics[0] ??
      null,
    [selectedVariableDiagnostics, visualizedVariable],
  );

  const activeVariableDistributionData = useMemo(
    () =>
      activeVariableDiagnostics
        ? activeVariableDiagnostics.histogram.map((bin) => ({
            label: bin.label,
            center: bin.center,
            count: bin.inliers + bin.outliers,
          }))
        : [],
    [activeVariableDiagnostics],
  );

  const activeVariableDensityData = useMemo(
    () =>
      activeVariableDiagnostics
        ? activeVariableDiagnostics.histogram.map((bin) => ({
            center: bin.center,
            density: bin.density * 100,
          }))
        : [],
    [activeVariableDiagnostics],
  );

  const activeVariableXAxisTicks = useMemo(() => {
    if (!activeVariableDiagnostics) {
      return [] as number[];
    }

    const min = activeVariableDiagnostics.min;
    const max = activeVariableDiagnostics.max;
    if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
      return [min];
    }

    const step = (max - min) / 9;
    return Array.from({ length: 10 }, (_, index) => min + step * index);
  }, [activeVariableDiagnostics]);

  const activeVariableBoxPoints = useMemo(() => {
    if (!activeVariableDiagnostics) {
      return [] as Array<{ x: number; y: number; element: string }>;
    }

    return [
      { x: activeVariableDiagnostics.lowerWhisker, y: 1, element: 'Lower whisker' },
      { x: activeVariableDiagnostics.q1, y: 1, element: 'Q1' },
      { x: activeVariableDiagnostics.median, y: 1, element: 'Median' },
      { x: activeVariableDiagnostics.q3, y: 1, element: 'Q3' },
      { x: activeVariableDiagnostics.upperWhisker, y: 1, element: 'Upper whisker' },
      { x: activeVariableDiagnostics.min, y: 1, element: 'Min' },
      { x: activeVariableDiagnostics.max, y: 1, element: 'Max' },
    ];
  }, [activeVariableDiagnostics]);

  const columnCompleteness = useMemo(() => {
    if (!depthData?.data?.length || availableColumns.length === 0) {
      return {} as Record<string, ColumnCompletenessStats>;
    }

    const totalRows = depthData.data.length;
    const counts: Record<string, number> = Object.fromEntries(
      availableColumns.map((column) => [column, 0])
    );

    depthData.data.forEach((row) => {
      availableColumns.forEach((column) => {
        const value = row[column];
        const isMissing =
          value === null ||
          value === undefined ||
          (typeof value === 'number' && Number.isNaN(value));
        if (!isMissing) {
          counts[column] = (counts[column] ?? 0) + 1;
        }
      });
    });

    return availableColumns.reduce<Record<string, ColumnCompletenessStats>>((acc, column) => {
      const present = counts[column] ?? 0;
      const missing = totalRows - present;
      acc[column] = {
        present,
        missing,
        percent: totalRows ? (present / totalRows) * 100 : 0,
      };
      return acc;
    }, {});
  }, [availableColumns, depthData]);

  useEffect(() => {
    if (availableColumns.length) {
      const numericCandidates = selectableVariableColumns.filter((column) => {
        const sampleValue = depthData?.data?.[0]?.[column];
        return typeof sampleValue === 'number';
      });
      if (!selectedVariables.length && numericCandidates.length) {
        const preferredDefaults = defaultOutlierVariables.filter((variable) =>
          numericCandidates.includes(variable),
        );
        setSelectedVariables(
          preferredDefaults.length > 0 ? preferredDefaults : numericCandidates.slice(0, 7),
        );
      }
    } else {
      setSelectedVariables([]);
    }
  }, [availableColumns, depthData, selectableVariableColumns, selectedVariables.length]);

  useEffect(() => {
    if (selectedVariables.length === 0) {
      setVisualizedVariable('');
      setVisualizationEnabled(false);
      return;
    }

    if (!visualizedVariable || !selectedVariables.includes(visualizedVariable)) {
      setVisualizedVariable(selectedVariables[0]);
    }
  }, [selectedVariables, visualizedVariable]);

  const { data: datasetDetail } = useOutlierDataset(selectedDatasetId);
  const {
    data: datasetData,
    isLoading: isDatasetDataLoading,
  } = useOutlierDatasetData(selectedDatasetId, {
    includeOutliers: includeOutliersPreview,
    page: previewPage,
    pageSize: previewPageSize,
  });
  const densityPreviewLimit = useMemo(() => {
    const metricTotal = datasetDetail?.metrics?.total_records;
    if (typeof metricTotal === 'number' && metricTotal > 0) {
      return Math.min(metricTotal, 5000);
    }
    return 5000;
  }, [datasetDetail?.metrics?.total_records]);
  const {
    data: densityDatasetData,
    isLoading: isDensityDatasetLoading,
  } = useOutlierDatasetData(selectedDatasetId, {
    includeOutliers: false,
    page: 1,
    pageSize: densityPreviewLimit,
  });

  const selectedWell = useMemo(() => wells.find((well) => well.id === selectedWellId) ?? null, [wells, selectedWellId]);

  const runOutlierDetectionMutation = useRunOutlierDetection();

  const [scalingPreviewPage, setScalingPreviewPage] = useState(1);
  const [scalingPreviewPageSize, setScalingPreviewPageSize] = useState(20);
  const [scalingPreview, setScalingPreview] = useState<AsyncState<ScalingPreviewData>>(
    createIdleAsyncState<ScalingPreviewData>(),
  );
  const [pcaPreview, setPcaPreview] = useState<AsyncState<PcaPreviewData>>(
    createIdleAsyncState<PcaPreviewData>(),
  );
  const [pcaScatterX, setPcaScatterX] = useState(0);
  const [pcaScatterY, setPcaScatterY] = useState(1);
  const [pcaScatterPlotted, setPcaScatterPlotted] = useState(false);
  const [outlierPreview, setOutlierPreview] = useState<AsyncState<OutlierPreviewData>>(
    createIdleAsyncState<OutlierPreviewData>(),
  );
  const [outlierScatterX, setOutlierScatterX] = useState(0);
  const [outlierScatterY, setOutlierScatterY] = useState(1);
  const [outlierScatterPlotted, setOutlierScatterPlotted] = useState(false);

  const canCalculateScaling = Boolean(appliedWellId) && selectedVariables.length > 0 && sampleRows.length > 0;
  const handleCalculateScalingPreview = useCallback(() => {
    if (!canCalculateScaling) {
      setScalingPreview({
        status: 'error',
        data: null,
        error:
          selectedVariables.length === 0
            ? 'Select at least one numeric variable before calculating.'
            : 'Load a well and ensure sample data is available to calculate the preview.',
      });
      return;
    }

    setScalingPreview({ status: 'loading', data: null, error: null });

    try {
      const data = buildScalingPreviewData(sampleRows, selectedVariables, scalingConfig.method);
      setScalingPreview({ status: 'ready', data, error: null });
      setScalingPreviewPage(1);
    } catch (error) {
      setScalingPreview({
        status: 'error',
        data: null,
        error: error instanceof Error ? error.message : 'Failed to calculate scaling preview.',
      });
    }
  }, [canCalculateScaling, sampleRows, selectedVariables, scalingConfig.method]);

  const scalingPreviewRows = useMemo(() => {
    if (scalingPreview.status !== 'ready' || !scalingPreview.data) {
      return [] as ScalingPreviewRow[];
    }

    const startIndex = (scalingPreviewPage - 1) * scalingPreviewPageSize;
    const endIndex = startIndex + scalingPreviewPageSize;
    return scalingPreview.data.rows.slice(startIndex, endIndex);
  }, [scalingPreview, scalingPreviewPage, scalingPreviewPageSize]);

  const scalingTotalRows = scalingPreview.data?.totalRows ?? 0;
  const scalingTotalPages = scalingTotalRows ? Math.ceil(scalingTotalRows / scalingPreviewPageSize) : 1;
  const hasScalingPreview = scalingPreview.status === 'ready' && scalingPreviewRows.length > 0;
  const scalingPageFirst = hasScalingPreview
    ? (scalingPreviewPage - 1) * scalingPreviewPageSize + 1
    : 0;
  const scalingPageLast = hasScalingPreview
    ? Math.min(scalingPreviewPage * scalingPreviewPageSize, scalingTotalRows)
    : 0;
  const isScalingCalculating = scalingPreview.status === 'loading';
  const canCalculatePca = Boolean(appliedWellId) && selectedVariables.length > 0 && sampleRows.length > 0;
  const isPcaCalculating = pcaPreview.status === 'loading';
  const canCalculateOutlier = Boolean(appliedWellId) && selectedVariables.length > 0 && sampleRows.length > 0;
  const isOutlierCalculating = outlierPreview.status === 'loading';

  const handleCalculatePcaPreview = useCallback(() => {
    if (!canCalculatePca) {
      setPcaPreview({
        status: 'error',
        data: null,
        error: 'Load a well and select numeric variables before calculating PCA.',
      });
      return;
    }

    setPcaPreview({ status: 'loading', data: null, error: null });

    try {
      const scalingData = buildScalingPreviewData(sampleRows, selectedVariables, scalingConfig.method);
      const data = buildPcaPreviewData(scalingData, pcaConfig);
      setPcaPreview({ status: 'ready', data, error: null });
      setPcaScatterX(0);
      setPcaScatterY(data.componentLabels.length > 1 ? 1 : 0);
      setPcaScatterPlotted(false);
    } catch (error) {
      setPcaPreview({
        status: 'error',
        data: null,
        error: error instanceof Error ? error.message : 'Failed to calculate PCA preview.',
      });
    }
  }, [canCalculatePca, pcaConfig, sampleRows, scalingConfig.method, selectedVariables]);

  const handleCalculateOutlierPreview = useCallback(() => {
    if (!canCalculateOutlier) {
      setOutlierPreview({
        status: 'error',
        data: null,
        error: 'Load a well and select numeric variables before calculating outlier preview.',
      });
      return;
    }

    setOutlierPreview({ status: 'loading', data: null, error: null });

    try {
      const scalingData = buildScalingPreviewData(sampleRows, selectedVariables, scalingConfig.method);
      const pcaData = buildPcaPreviewData(scalingData, pcaConfig);
      const data = buildOutlierPreviewData(scalingData, outlierConfig, pcaData);
      setOutlierPreview({ status: 'ready', data, error: null });
      setOutlierScatterX(0);
      setOutlierScatterY((data.componentLabels?.length ?? 0) > 1 ? 1 : 0);
      setOutlierScatterPlotted(false);
    } catch (error) {
      setOutlierPreview({
        status: 'error',
        data: null,
        error: error instanceof Error ? error.message : 'Failed to calculate outlier preview.',
      });
    }
  }, [canCalculateOutlier, outlierConfig, pcaConfig, sampleRows, scalingConfig.method, selectedVariables]);

  useEffect(() => {
    setScalingPreviewPage(1);
    setScalingPreview((prev) =>
      prev.status === 'idle' ? prev : createIdleAsyncState<ScalingPreviewData>(),
    );
  }, [sampleRows, selectedVariables, scalingConfig.method]);

  useEffect(() => {
    setPcaPreview((prev) => (prev.status === 'idle' ? prev : createIdleAsyncState<PcaPreviewData>()));
    setPcaScatterX(0);
    setPcaScatterY(1);
    setPcaScatterPlotted(false);
  }, [sampleRows, selectedVariables, scalingConfig.method, pcaConfig.n_components, pcaConfig.whiten, pcaConfig.svd_solver]);

  useEffect(() => {
    setOutlierPreview((prev) => (prev.status === 'idle' ? prev : createIdleAsyncState<OutlierPreviewData>()));
    setOutlierScatterX(0);
    setOutlierScatterY(1);
    setOutlierScatterPlotted(false);
  }, [sampleRows, selectedVariables, scalingConfig.method, pcaConfig.n_components, pcaConfig.whiten, outlierConfig.method, outlierConfig.params]);

  useEffect(() => {
    setScalingPreviewPage(1);
  }, [scalingPreviewPageSize]);

  useEffect(() => {
    setPreviewPage(1);
  }, [selectedDatasetId, includeOutliersPreview]);

  const hasPcaMetrics = Boolean(datasetDetail?.metrics?.pca_component_labels?.length);

  useEffect(() => {
    if (previewTab === 'components' && !hasPcaMetrics) {
      setPreviewTab('records');
    }
  }, [previewTab, hasPcaMetrics]);

  const pcaPreviewVarianceChartData = useMemo(() => {
    if (pcaPreview.status !== 'ready' || !pcaPreview.data) {
      return [] as Array<{ component: string; percentage: number }>;
    }

    return pcaPreview.data.componentLabels.map((label, index) => ({
      component: label,
      percentage: (pcaPreview.data?.explainedVarianceRatio[index] ?? 0) * 100,
    }));
  }, [pcaPreview]);

  const pcaPreviewScatterData = useMemo(() => {
    if (pcaPreview.status !== 'ready' || !pcaPreview.data) {
      return [] as Array<{ x: number; y: number; row: number }>;
    }

    return pcaPreview.data.scores
      .map((row) => {
        const x = row.components[pcaScatterX];
        const y = row.components[pcaScatterY];
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          return null;
        }
        return {
          x,
          y,
          row: row.index,
        };
      })
      .filter((item): item is { x: number; y: number; row: number } => item !== null);
  }, [pcaPreview, pcaScatterX, pcaScatterY]);

  const outlierPreviewScatterData = useMemo(() => {
    if (outlierPreview.status !== 'ready' || !outlierPreview.data?.rows?.length) {
      return [] as Array<{ x: number; y: number; row: number; isOutlier: boolean }>;
    }

    return outlierPreview.data.rows
      .map((row) => {
        const components = row.components ?? [];
        const x = components[outlierScatterX];
        const y = components[outlierScatterY];
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          return null;
        }
        return {
          x,
          y,
          row: row.index,
          isOutlier: row.isOutlier,
        };
      })
      .filter((item): item is { x: number; y: number; row: number; isOutlier: boolean } => item !== null);
  }, [outlierPreview, outlierScatterX, outlierScatterY]);

  useEffect(() => {
    if (wellsError) {
      addToast('Failed to load wells. Please verify the data service.', 'error');
    }
  }, [wellsError, addToast]);

  useEffect(() => {
    if (!selectedWellId && wells.length > 0) {
      setSelectedWellId(wells[0].id);
    }
  }, [selectedWellId, wells]);

  useEffect(() => {
    setSelectedCaseDatasetId(null);
    setSelectedDatasetId(null);
    setHydratingFromCase(false);
  }, [selectedWellId]);

  useEffect(() => {
    if (!hydratingFromCase) {
      return;
    }
    if (!canCalculateScaling || sampleRows.length === 0 || selectedVariables.length === 0) {
      return;
    }

    handleCalculateScalingPreview();
    handleCalculatePcaPreview();
    handleCalculateOutlierPreview();
    setHydratingFromCase(false);
  }, [
    hydratingFromCase,
    canCalculateScaling,
    sampleRows,
    selectedVariables,
    handleCalculateScalingPreview,
    handleCalculatePcaPreview,
    handleCalculateOutlierPreview,
  ]);

  const handleToggleVariable = (variable: string) => {
    setSelectedVariables((prev) =>
      prev.includes(variable) ? prev.filter((item) => item !== variable) : [...prev, variable]
    );
  };

  const handleLoadExistingCase = async () => {
    if (!selectedWellId || !selectedCaseDatasetId) {
      return;
    }

    try {
      const dataset = await getProcessedDataset(selectedCaseDatasetId);
      const pipelineConfig = dataset.pipeline_config ?? {};

      const variables = Array.isArray(pipelineConfig.variables)
        ? pipelineConfig.variables.filter((item): item is string => typeof item === 'string')
        : [];
      const scaling = (pipelineConfig.scaling ?? {}) as Partial<ScalingConfig>;
      const pca = (pipelineConfig.pca ?? {}) as Partial<PCAConfig>;
      const outlier = (pipelineConfig.outlier ?? {}) as Partial<OutlierConfig>;

      if (variables.length > 0) {
        setSelectedVariables(variables);
        setVisualizedVariable(variables[0] ?? '');
      }

      setScalingConfig({
        method: scaling.method ?? 'standard',
        params: (scaling.params ?? {}) as Record<string, unknown>,
      });
      setPcaConfig({
        enabled: pca.enabled ?? true,
        n_components:
          typeof pca.n_components === 'number' || pca.n_components === null
            ? pca.n_components
            : undefined,
        whiten: pca.whiten ?? false,
        svd_solver: pca.svd_solver ?? 'auto',
      });
      setOutlierConfig({
        method: outlier.method ?? 'isolation_forest',
        params: (outlier.params ?? { contamination: 0.05 }) as Record<string, unknown>,
        mark_outliers: outlier.mark_outliers ?? true,
      });

      setAppliedWellId(selectedWellId);
      setSelectedDatasetId(dataset.id);
      setDatasetName(dataset.name || 'Outlier Detection Run');
      setDescription(dataset.description ?? '');
      setVisualizationEnabled(true);
      setHydratingFromCase(true);
      setCurrentStepIndex(0);
      addToast('Existing case loaded. Review and adjust before running.', 'success');
    } catch (_error) {
      addToast('Failed to load selected case.', 'error');
    }
  };

  const ensureAllStepsValid = (): boolean => {
    for (let index = 0; index < wizardSteps.length - 1; index += 1) {
      const stepKey = wizardSteps[index].key;
      const errors = validateStep(stepKey);
      if (errors.length > 0) {
        setFormErrors(errors);
        addToast(errors[0], 'warning');
        setCurrentStepIndex(index);
        return false;
      }
    }
    setFormErrors([]);
    return true;
  };

  const handleRunPipeline = () => {
    if (!ensureAllStepsValid()) {
      return;
    }

    const payload: OutlierDetectionRequest = {
      well_id: appliedWellId!,
      dataset_name: datasetName.trim(),
      description: description.trim() || undefined,
      variables: selectedVariables,
      scaling: scalingConfig,
      pca: { ...pcaConfig, enabled: true },
      outlier: { ...outlierConfig, mark_outliers: true },
      include_columns: autoIncludedColumns,
    };

    runOutlierDetectionMutation.mutate(payload, {
      onSuccess: (response) => {
        addToast(`Dataset "${response.dataset.name}" created successfully.`, 'success');
        setSelectedDatasetId(response.dataset.id);
        setCurrentStepIndex(0);
      },
      onError: (error) => {
        addToast(error.message || 'Failed to run outlier detection.', 'error');
      },
    });
  };

  const currentStep = wizardSteps[currentStepIndex];
  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === wizardSteps.length - 1;

  const validateStep = (stepKey: WizardStepKey): string[] => {
    const errors: string[] = [];

    switch (stepKey) {
      case 'well':
        if (!selectedWellId) {
          errors.push('Select a well before continuing.');
        }
        if (!datasetName.trim()) {
          errors.push('Dataset name is required.');
        }
        if (!appliedWellId) {
          errors.push('Load the selected well to explore its columns.');
        }
        return errors;
      case 'variables':
        if (selectedVariables.length === 0) {
          errors.push('Select at least one variable for outlier detection.');
        }
        return errors;
      case 'scaling':
        return errors;
      case 'pca':
        if (
          pcaConfig.n_components !== undefined &&
          pcaConfig.n_components !== null &&
          pcaConfig.n_components <= 0
        ) {
          errors.push('PCA components must be greater than zero.');
        }
        return errors;
      case 'outlier':
        return errors;
      case 'review': {
        const aggregate = [
          ...validateStep('well'),
          ...validateStep('variables'),
          ...validateStep('scaling'),
          ...validateStep('pca'),
          ...validateStep('outlier'),
        ];
        return Array.from(new Set(aggregate));
      }
      default:
        return errors;
    }
  };

  const handlePrevStep = () => {
    setFormErrors([]);
    setCurrentStepIndex((index) => Math.max(0, index - 1));
  };

  const handleNextStep = () => {
    const errors = validateStep(currentStep.key);
    if (errors.length > 0) {
      setFormErrors(errors);
      addToast(errors[0], 'warning');
      return;
    }

    setFormErrors([]);
    setCurrentStepIndex((index) => Math.min(wizardSteps.length - 1, index + 1));
  };

  const handleGoToStep = (index: number) => {
    if (index > currentStepIndex) {
      return;
    }
    setFormErrors([]);
    setCurrentStepIndex(index);
  };

  const previewColumns = useMemo(() => {
    if (!datasetData?.records?.length) {
      return [] as string[];
    }

    if (previewTab === 'scaled') {
      const scaledLabels = datasetDetail?.metrics?.scaled_feature_labels ?? [];
      if (scaledLabels.length) {
        return scaledLabels;
      }
      return Object.keys(datasetData.records[0]?.scaled ?? {});
    }

    if (previewTab === 'components') {
      const componentLabels = datasetDetail?.metrics?.pca_component_labels ?? [];
      if (componentLabels.length) {
        return componentLabels;
      }
      return Object.keys(datasetData.records[0]?.components ?? {});
    }

    const recordColumns = Object.keys(datasetData.records[0]?.data ?? {});
    const withSource = datasetData.records.some((record) => record.source_record_id !== null)
      ? ['source_record_id', ...recordColumns]
      : recordColumns;
    return withSource;
  }, [datasetData, datasetDetail, previewTab]);

  const totalPages = useMemo(() => {
    if (!datasetData) return 0;
    return Math.max(1, Math.ceil(datasetData.total_records / datasetData.page_size));
  }, [datasetData]);

  const varianceChartData = useMemo(() => {
    const ratios = datasetDetail?.metrics?.explained_variance_ratio ?? [];
    const labels = datasetDetail?.metrics?.pca_component_labels ?? [];
    return ratios.map((value, index) => ({
      component: labels[index] ?? `PC${index + 1}`,
      percentage: value * 100,
    }));
  }, [datasetDetail]);

  const scatterData = useMemo(() => {
    if (!datasetData?.records?.length) return [] as Array<Record<string, unknown>>;
    const labels = datasetDetail?.metrics?.pca_component_labels;
    if (!labels || labels.length < 2) return [] as Array<Record<string, unknown>>;
    const [xKey, yKey] = labels;
    return datasetData.records
      .map((record, index) => {
        const components = record.components ?? {};
        const x = components?.[xKey];
        const y = components?.[yKey];
        if (typeof x !== 'number' || typeof y !== 'number') {
          return null;
        }
        return {
          id: record.source_record_id ?? `row-${datasetData.page}:${index}`,
          x,
          y,
          is_outlier: record.is_outlier,
        };
      })
      .filter((point): point is { id: number | string; x: number; y: number; is_outlier: boolean } => point !== null);
  }, [datasetData, datasetDetail]);

  const renderDataPreview = () => {
    if (!datasetData) {
      return <p className="text-sm text-[var(--color-text-muted)]">No data preview available.</p>;
    }

    if (!datasetData.records.length) {
      return <p className="text-sm text-[var(--color-text-muted)]">Dataset has no stored records.</p>;
    }

    if (!previewColumns.length) {
      return (
        <p className="text-sm text-[var(--color-text-muted)]">
          No columns available for the selected view.
        </p>
      );
    }

    const getPreviewColumnLabel = (column: string): string => {
      if (column === 'source_record_id') {
        return 'Source Record ID';
      }
      if (previewTab === 'components') {
        return column.toUpperCase();
      }
      const normalizedColumn = column
        .replace(/^scaled_/i, '')
        .replace(/_scaled$/i, '');
      return getParameterLabel(normalizedColumn);
    };

    return (
      <div className="space-y-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2 text-xs md:text-sm" style={{ color: 'var(--color-text-muted)' }}>
            <span>
              Page {datasetData.page} of {totalPages}
            </span>
            <span>|</span>
            <span>
              Showing {(datasetData.page - 1) * datasetData.page_size + 1} -
              {Math.min(datasetData.page * datasetData.page_size, datasetData.total_records)} of {datasetData.total_records}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Rows per page
            </label>
            <select
              value={previewPageSize}
              onChange={(event) => {
                setPreviewPageSize(Number(event.target.value));
                setPreviewPage(1);
              }}
              className="px-2 py-1 text-xs md:text-sm focus:outline-none"
              style={fieldStyle}
            >
              {[20, 50, 100, 250, 500].map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPreviewPage((page) => Math.max(1, page - 1))}
              disabled={datasetData.page <= 1}
            >
              Prev
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setPreviewPage((page) => (page < totalPages ? page + 1 : page))
              }
              disabled={datasetData.page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto border border-[var(--color-border)] rounded-md">
          <table className="min-w-full text-sm">
            <thead style={{ backgroundColor: 'var(--color-surface-hover)' }}>
              <tr>
                <th className="px-3 py-2 text-left font-semibold text-[var(--color-text-muted)] whitespace-nowrap">#</th>
                <th className="px-3 py-2 text-left font-semibold text-[var(--color-text-muted)] whitespace-nowrap">Outlier</th>
                {previewColumns.map((column) => (
                  <th key={column} className="px-3 py-2 text-left font-semibold text-[var(--color-text-muted)] whitespace-nowrap">
                    {getPreviewColumnLabel(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {datasetData.records.map((record, index) => {
                const rowIndex = (datasetData.page - 1) * datasetData.page_size + index + 1;
                const valueMap =
                  previewTab === 'scaled'
                    ? record.scaled ?? {}
                    : previewTab === 'components'
                      ? record.components ?? {}
                      : record.data ?? {};

                return (
                  <tr
                    key={record.source_record_id ?? `row-${rowIndex}`}
                    className={index % 2 === 0 ? 'bg-transparent' : 'bg-[var(--color-surface-hover)]/40'}
                  >
                    <td className="px-3 py-2 text-[var(--color-text-muted)]">{rowIndex}</td>
                    <td className="px-3 py-2 text-[var(--color-text)]">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${
                          record.is_outlier
                            ? 'bg-[var(--color-danger, #ef4444)]/15 text-[var(--color-danger, #ef4444)]'
                            : 'bg-[var(--color-success, #22c55e)]/15 text-[var(--color-success, #22c55e)]'
                        }`}
                      >
                        {record.is_outlier ? 'Outlier' : 'Inlier'}
                      </span>
                    </td>
                    {previewColumns.map((column) => {
                      if (column === 'source_record_id' && previewTab !== 'scaled' && previewTab !== 'components') {
                        return (
                          <td key={column} className="px-3 py-2 text-[var(--color-text)]">
                            {record.source_record_id ?? 'N/A'}
                          </td>
                        );
                      }

                      const rawValue = valueMap[column as keyof typeof valueMap];
                      let displayValue: React.ReactNode;

                      if (typeof rawValue === 'number') {
                        displayValue = formatNumber(rawValue as number);
                      } else if (rawValue === null || rawValue === undefined || rawValue === '') {
                        displayValue = 'N/A';
                      } else {
                        displayValue = String(rawValue);
                      }

                      return (
                        <td key={column} className="px-3 py-2 text-[var(--color-text)]">
                          {displayValue}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderStepContent = (): React.ReactNode => {
    switch (currentStep.key) {
      case 'well':
        return (
          <Card>
            <CardHeader>
              <CardTitle>Step 1 - Well & dataset</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-4 items-end">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                    Select well
                  </label>
                  <select
                    value={selectedWellId ?? ''}
                    onChange={(event) => setSelectedWellId(event.target.value ? Number(event.target.value) : null)}
                    className="w-full px-3 py-2 text-sm focus:outline-none"
                    style={fieldStyle}
                    disabled={wellsLoading || (!!wellsError && wells.length === 0)}
                  >
                    <option value="">-- Select well --</option>
                    {wells.map((well) => (
                      <option key={well.id} value={well.id}>
                        {well.well_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                    Dataset name
                  </label>
                  <input
                    type="text"
                    value={datasetName}
                    onChange={(event) => setDatasetName(event.target.value)}
                    className="w-full px-3 py-2 text-sm focus:outline-none"
                    style={fieldStyle}
                    placeholder="Outlier Detection Run"
                    required
                  />
                </div>
                <div>
                  <Button
                    variant="primary"
                    onClick={() => setAppliedWellId(selectedWellId)}
                    disabled={!selectedWellId || wellsLoading || wells.length === 0}
                  >
                    Load well
                  </Button>
                </div>
              </div>
              <div className="space-y-1 text-xs">
                {wellsLoading && (
                  <p style={{ color: 'var(--color-text-muted)' }}>Loading wells...</p>
                )}
                {!wellsLoading && wells.length === 0 && !wellsError && (
                  <p style={{ color: 'var(--color-text-muted)' }}>
                    No wells available. Import well data and retry.
                  </p>
                )}
                {wellsError && (
                  <div style={{ color: 'var(--color-danger)' }} className="flex items-center gap-2">
                    <span>Could not load wells.</span>
                    <Button variant="ghost" size="sm" onClick={() => refetchWells()}>
                      Retry
                    </Button>
                  </div>
                )}
              </div>

              {selectedWellId && (
                <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto] gap-4 items-end">
                  <div>
                    <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Load existing case
                    </label>
                    <select
                      value={selectedCaseDatasetId ?? ''}
                      onChange={(event) =>
                        setSelectedCaseDatasetId(event.target.value ? Number(event.target.value) : null)
                      }
                      className="w-full px-3 py-2 text-sm focus:outline-none"
                      style={fieldStyle}
                      disabled={existingCasesLoading}
                    >
                      <option value="">-- Select clean case --</option>
                      {(existingCases ?? []).map((dataset) => (
                        <option key={dataset.id} value={dataset.id}>
                          {dataset.name || `Dataset #${dataset.id}`}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Button
                      variant="ghost"
                      onClick={handleLoadExistingCase}
                      disabled={!selectedWellId || !selectedCaseDatasetId}
                    >
                      Load case
                    </Button>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                  Description (optional)
                </label>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className="w-full px-3 py-2 text-sm focus:outline-none"
                  rows={3}
                  style={fieldStyle}
                  placeholder="Add notes about the variables, rationale, or target behavior."
                />
              </div>
            </CardContent>
          </Card>
        );
      case 'variables':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Step 2 · Select variables</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {!appliedWellId && (
                    <p className="text-sm text-[var(--color-text-muted)]">Select and load a well to view available columns.</p>
                  )}
                  {appliedWellId && (
                    <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
                      {selectableVariableColumns.map((column) => {
                        const checked = selectedVariables.includes(column);
                        const stats = columnCompleteness[column];
                        return (
                          <label
                            key={column}
                            className="flex items-center justify-between gap-3 px-3 py-2 rounded-md"
                            style={{
                              backgroundColor: checked ? 'rgba(74, 124, 255, 0.12)' : 'transparent',
                              border: `1px solid ${checked ? 'var(--color-primary)' : 'var(--color-border)'}`,
                              color: 'var(--color-text)',
                            }}
                          >
                            <div className="flex-1 min-w-0">
                              <span className="truncate text-sm block">{getParameterLabel(column)}</span>
                              {stats && (
                                <div className="mt-1 space-y-1">
                                  <div className="h-1.5 rounded-full bg-[var(--color-surface-hover)] overflow-hidden">
                                    <div
                                      className="h-full rounded-full"
                                      style={{
                                        width: `${Math.min(100, Math.max(0, stats.percent))}%`,
                                        backgroundColor:
                                          stats.percent >= 80
                                            ? 'var(--color-success, #22c55e)'
                                            : stats.percent >= 50
                                              ? 'var(--color-warning, #f59e0b)'
                                              : 'var(--color-danger, #ef4444)',
                                      }}
                                    />
                                  </div>
                                  <span className="block text-xs text-[var(--color-text-muted)]">
                                    {formatPercent(stats.percent)} complete · {stats.missing} nulls
                                  </span>
                                </div>
                              )}
                            </div>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => handleToggleVariable(column)}
                              style={checkboxStyle}
                            />
                          </label>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle>Variable visualization</CardTitle>
                  <Button
                    variant="primary"
                    disabled={!appliedWellId || selectedVariables.length === 0}
                    onClick={() => {
                      setVisualizationEnabled(true);
                      if (!visualizedVariable && selectedVariables.length > 0) {
                        setVisualizedVariable(selectedVariables[0]);
                      }
                    }}
                  >
                    Visualize
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {!appliedWellId && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    Load a well first to enable variable diagnostics.
                  </p>
                )}
                {appliedWellId && selectedVariables.length === 0 && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    Select at least one variable and then click Visualize.
                  </p>
                )}
                {appliedWellId && selectedVariables.length > 0 && !visualizationEnabled && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    Click Visualize to inspect distribution and box plot charts before running outlier detection.
                  </p>
                )}
                {visualizationEnabled && activeVariableDiagnostics && (
                  <div className="space-y-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                          Variable
                        </span>
                        <select
                          value={activeVariableDiagnostics.variable}
                          onChange={(event) => setVisualizedVariable(event.target.value)}
                          className="px-3 py-2 text-sm focus:outline-none"
                          style={fieldStyle}
                        >
                          {selectedVariables.map((variable) => (
                            <option key={variable} value={variable}>
                              {getParameterLabel(variable)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                        Count: {formatNumber(activeVariableDiagnostics.sampleSize, 0)} rows (all records)
                      </p>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 text-xs">
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Count</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.sampleSize, 0)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Avg</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.mean)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Min</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.min)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Q1</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.q1)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Median</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.median)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Q3</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.q3)}</p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Max</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">{formatNumber(activeVariableDiagnostics.max)}</p>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
                        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                          Distribution
                        </p>
                        <div className="h-96 mt-3">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={activeVariableDistributionData} margin={{ top: 36, right: 36, bottom: 56, left: 52 }}>
                              <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                              <XAxis
                                type="number"
                                dataKey="center"
                                domain={[activeVariableDiagnostics.min, activeVariableDiagnostics.max]}
                                ticks={activeVariableXAxisTicks}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={(value) => formatNumber(value)}
                                label={{
                                  value: getParameterLabel(activeVariableDiagnostics.variable),
                                  position: 'insideBottom',
                                  offset: -24,
                                  fill: chartAxisColor,
                                }}
                              />
                              <YAxis
                                allowDecimals={false}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                label={{
                                  value: 'Frequency',
                                  angle: -90,
                                  position: 'insideLeft',
                                  fill: chartAxisColor,
                                  offset: -10,
                                  dy: 40,
                                }}
                              />
                              <RechartsTooltip
                                contentStyle={tooltipContentStyle}
                                formatter={(value: number | string | undefined) => [formatNumber(Number(value ?? 0), 0), 'Count']}
                                labelFormatter={(label) => `Value: ${formatNumber(Number(label ?? 0))}`}
                              />
                              <Bar dataKey="count" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
                        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                          Density
                        </p>
                        <div className="h-96 mt-3">
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={activeVariableDensityData} margin={{ top: 36, right: 36, bottom: 56, left: 52 }}>
                              <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                              <XAxis
                                type="number"
                                dataKey="center"
                                domain={[activeVariableDiagnostics.min, activeVariableDiagnostics.max]}
                                ticks={activeVariableXAxisTicks}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={(value) => formatNumber(value)}
                                label={{
                                  value: getParameterLabel(activeVariableDiagnostics.variable),
                                  position: 'insideBottom',
                                  offset: -24,
                                  fill: chartAxisColor,
                                }}
                              />
                              <YAxis
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={(value) => `${Number(value).toFixed(0)}%`}
                                label={{
                                  value: 'Density',
                                  angle: -90,
                                  position: 'insideLeft',
                                  fill: chartAxisColor,
                                  offset: -10,
                                  dy: 40,
                                }}
                              />
                              <RechartsTooltip
                                contentStyle={tooltipContentStyle}
                                formatter={(value: number | string | undefined) => [
                                  `${Number(value ?? 0).toFixed(2)}%`,
                                  'Density',
                                ]}
                                labelFormatter={(label) => `Value: ${formatNumber(Number(label ?? 0))}`}
                              />
                              <Area
                                type="monotone"
                                dataKey="density"
                                stroke="var(--color-primary)"
                                fill="var(--color-primary)"
                                fillOpacity={0.28}
                                strokeWidth={2}
                              />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div className="space-y-2 rounded-md border border-[var(--color-border)] p-3">
                        <p className="text-sm font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                          Box and Whiskers
                        </p>
                        <div className="h-96 mt-3">
                          <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart
                              data={activeVariableBoxPoints}
                              margin={{ top: 36, right: 36, bottom: 56, left: 52 }}
                            >
                              <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                              <XAxis
                                type="number"
                                dataKey="x"
                                domain={[activeVariableDiagnostics.min, activeVariableDiagnostics.max]}
                                ticks={activeVariableXAxisTicks}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={(value) => formatNumber(value)}
                                label={{
                                  value: getParameterLabel(activeVariableDiagnostics.variable),
                                  position: 'insideBottom',
                                  offset: -24,
                                  fill: chartAxisColor,
                                }}
                              />
                              <YAxis
                                type="number"
                                dataKey="y"
                                domain={[0.5, 1.5]}
                                ticks={[1]}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={() => ''}
                              />
                              <ReferenceLine
                                segment={[
                                  { x: activeVariableDiagnostics.lowerWhisker, y: 1 },
                                  { x: activeVariableDiagnostics.upperWhisker, y: 1 },
                                ]}
                                stroke="var(--color-primary)"
                                strokeWidth={3}
                              />
                              <ReferenceLine
                                segment={[
                                  { x: activeVariableDiagnostics.lowerWhisker, y: 0.85 },
                                  { x: activeVariableDiagnostics.lowerWhisker, y: 1.15 },
                                ]}
                                stroke="var(--color-primary)"
                                strokeWidth={3}
                              />
                              <ReferenceLine
                                segment={[
                                  { x: activeVariableDiagnostics.upperWhisker, y: 0.85 },
                                  { x: activeVariableDiagnostics.upperWhisker, y: 1.15 },
                                ]}
                                stroke="var(--color-primary)"
                                strokeWidth={3}
                              />
                              <ReferenceArea
                                x1={activeVariableDiagnostics.q1}
                                x2={activeVariableDiagnostics.q3}
                                y1={0.78}
                                y2={1.22}
                                fill="var(--color-primary)"
                                fillOpacity={0.2}
                                stroke="var(--color-primary)"
                                strokeOpacity={0.9}
                              />
                              <ReferenceLine
                                segment={[
                                  { x: activeVariableDiagnostics.median, y: 0.78 },
                                  { x: activeVariableDiagnostics.median, y: 1.22 },
                                ]}
                                stroke="var(--color-primary)"
                                strokeWidth={3}
                              />
                              <Scatter
                                data={activeVariableBoxPoints}
                                fill="var(--color-primary)"
                                line={false}
                              />
                              <RechartsTooltip
                                contentStyle={tooltipContentStyle}
                                formatter={(_value, _name, item) => {
                                  const payload = item.payload as { element: string; x: number };
                                  return [formatNumber(payload.x), payload.element];
                                }}
                                labelFormatter={() => ''}
                              />
                            </ComposedChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                    </div>
                  </div>
                )}
                {visualizationEnabled && !activeVariableDiagnostics && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    The selected variables do not have enough numeric data to build charts.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        );
      case 'scaling':
        return (
          <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Step 3 - Configure scaling</CardTitle>
            </CardHeader>
            <CardContent>
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                  Scaling method
                </label>
                <select
                  value={scalingConfig.method}
                  onChange={(event) => setScalingConfig({ method: event.target.value as ScalingConfig['method'], params: {} })}
                  className="w-full px-3 py-2 text-sm focus:outline-none"
                  style={fieldStyle}
                >
                  {scalingMethods.map((method) => (
                    <option key={method.value} value={method.value}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-wrap items-center gap-2 mt-4">
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleCalculateScalingPreview}
                  disabled={!canCalculateScaling || isScalingCalculating}
                >
                  {isScalingCalculating ? 'Calculating...' : 'Calculate preview'}
                </Button>
                {!canCalculateScaling && (
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    Load a well and select variables to enable the preview.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Scaling preview</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {hasScalingPreview && (
                    <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      Showing records {formatNumber(scalingPageFirst, 0)} - {formatNumber(scalingPageLast, 0)} of{' '}
                      {formatNumber(scalingTotalRows, 0)}
                    </span>
                  )}
                </div>

                {!appliedWellId && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    Load a well in Step 1 to inspect scaled values.
                  </p>
                )}

                {appliedWellId && selectedVariables.length === 0 && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    Select at least one numeric variable in Step 2 to preview scaled results.
                  </p>
                )}

                {scalingPreview.status === 'loading' && (
                  <p className="text-sm text-[var(--color-text-muted)]">Calculating scaled preview...</p>
                )}

                {scalingPreview.status === 'error' && scalingPreview.error && (
                  <p className="text-sm" style={{ color: 'var(--color-danger, #ef4444)' }}>
                    {scalingPreview.error}
                  </p>
                )}

                {hasScalingPreview && (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead>
                        <tr style={{ color: 'var(--color-text-muted)' }}>
                          <th className="px-3 py-2 text-left font-semibold">Row</th>
                          {selectedVariables.map((variable) => (
                            <React.Fragment key={variable}>
                              <th className="px-3 py-2 text-left font-semibold whitespace-nowrap">
                                {getParameterLabel(variable)} (raw)
                              </th>
                              <th className="px-3 py-2 text-left font-semibold whitespace-nowrap">
                                {getParameterLabel(variable)} (scaled)
                              </th>
                            </React.Fragment>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {scalingPreviewRows.map((row) => (
                          <tr key={row.index} className="border-t border-[var(--color-border)]" style={{ color: 'var(--color-text)' }}>
                            <td className="px-3 py-2 font-medium">{row.index}</td>
                            {selectedVariables.map((variable) => (
                              <React.Fragment key={`${row.index}-${variable}`}>
                                <td className="px-3 py-2 text-right">
                                  {row.raw[variable] !== null && row.raw[variable] !== undefined
                                    ? formatNumber(row.raw[variable] as number)
                                    : 'N/A'}
                                </td>
                                <td className="px-3 py-2 text-right">
                                  {row.scaled[variable] !== null && row.scaled[variable] !== undefined
                                    ? formatNumber(row.scaled[variable] as number)
                                    : 'N/A'}
                                </td>
                              </React.Fragment>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="flex flex-wrap items-center justify-between gap-3 mt-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      <div className="flex items-center gap-2">
                        <span>Rows per page</span>
                        <select
                          value={scalingPreviewPageSize}
                          onChange={(event) => {
                            setScalingPreviewPageSize(Number(event.target.value));
                            setScalingPreviewPage(1);
                          }}
                          disabled={!hasScalingPreview}
                          className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]"
                        >
                          {[10, 20, 50, 100].map((size) => (
                            <option key={size} value={size}>
                              {size}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setScalingPreviewPage((page) => Math.max(1, page - 1))}
                          disabled={!hasScalingPreview || scalingPreviewPage <= 1}
                        >
                          Previous
                        </Button>
                        <span>
                          Page {hasScalingPreview ? scalingPreviewPage : 0} of {hasScalingPreview ? scalingTotalPages : 0}
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setScalingPreviewPage((page) =>
                              hasScalingPreview ? Math.min(scalingTotalPages || 1, page + 1) : page,
                            )
                          }
                          disabled={!hasScalingPreview || scalingPreviewPage >= (scalingTotalPages || 1)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                {scalingPreview.status === 'ready' && !hasScalingPreview && (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    No numeric data available for the selected variables in the current sample.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
          </div>
        );
      case 'pca':
        return (
          <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Step 4 - Configure PCA</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium" style={{ color: 'var(--color-text-muted)' }}>
                      Components
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={Number(pcaConfig.n_components ?? '')}
                      onChange={(event) => setPcaConfig((prev) => ({
                        ...prev,
                        n_components: event.target.value ? Number(event.target.value) : undefined,
                      }))}
                      className="w-full px-2 py-1 text-sm focus:outline-none"
                      style={fieldStyle}
                    />
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Leave blank to keep all components. Lower values speed up downstream analysis and simplify visualization.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium" style={{ color: 'var(--color-text-muted)' }}>
                      SVD solver
                    </label>
                    <select
                      value={pcaConfig.svd_solver}
                      onChange={(event) => setPcaConfig((prev) => ({ ...prev, svd_solver: event.target.value as PCAConfig['svd_solver'] }))}
                      className="w-full px-2 py-1 text-sm focus:outline-none"
                      style={fieldStyle}
                    >
                      <option value="auto">Auto</option>
                      <option value="full">Full</option>
                      <option value="arpack">ARPACK</option>
                      <option value="randomized">Randomized</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text)' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(pcaConfig.whiten)}
                      onChange={(event) => setPcaConfig((prev) => ({ ...prev, whiten: event.target.checked }))}
                      style={checkboxStyle}
                    />
                    Apply whitening (scales principal components to unit variance)
                  </label>
                </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleCalculatePcaPreview}
                  disabled={!canCalculatePca || isPcaCalculating}
                >
                  {isPcaCalculating ? 'Calculating...' : 'Calculate preview'}
                </Button>
                {!canCalculatePca && (
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    Load a well and select variables in Step 2 before calculating PCA.
                  </span>
                )}
                {pcaPreview.status === 'ready' && pcaPreview.data && (
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    Using {formatNumber(pcaPreview.data.scores.length, 0)} rows with {pcaPreview.data.componentLabels.length} components.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {pcaPreview.status !== 'idle' && (
          <Card>
            <CardHeader>
              <CardTitle>PCA preview</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                  {pcaPreview.status === 'error' && pcaPreview.error && (
                    <p className="text-sm" style={{ color: 'var(--color-danger, #ef4444)' }}>
                      {pcaPreview.error}
                    </p>
                  )}

                  {pcaPreview.status === 'ready' && pcaPreview.data && (
                    <div className="space-y-4">
                      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-hover)]/20 p-4 space-y-3">
                        <p className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
                          Explained variance by component
                        </p>
                        <div className="h-80 mt-3">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={pcaPreviewVarianceChartData} margin={{ top: 36, right: 36, bottom: 56, left: 52 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                              <XAxis
                                dataKey="component"
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                label={{
                                  value: 'Principal Components',
                                  position: 'insideBottom',
                                  offset: -24,
                                  fill: chartAxisColor,
                                }}
                              />
                              <YAxis
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                tickFormatter={(value) => `${value.toFixed(0)}%`}
                                label={{
                                  value: 'Explained Variance',
                                  angle: -90,
                                  position: 'insideLeft',
                                  fill: chartAxisColor,
                                  offset: -12,
                                  dy: 40,
                                }}
                              />
                              <RechartsTooltip
                                contentStyle={tooltipContentStyle}
                                formatter={(value: number | string | (number | string)[] | undefined) =>
                                  varianceTooltipFormatter(value)
                                }
                                labelFormatter={(label) => varianceLabelFormatter(label)}
                              />
                              <Bar dataKey="percentage" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>

                      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-hover)]/20 p-4 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <p className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
                            Component scatter (PC vs PC)
                          </p>
                          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                            <span>X</span>
                            <select
                              value={String(pcaScatterX)}
                              onChange={(event) => {
                                setPcaScatterX(Number(event.target.value));
                                setPcaScatterPlotted(false);
                              }}
                              className="px-2 py-1 text-xs focus:outline-none"
                              style={fieldStyle}
                            >
                              {pcaPreview.data.componentLabels.map((label, index) => (
                                <option key={`x-${label}`} value={index}>
                                  {label}
                                </option>
                              ))}
                            </select>
                            <span>Y</span>
                            <select
                              value={String(pcaScatterY)}
                              onChange={(event) => {
                                setPcaScatterY(Number(event.target.value));
                                setPcaScatterPlotted(false);
                              }}
                              className="px-2 py-1 text-xs focus:outline-none"
                              style={fieldStyle}
                            >
                              {pcaPreview.data.componentLabels.map((label, index) => (
                                <option key={`y-${label}`} value={index}>
                                  {label}
                                </option>
                              ))}
                            </select>
                            <Button
                              type="button"
                              variant="primary"
                              onClick={() => setPcaScatterPlotted(true)}
                              disabled={pcaPreview.data.componentLabels.length < 2}
                            >
                              Plot
                            </Button>
                          </div>
                        </div>
                        {pcaPreview.data.componentLabels.length < 2 ? (
                          <p className="text-sm text-[var(--color-text-muted)]">
                            At least two components are required to draw a scatter plot.
                          </p>
                        ) : !pcaScatterPlotted ? (
                          <p className="text-sm text-[var(--color-text-muted)]">
                            Click <strong>Plot</strong> to render the component scatter preview.
                          </p>
                        ) : (
                          <div className="w-full min-w-0" style={{ aspectRatio: '2 / 1', pointerEvents: 'none' }}>
                            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                              <ScatterChart margin={{ top: 36, right: 36, bottom: 56, left: 52 }}>
                                <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                                <XAxis
                                  type="number"
                                  dataKey="x"
                                  name={pcaPreview.data.componentLabels[pcaScatterX] ?? 'PC1'}
                                  stroke={chartAxisColor}
                                  tick={{ fill: chartAxisColor }}
                                  label={{
                                    value: pcaPreview.data.componentLabels[pcaScatterX] ?? 'PC1',
                                    position: 'insideBottom',
                                    offset: -24,
                                    fill: chartAxisColor,
                                  }}
                                />
                                <YAxis
                                  type="number"
                                  dataKey="y"
                                  name={pcaPreview.data.componentLabels[pcaScatterY] ?? 'PC2'}
                                  stroke={chartAxisColor}
                                  tick={{ fill: chartAxisColor }}
                                  label={{
                                    value: pcaPreview.data.componentLabels[pcaScatterY] ?? 'PC2',
                                    angle: -90,
                                    position: 'insideLeft',
                                    fill: chartAxisColor,
                                    offset: -10,
                                    dy: 40,
                                  }}
                                />
                                <Scatter
                                  name="Rows"
                                  data={pcaPreviewScatterData}
                                  fill="var(--color-primary)"
                                  opacity={0.75}
                                  isAnimationActive={false}
                                />
                              </ScatterChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
            </CardContent>
          </Card>
          )}
          </div>
        );
      case 'outlier':
        return (
          <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Step 5 - Configure outlier detection</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
                    Outlier method
                  </label>
                  <select
                    value={outlierConfig.method}
                    onChange={(event) => setOutlierConfig((prev) => ({ ...prev, method: event.target.value as OutlierMethod }))}
                    className="w-full px-3 py-2 text-sm focus:outline-none"
                    style={fieldStyle}
                  >
                    {outlierMethods.map((method) => (
                      <option key={method.value} value={method.value}>
                        {method.label}
                      </option>
                    ))}
                  </select>
                </div>

                {outlierConfig.method === 'isolation_forest' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Contamination
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={Number(outlierConfig.params?.contamination ?? 0.05)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, contamination: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Estimators
                      </label>
                      <input
                        type="number"
                        value={Number(outlierConfig.params?.n_estimators ?? 100)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, n_estimators: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                  </div>
                )}

                {outlierConfig.method === 'dbscan' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Epsilon
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={Number(outlierConfig.params?.eps ?? 0.5)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, eps: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Min samples
                      </label>
                      <input
                        type="number"
                        value={Number(outlierConfig.params?.min_samples ?? 5)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, min_samples: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                  </div>
                )}

                {outlierConfig.method === 'local_outlier_factor' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Neighbors
                      </label>
                      <input
                        type="number"
                        value={Number(outlierConfig.params?.n_neighbors ?? 20)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, n_neighbors: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                        Contamination
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={Number(outlierConfig.params?.contamination ?? 0.1)}
                        onChange={(event) => setOutlierConfig((prev) => ({
                          ...prev,
                          params: { ...prev.params, contamination: Number(event.target.value) },
                        }))}
                        className="w-full px-2 py-1 text-sm focus:outline-none"
                        style={fieldStyle}
                      />
                    </div>
                  </div>
                )}

                {outlierConfig.method === 'zscore' && (
                  <div>
                    <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Threshold (sigma)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={Number(outlierConfig.params?.threshold ?? 3)}
                      onChange={(event) => setOutlierConfig((prev) => ({
                        ...prev,
                        params: { ...prev.params, threshold: Number(event.target.value) },
                      }))}
                      className="w-full px-2 py-1 text-sm focus:outline-none"
                      style={fieldStyle}
                    />
                  </div>
                )}

                {outlierConfig.method === 'iqr' && (
                  <div>
                    <label className="block text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>
                      Multiplier
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={Number(outlierConfig.params?.multiplier ?? 1.5)}
                      onChange={(event) => setOutlierConfig((prev) => ({
                        ...prev,
                        params: { ...prev.params, multiplier: Number(event.target.value) },
                      }))}
                      className="w-full px-2 py-1 text-sm focus:outline-none"
                      style={fieldStyle}
                    />
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleCalculateOutlierPreview}
                  disabled={!canCalculateOutlier || isOutlierCalculating}
                >
                  {isOutlierCalculating ? 'Calculating…' : 'Calculate preview'}
                </Button>
                {!canCalculateOutlier && (
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    Load a well and select variables before calculating outlier preview.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

              {outlierPreview.status !== 'idle' && (
              <Card>
                <CardHeader>
                  <CardTitle>Outlier preview</CardTitle>
                </CardHeader>
                <CardContent>
              <div className="space-y-4">

                {outlierPreview.status === 'error' && outlierPreview.error && (
                  <p className="text-sm" style={{ color: 'var(--color-danger, #ef4444)' }}>
                    {outlierPreview.error}
                  </p>
                )}

                {outlierPreview.status === 'ready' && outlierPreview.data && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Total Rows</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">
                          {formatNumber(outlierPreview.data.totalRows, 0)}
                        </p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Outliers</p>
                        <p style={{ color: 'var(--color-danger, #ef4444)' }} className="font-semibold">
                          {formatNumber(outlierPreview.data.outlierCount, 0)}
                        </p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Clean Rows</p>
                        <p style={{ color: 'var(--color-primary)' }} className="font-semibold">
                          {formatNumber(outlierPreview.data.totalRows - outlierPreview.data.outlierCount, 0)}
                        </p>
                      </div>
                      <div className="rounded-md border border-[var(--color-border)] px-3 py-2">
                        <p style={{ color: 'var(--color-text-muted)' }}>Outlier Rate</p>
                        <p style={{ color: 'var(--color-text)' }} className="font-semibold">
                          {formatPercent(
                            outlierPreview.data.totalRows > 0
                              ? (outlierPreview.data.outlierCount / outlierPreview.data.totalRows) * 100
                              : 0,
                          )}
                        </p>
                      </div>
                    </div>

                    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-hover)]/20 p-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
                          PCA outlier scatter (PC vs PC)
                        </p>
                        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                          <span>X</span>
                          <select
                            value={String(outlierScatterX)}
                            onChange={(event) => {
                              setOutlierScatterX(Number(event.target.value));
                              setOutlierScatterPlotted(false);
                            }}
                            className="px-2 py-1 text-xs focus:outline-none"
                            style={fieldStyle}
                            disabled={!outlierPreview.data.componentLabels?.length}
                          >
                            {(outlierPreview.data.componentLabels ?? []).map((label, index) => (
                              <option key={`ox-${label}`} value={index}>
                                {label}
                              </option>
                            ))}
                          </select>
                          <span>Y</span>
                          <select
                            value={String(outlierScatterY)}
                            onChange={(event) => {
                              setOutlierScatterY(Number(event.target.value));
                              setOutlierScatterPlotted(false);
                            }}
                            className="px-2 py-1 text-xs focus:outline-none"
                            style={fieldStyle}
                            disabled={!outlierPreview.data.componentLabels?.length}
                          >
                            {(outlierPreview.data.componentLabels ?? []).map((label, index) => (
                              <option key={`oy-${label}`} value={index}>
                                {label}
                              </option>
                            ))}
                          </select>
                          <Button
                            type="button"
                            variant="primary"
                            onClick={() => setOutlierScatterPlotted(true)}
                            disabled={!outlierPreview.data.componentLabels?.length}
                          >
                            Plot
                          </Button>
                        </div>
                      </div>
                      {!outlierPreview.data.componentLabels || outlierPreview.data.componentLabels.length < 2 ? (
                        <p className="text-sm text-[var(--color-text-muted)]">
                          Enable and calculate PCA in Step 4 to visualize PC scatter in this preview.
                        </p>
                      ) : !outlierScatterPlotted ? (
                        <p className="text-sm text-[var(--color-text-muted)]">
                          Click <strong>Plot</strong> to render the PCA outlier scatter.
                        </p>
                      ) : (
                            <div className="w-full min-w-0" style={{ aspectRatio: '2 / 1', pointerEvents: 'none' }}>
                              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                            <ScatterChart margin={{ top: 36, right: 36, bottom: 56, left: 52 }}>
                              <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                              <XAxis
                                type="number"
                                dataKey="x"
                                name={outlierPreview.data.componentLabels[outlierScatterX] ?? 'PC1'}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                label={{
                                  value: outlierPreview.data.componentLabels[outlierScatterX] ?? 'PC1',
                                  position: 'insideBottom',
                                  offset: -24,
                                  fill: chartAxisColor,
                                }}
                              />
                              <YAxis
                                type="number"
                                dataKey="y"
                                name={outlierPreview.data.componentLabels[outlierScatterY] ?? 'PC2'}
                                stroke={chartAxisColor}
                                tick={{ fill: chartAxisColor }}
                                label={{
                                  value: outlierPreview.data.componentLabels[outlierScatterY] ?? 'PC2',
                                  angle: -90,
                                  position: 'insideLeft',
                                  fill: chartAxisColor,
                                  offset: -10,
                                  dy: 40,
                                }}
                              />
                              <Scatter
                                name="Inliers"
                                data={outlierPreviewScatterData.filter((point) => !point.isOutlier)}
                                fill="var(--color-primary)"
                                opacity={0.75}
                                isAnimationActive={false}
                              />
                              <Scatter
                                name="Outliers"
                                data={outlierPreviewScatterData.filter((point) => point.isOutlier)}
                                fill="var(--color-danger, #ef4444)"
                                opacity={0.9}
                                isAnimationActive={false}
                              />
                            </ScatterChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
                </CardContent>
              </Card>
              )}
          </div>
        );
      case 'review':
        return (
          <Card>
            <CardHeader>
              <CardTitle>Step 6 - Review & run</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div style={{ color: 'var(--color-text)' }}>
                  <p className="font-semibold mb-1">Selection summary</p>
                  <ul className="space-y-1 text-[var(--color-text-muted)]">
                    <li>Well: {selectedWell ? selectedWell.well_name : 'N/A'}</li>
                    <li>Dataset name: {datasetName.trim() || 'N/A'}</li>
                    <li>Description: {description.trim() || 'N/A'}</li>
                    <li>Variables: {selectedVariables.length ? selectedVariables.map((variable) => getParameterLabel(variable)).join(', ') : 'N/A'}</li>
                  </ul>
                </div>
                <div style={{ color: 'var(--color-text)' }}>
                  <p className="font-semibold mb-1">Pipeline configuration</p>
                  <ul className="space-y-1 text-[var(--color-text-muted)]">
                    <li>Scaling: {scalingConfig.method}</li>
                    <li>PCA: {pcaConfig.n_components ?? 'auto'} components</li>
                    <li>Outlier method: {outlierMethods.find((method) => method.value === outlierConfig.method)?.label ?? outlierConfig.method}</li>
                  </ul>
                </div>
              </div>
              <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-hover)]/30 px-4 py-3 text-xs text-[var(--color-text-muted)]">
                Review the configuration and click "Run pipeline" to generate a processed dataset. You can revisit previous steps at any time to correct parameters before executing.
              </div>
            </CardContent>
          </Card>
        );
      default:
        return null;
    }
  };

  const variableDiagnostics = useMemo<VariableDiagnostics[]>(() => {
    if (!datasetData?.records?.length) {
      return [];
    }

    const baseVariables = datasetDetail?.metrics?.variables ?? selectedVariables;
    const uniqueVariables = Array.from(new Set(baseVariables.filter((variable): variable is string => Boolean(variable))));

    return uniqueVariables
      .map((variable) => {
        const entries: ValueEntry[] = datasetData.records.reduce<ValueEntry[]>((acc, record) => {
          const value = record.data?.[variable];
          if (typeof value === 'number' && Number.isFinite(value)) {
            acc.push({ value, isOutlier: Boolean(record.is_outlier) });
          }
          return acc;
        }, []);

        if (entries.length < 2) {
          return null;
        }

        const values = entries.map((entry) => entry.value).sort((a, b) => a - b);
        const sampleSize = values.length;
        const min = values[0];
        const max = values[values.length - 1];
        const boxStats = computeBoxPlotStats(values);
        const mean = values.reduce((sum, value) => sum + value, 0) / sampleSize;
        const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / sampleSize;
        const std = Math.sqrt(variance);
        const histogram = computeHistogramBins(entries);
        const violin = histogram.map((bin) => ({
          center: bin.center,
          positive: bin.density,
          negative: -bin.density,
          label: bin.label,
        }));
        const outlierRatio = entries.filter((entry) => entry.isOutlier).length / sampleSize;

        return {
          variable,
          sampleSize,
          min,
          max,
          q1: boxStats.q1,
          median: boxStats.median,
          q3: boxStats.q3,
          lowerWhisker: boxStats.lowerWhisker,
          upperWhisker: boxStats.upperWhisker,
          mean,
          std,
          outlierRatio,
          outlierCount: entries.filter((entry) => entry.isOutlier).length,
          histogram,
          violin,
        } satisfies VariableDiagnostics;
      })
      .filter((item): item is VariableDiagnostics => Boolean(item));
  }, [datasetData?.records, datasetDetail?.metrics?.variables, selectedVariables]);

  const densityComparisons = useMemo(() => {
    const variablesForDensity = datasetDetail?.metrics?.variables ?? selectedVariables;
    const cleanedRows = densityDatasetData?.records ?? [];
    if (!datasetDetail || variablesForDensity.length === 0 || cleanedRows.length === 0 || sampleRows.length === 0) {
      return [] as Array<{
        variable: string;
        bins: Array<{ center: number; preDensityPct: number; postDensityPct: number }>;
        preCount: number;
        postCount: number;
      }>;
    }

    return variablesForDensity
      .map((variable) => {
        const preValues = sampleRows
          .map((row) => row?.[variable])
          .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
        const postValues = cleanedRows
          .map((row) => row?.data?.[variable])
          .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));

        if (preValues.length < 2 || postValues.length < 2) {
          return null;
        }

        const bins = buildDensityComparisonBins(preValues, postValues, 24).map((bin) => ({
          center: bin.center,
          preDensityPct: bin.preDensity * 100,
          postDensityPct: bin.postDensity * 100,
        }));

        return {
          variable,
          bins,
          preCount: preValues.length,
          postCount: postValues.length,
        };
      })
      .filter(
        (
          item,
        ): item is {
          variable: string;
          bins: Array<{ center: number; preDensityPct: number; postDensityPct: number }>;
          preCount: number;
          postCount: number;
        } => Boolean(item),
      );
  }, [datasetDetail, densityDatasetData?.records, sampleRows, selectedVariables]);

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Outlier Detection"
          subtitle="Configure pipelines to scale data, apply PCA, and remove anomalies"
        />

        <Card>
          <CardHeader>
            <CardTitle>Pipeline configuration</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col md:flex-row gap-3">
              {wizardSteps.map((step, index) => {
                const isActive = index === currentStepIndex;
                const isCompleted = index < currentStepIndex;
                return (
                  <li key={step.key} className="flex-1">
                    <button
                      type="button"
                      onClick={() => handleGoToStep(index)}
                      disabled={index > currentStepIndex}
                      className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                        isActive
                          ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                          : isCompleted
                            ? 'border-[var(--color-success, #22c55e)] text-[var(--color-success, #22c55e)]'
                            : 'border-[var(--color-border)] text-[var(--color-text-muted)]'
                      } ${index > currentStepIndex ? 'cursor-not-allowed opacity-60' : 'hover:border-[var(--color-primary)]'}`}
                    >
                      <div className="text-xs uppercase tracking-wide">Step {index + 1}</div>
                      <div className="text-sm font-semibold">{step.title}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">{step.description}</div>
                    </button>
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {renderStepContent()}

          {currentStep.key !== 'well' && (
            <>
              <div className="flex flex-col md:flex-row md:items-center md:justify-end gap-3">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={handlePrevStep}
                  disabled={isFirstStep || runOutlierDetectionMutation.isPending}
                >
                  Back
                </Button>
                {isLastStep ? (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={handleRunPipeline}
                    disabled={runOutlierDetectionMutation.isPending || !appliedWellId || selectedVariables.length === 0}
                  >
                    {runOutlierDetectionMutation.isPending ? 'Processing...' : 'Run pipeline'}
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={handleNextStep}
                    disabled={runOutlierDetectionMutation.isPending}
                  >
                    Next step
                  </Button>
                )}
              </div>

              {formErrors.length > 0 && (
                <div className="rounded-md border border-[var(--color-danger, #ef4444)] bg-[var(--color-danger, #ef4444)]/10 px-4 py-3 text-sm" style={{ color: 'var(--color-danger, #ef4444)' }}>
                  <ul className="list-disc list-inside space-y-1">
                    {formErrors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        {currentStep.key === 'well' && appliedWellId && (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Dataset details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {!selectedDatasetId && !datasetDetail && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-sm text-[var(--color-text-muted)]">Well Name</p>
                      <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                        {selectedWell ? selectedWell.well_name : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-[var(--color-text-muted)]">Well ID</p>
                      <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                        {selectedWell ? selectedWell.id : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-[var(--color-text-muted)]">Total Rows</p>
                      <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                        {formatNumber(selectedWell?.total_rows ?? null, 0)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-[var(--color-text-muted)]">Total Columns</p>
                      <p className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                        {availableColumns.length
                          ? formatNumber(availableColumns.length, 0)
                          : formatNumber(selectedWell?.total_columns ?? null, 0)}
                      </p>
                    </div>
                  </div>
                )}

                {datasetDetail && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                      <div style={{ color: 'var(--color-text)' }}>
                        <p className="font-semibold mb-1">Summary</p>
                        <ul className="space-y-1 text-[var(--color-text-muted)]">
                          <li>Name: {datasetDetail.name}</li>
                          <li>Status: {datasetDetail.status}</li>
                          <li>Records: {datasetDetail.record_count ?? 'N/A'}</li>
                          <li>Created: {formatDateTime(datasetDetail.created_at)}</li>
                          <li>Updated: {formatDateTime(datasetDetail.updated_at)}</li>
                        </ul>
                      </div>
                      <div style={{ color: 'var(--color-text)' }}>
                        <p className="font-semibold mb-1">Metrics</p>
                        <ul className="space-y-1 text-[var(--color-text-muted)]">
                          <li>Total rows: {formatNumber(datasetDetail.metrics?.total_records ?? null, 0)}</li>
                          <li>Processed rows: {formatNumber(datasetDetail.metrics?.processed_records ?? null, 0)}</li>
                          <li>Outliers removed: {formatNumber(datasetDetail.metrics?.outlier_records ?? null, 0)}</li>
                          <li>Removed (%): {formatNumber(datasetDetail.metrics?.outlier_percentage ?? null)}%</li>
                          <li>
                            Variables: {datasetDetail.metrics?.variables?.length
                              ? datasetDetail.metrics.variables.map((variable) => getParameterLabel(variable)).join(', ')
                              : 'N/A'}
                          </li>
                          {datasetDetail.metrics?.scaled_feature_labels && (
                            <li>
                              Scaled features: {datasetDetail.metrics.scaled_feature_labels.map((variable) => getParameterLabel(variable)).join(', ')}
                            </li>
                          )}
                          {datasetDetail.metrics?.pca_component_labels && datasetDetail.metrics.pca_component_labels.length > 0 && (
                            <li>
                              PCA components: {datasetDetail.metrics.pca_component_labels.join(', ')}
                            </li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {datasetDetail.description && (
                      <div>
                        <p className="font-semibold text-sm" style={{ color: 'var(--color-text)' }}>
                          Description
                        </p>
                        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                          {datasetDetail.description}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {datasetDetail && (
              <Card>
                <CardHeader>
                  <CardTitle>Data preview</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between mb-2">
                    <div />
                    <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text)' }}>
                      <input
                        type="checkbox"
                        checked={includeOutliersPreview}
                        onChange={(event) => setIncludeOutliersPreview(event.target.checked)}
                      />
                      Include outlier rows
                    </label>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      View
                    </span>
                    <Button
                      variant={previewTab === 'records' ? 'primary' : 'ghost'}
                      size="sm"
                      onClick={() => setPreviewTab('records')}
                    >
                      Processed data
                    </Button>
                    <Button
                      variant={previewTab === 'scaled' ? 'primary' : 'ghost'}
                      size="sm"
                      onClick={() => setPreviewTab('scaled')}
                    >
                      Scaled features
                    </Button>
                    <Button
                      variant={previewTab === 'components' ? 'primary' : 'ghost'}
                      size="sm"
                      onClick={() => setPreviewTab('components')}
                      disabled={!hasPcaMetrics}
                    >
                      PCA components
                    </Button>
                  </div>
                  {isDatasetDataLoading ? (
                    <p className="text-sm text-[var(--color-text-muted)]">Loading data...</p>
                  ) : (
                    renderDataPreview()
                  )}
                </CardContent>
              </Card>
            )}

            {datasetDetail && (
              <Card>
                <CardHeader>
                  <CardTitle>Density comparison (pre-clean vs post-clean)</CardTitle>
                </CardHeader>
                <CardContent>
                  {isDensityDatasetLoading ? (
                    <p className="text-sm text-[var(--color-text-muted)]">
                      Loading cleaned rows for density comparison...
                    </p>
                  ) : densityComparisons.length === 0 ? (
                    <p className="text-sm text-[var(--color-text-muted)]">
                      Density charts are available when both raw and cleaned numeric values exist for the selected variables.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {densityComparisons.map((comparison) => (
                        <Card key={comparison.variable}>
                          <CardHeader>
                            <CardTitle>
                              {getParameterLabel(comparison.variable)} · Pre vs Post cleaning
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            <div className="flex items-center justify-center gap-6 text-xs mb-3" style={{ color: 'var(--color-text-muted)' }}>
                              <span className="inline-flex items-center gap-2">
                                <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: '#f59e0b' }} />
                                Pre-clean
                              </span>
                              <span className="inline-flex items-center gap-2">
                                <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: 'var(--color-primary)' }} />
                                Post-clean
                              </span>
                            </div>
                            <div className="h-96 mt-2">
                              <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={comparison.bins} margin={{ top: 28, right: 28, bottom: 56, left: 52 }}>
                                  <CartesianGrid stroke={chartGridColor} strokeDasharray="3 3" />
                                  <XAxis
                                    dataKey="center"
                                    type="number"
                                    stroke={chartAxisColor}
                                    tick={{ fill: chartAxisColor }}
                                    tickFormatter={(value) => formatNumber(Number(value), 2)}
                                    label={{
                                      value: getParameterLabel(comparison.variable),
                                      position: 'insideBottom',
                                      offset: -22,
                                      fill: chartAxisColor,
                                    }}
                                  />
                                  <YAxis
                                    stroke={chartAxisColor}
                                    tick={{ fill: chartAxisColor }}
                                    tickFormatter={(value) => `${Number(value).toFixed(1)}%`}
                                    label={{
                                      value: 'Density',
                                      angle: -90,
                                      position: 'insideLeft',
                                      fill: chartAxisColor,
                                      offset: -10,
                                      dy: 36,
                                    }}
                                  />
                                  <RechartsTooltip
                                    contentStyle={tooltipContentStyle}
                                    formatter={(value: number | string | (number | string)[] | undefined, nameParam) => {
                                      const numeric = Array.isArray(value)
                                        ? Number(value[0] ?? 0)
                                        : Number(value ?? 0);
                                      const label = nameParam === 'preDensityPct' ? 'Pre-clean' : 'Post-clean';
                                      return [`${numeric.toFixed(2)}%`, label];
                                    }}
                                    labelFormatter={(label) => `Value: ${formatNumber(Number(label), 2)}`}
                                  />
                                  <Area
                                    type="monotone"
                                    dataKey="preDensityPct"
                                    stroke="#f59e0b"
                                    fill="#f59e0b"
                                    fillOpacity={0.15}
                                    strokeWidth={2}
                                    name="Pre-clean"
                                  />
                                  <Area
                                    type="monotone"
                                    dataKey="postDensityPct"
                                    stroke="var(--color-primary)"
                                    fill="var(--color-primary)"
                                    fillOpacity={0.2}
                                    strokeWidth={2}
                                    name="Post-clean"
                                  />
                                </ComposedChart>
                              </ResponsiveContainer>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}
        {currentStep.key === 'well' && (
          <>
            <div className="flex flex-col md:flex-row md:items-center md:justify-end gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={handlePrevStep}
                disabled={isFirstStep || runOutlierDetectionMutation.isPending}
              >
                Back
              </Button>
              {isLastStep ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleRunPipeline}
                  disabled={runOutlierDetectionMutation.isPending || !appliedWellId || selectedVariables.length === 0}
                >
                  {runOutlierDetectionMutation.isPending ? 'Processing...' : 'Run pipeline'}
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleNextStep}
                  disabled={runOutlierDetectionMutation.isPending}
                >
                  Next step
                </Button>
              )}
            </div>

            {formErrors.length > 0 && (
              <div className="rounded-md border border-[var(--color-danger, #ef4444)] bg-[var(--color-danger, #ef4444)]/10 px-4 py-3 text-sm" style={{ color: 'var(--color-danger, #ef4444)' }}>
                <ul className="list-disc list-inside space-y-1">
                  {formErrors.map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
};

export default OutlierDetection;





