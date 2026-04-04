/**
 * Data Quality Report Component
 */
import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui';
import { getParameterLabel, getAllParameterNames } from '../../constants/parameterLabels';

interface QualityReportProps {
  report: {
    well_id: number;
    total_records: number;
    columns_analyzed: number;
    missing_values: {
      [key: string]: number;
    };
    outliers_detected: {
      [key: string]: number;
    };
    data_ranges: {
      [key: string]: {
        min: number;
        max: number;
        mean: number;
        std: number;
        p25?: number;
        p50?: number;
        p75?: number;
        null_pct?: number;
      };
    };
    quality_score: number;
  };
}

export const QualityReport: React.FC<QualityReportProps> = ({ report }) => {
  const getQualityColor = (score: number) => {
    if (score >= 90) return 'text-green-500';
    if (score >= 70) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getQualityLabel = (score: number) => {
    if (score >= 90) return 'Excellent';
    if (score >= 70) return 'Good';
    if (score >= 50) return 'Fair';
    return 'Poor';
  };

  // Get ALL columns from parameterLabels
  const allParameters = getAllParameterNames();
  
  // Calculate completeness percentage for ALL parameters
  // If a column is NOT in missing_values, it means there's no data for it (0% complete)
  // If a column IS in missing_values, calculate: (total - missing) / total * 100
  const completeColumns = allParameters.map((column) => {
    const hasData = column in report.missing_values;
    const missing = hasData ? report.missing_values[column] : report.total_records;
    const completeness = hasData 
      ? ((report.total_records - report.missing_values[column]) / report.total_records) * 100
      : 0;
    
    return {
      column,
      missing,
      completeness
    };
  }).sort((a, b) => b.completeness - a.completeness);

  return (
    <div className="space-y-6">
      {/* Quality Score Card */}
      <Card>
        <CardHeader>
          <CardTitle>Data Quality Score</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center">
            <div className={`text-6xl font-bold ${getQualityColor(report.quality_score)}`}>
              {report.quality_score.toFixed(1)}
            </div>
            <p className="text-xl text-gray-400 mt-2">
              {getQualityLabel(report.quality_score)}
            </p>
            <div className="mt-4 w-full bg-gray-700 rounded-full h-4">
              <div
                className={`h-4 rounded-full transition-all ${
                  report.quality_score >= 90
                    ? 'bg-green-500'
                    : report.quality_score >= 70
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${report.quality_score}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-3xl font-bold text-blue-500">
                {report.total_records.toLocaleString()}
              </p>
              <p className="text-sm text-gray-400 mt-2">Total Records</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-3xl font-bold text-purple-500">{report.columns_analyzed}</p>
              <p className="text-sm text-gray-400 mt-2">Columns Analyzed</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-3xl font-bold text-orange-500">
                {Object.keys(report.data_ranges).length}
              </p>
              <p className="text-sm text-gray-400 mt-2">Parameters Tracked</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Column Completeness */}
      <Card>
        <CardHeader>
          <CardTitle>Column Completeness</CardTitle>
        </CardHeader>
        <CardContent>
          {completeColumns.length === 0 ? (
            <p className="text-gray-400 text-center py-4">No data available</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
              {completeColumns.map(({ column, completeness }) => (
                <div key={column}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-300 truncate max-w-[200px]">
                      {getParameterLabel(column)}
                    </span>
                    <span className="text-sm text-green-400">
                      {completeness.toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-green-500 h-2 rounded-full"
                      style={{ width: `${completeness}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data Ranges */}
      <Card>
        <CardHeader>
          <CardTitle>Parameter Ranges</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-2 px-3 text-gray-400">Parameter</th>
                  <th className="text-right py-2 px-3 text-gray-400">Null %</th>
                  <th className="text-right py-2 px-3 text-gray-400">Min</th>
                  <th className="text-right py-2 px-3 text-gray-400">P25</th>
                  <th className="text-right py-2 px-3 text-gray-400">P50</th>
                  <th className="text-right py-2 px-3 text-gray-400">P75</th>
                  <th className="text-right py-2 px-3 text-gray-400">Max</th>
                  <th className="text-right py-2 px-3 text-gray-400">Mean</th>
                  <th className="text-right py-2 px-3 text-gray-400">Std Dev</th>
                </tr>
              </thead>
              <tbody>
                {allParameters.map((param) => {
                  const range = report.data_ranges[param];
                  if (!range) {
                    return (
                      <tr key={param} className="border-b border-gray-800">
                        <td className="py-2 px-3 text-gray-300 truncate max-w-[150px]">
                          {getParameterLabel(param)}
                        </td>
                        <td className="text-right py-2 px-3 text-gray-500" colSpan={8}>
                          No data available
                        </td>
                      </tr>
                    );
                  }
                  return (
                    <tr key={param} className="border-b border-gray-800">
                      <td className="py-2 px-3 text-gray-300 truncate max-w-[150px]">
                        {getParameterLabel(param)}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.null_pct !== undefined ? range.null_pct.toFixed(1) : '0.0'}%
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.min.toFixed(2)}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.p25 !== undefined ? range.p25.toFixed(2) : '-'}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.p50 !== undefined ? range.p50.toFixed(2) : '-'}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.p75 !== undefined ? range.p75.toFixed(2) : '-'}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.max.toFixed(2)}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.mean.toFixed(2)}
                      </td>
                      <td className="text-right py-2 px-3 text-gray-400">
                        {range.std.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
