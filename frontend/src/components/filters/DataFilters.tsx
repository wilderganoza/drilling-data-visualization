/**
 * Advanced Data Filters Component
 */
import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input } from '../ui';

export interface FilterConfig {
  minDepth?: number;
  maxDepth?: number;
  minTime?: string;
  maxTime?: string;
  selectedColumns?: string[];
}

interface DataFiltersProps {
  onApplyFilters: (filters: FilterConfig) => void;
  availableColumns?: string[];
  initialFilters?: FilterConfig;
}

export const DataFilters: React.FC<DataFiltersProps> = ({
  onApplyFilters,
  availableColumns = [],
  initialFilters = {},
}) => {
  const [minDepth, setMinDepth] = useState(initialFilters.minDepth?.toString() || '');
  const [maxDepth, setMaxDepth] = useState(initialFilters.maxDepth?.toString() || '');
  const [minTime, setMinTime] = useState(initialFilters.minTime || '');
  const [maxTime, setMaxTime] = useState(initialFilters.maxTime || '');
  const [selectedColumns, setSelectedColumns] = useState<string[]>(
    initialFilters.selectedColumns || []
  );

  const handleApply = () => {
    const filters: FilterConfig = {};
    
    if (minDepth) filters.minDepth = parseFloat(minDepth);
    if (maxDepth) filters.maxDepth = parseFloat(maxDepth);
    if (minTime) filters.minTime = minTime;
    if (maxTime) filters.maxTime = maxTime;
    if (selectedColumns.length > 0) filters.selectedColumns = selectedColumns;

    onApplyFilters(filters);
  };

  const handleReset = () => {
    setMinDepth('');
    setMaxDepth('');
    setMinTime('');
    setMaxTime('');
    setSelectedColumns([]);
    onApplyFilters({});
  };

  const toggleColumn = (column: string) => {
    if (selectedColumns.includes(column)) {
      setSelectedColumns(selectedColumns.filter((c) => c !== column));
    } else {
      setSelectedColumns([...selectedColumns, column]);
    }
  };

  const commonColumns = [
    'bit_depth_feet',
    'rate_of_penetration_ft_per_hr',
    'weight_on_bit_klbs',
    'rotary_rpm',
    'standpipe_pressure_psi',
    'hook_load_klbs',
    'flow_in_gpm',
    'torque_ft_klbs',
  ];

  const displayColumns = availableColumns.length > 0 ? availableColumns : commonColumns;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Data Filters</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Depth Range */}
          <div>
            <h4 className="text-sm font-semibold text-gray-300 mb-3">Depth Range (ft)</h4>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Min Depth"
                type="number"
                placeholder="0"
                value={minDepth}
                onChange={(e) => setMinDepth(e.target.value)}
              />
              <Input
                label="Max Depth"
                type="number"
                placeholder="10000"
                value={maxDepth}
                onChange={(e) => setMaxDepth(e.target.value)}
              />
            </div>
          </div>

          {/* Time Range */}
          <div>
            <h4 className="text-sm font-semibold text-gray-300 mb-3">Time Range</h4>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Start Time"
                type="datetime-local"
                value={minTime}
                onChange={(e) => setMinTime(e.target.value)}
              />
              <Input
                label="End Time"
                type="datetime-local"
                value={maxTime}
                onChange={(e) => setMaxTime(e.target.value)}
              />
            </div>
          </div>

          {/* Column Selection */}
          <div>
            <h4 className="text-sm font-semibold text-gray-300 mb-3">
              Select Columns ({selectedColumns.length} selected)
            </h4>
            <div className="max-h-64 overflow-y-auto space-y-2">
              {displayColumns.map((column) => (
                <label
                  key={column}
                  className="flex items-center space-x-2 p-2 hover:bg-gray-700 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedColumns.includes(column)}
                    onChange={() => toggleColumn(column)}
                    className="w-4 h-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">{column}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex space-x-3 pt-4 border-t border-gray-700">
            <Button onClick={handleApply} className="flex-1">
              Apply Filters
            </Button>
            <Button onClick={handleReset} variant="secondary" className="flex-1">
              Reset
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
