import React, { useEffect, useMemo, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  PageHeader,
  Button,
  InlineLoader,
  Input,
  SearchableSelect,
} from '../components/ui';
import { useWells } from '../hooks';
import { useExportColumns, useExportXlsx } from '../hooks/useExports';
import { useOutlierDatasets } from '../hooks/useOutlierDetection';
import { ExportCaseType } from '../api/endpoints/exports';
import { useAppStore } from '../store/appStore';

export const Exports: React.FC = () => {
  const { addToast } = useAppStore();

  const [selectedWellId, setSelectedWellId] = useState<number | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<'raw' | number>('raw');
  const [appliedWellId, setAppliedWellId] = useState<number | null>(null);
  const [appliedDatasetId, setAppliedDatasetId] = useState<'raw' | number>('raw');
  const [showColumns, setShowColumns] = useState(false);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [includeAllColumns, setIncludeAllColumns] = useState(true);
  const [columnSearch, setColumnSearch] = useState('');
  const [includeOutliers, setIncludeOutliers] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const exportXlsx = useExportXlsx();
  const { data: wellsData, isLoading: wellsLoading } = useWells();
  const wells = wellsData?.wells ?? [];
  const { data: datasetsData, isLoading: datasetsLoading } = useOutlierDatasets(selectedWellId);

  const appliedCase = typeof appliedDatasetId === 'number' ? ExportCaseType.PROCESSED : ExportCaseType.RAW;
  const appliedProcessedId = typeof appliedDatasetId === 'number' ? appliedDatasetId : null;

  const {
    data: columnsData,
    isLoading: columnsLoading,
    isFetching: columnsFetching,
  } = useExportColumns(
    showColumns ? appliedWellId : null,
    showColumns ? appliedCase : null,
    showColumns && appliedCase === ExportCaseType.PROCESSED ? appliedProcessedId : null,
  );

  const wellOptions = useMemo(
    () => wells.map((w) => ({ value: w.id, label: w.well_name })),
    [wells],
  );

  const datasetOptions = useMemo(() => {
    const opts: Array<{ value: string | number; label: string }> = [
      { value: 'raw', label: 'Raw data (original)' },
    ];
    (datasetsData ?? []).forEach((d) =>
      opts.push({ value: d.id, label: d.name || `Dataset #${d.id}` }),
    );
    return opts;
  }, [datasetsData]);

  const availableColumns = useMemo(() => {
    const cols = columnsData?.columns ?? [];
    if (!columnSearch.trim()) return cols;
    const q = columnSearch.toLowerCase();
    return cols.filter((c) => c.label.toLowerCase().includes(q) || c.key.toLowerCase().includes(q));
  }, [columnsData, columnSearch]);

  const groupedColumns = useMemo(() => {
    const groups: Record<string, typeof availableColumns> = {};
    availableColumns.forEach((col) => {
      const group = col.group ?? 'Columns';
      if (!groups[group]) groups[group] = [];
      groups[group].push(col);
    });
    return groups;
  }, [availableColumns]);

  useEffect(() => {
    if (!columnsData?.columns) return;
    if (includeAllColumns) {
      setSelectedColumns(columnsData.columns.map((c) => c.key));
    }
  }, [columnsData, includeAllColumns]);

  const canContinue = useMemo(() => {
    if (!selectedWellId) return false;
    if (typeof selectedDatasetId === 'number') return true;
    return selectedDatasetId === 'raw';
  }, [selectedWellId, selectedDatasetId]);

  const canDownload = useMemo(() => {
    if (!appliedWellId) return false;
    if (!includeAllColumns && selectedColumns.length === 0) return false;
    return true;
  }, [appliedWellId, includeAllColumns, selectedColumns]);

  const handleContinue = () => {
    if (!canContinue) return;
    setAppliedWellId(selectedWellId);
    setAppliedDatasetId(selectedDatasetId);
    setShowColumns(true);
    setIncludeAllColumns(true);
    setColumnSearch('');
  };

  const toggleColumn = (key: string) => {
    setSelectedColumns((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key],
    );
  };

  const toggleAllColumns = () => {
    if (!columnsData?.columns) return;
    const allKeys = columnsData.columns.map((c) => c.key);
    const allSelected = selectedColumns.length >= allKeys.length;
    setIncludeAllColumns(!allSelected);
    setSelectedColumns(allSelected ? [] : allKeys);
  };

  const handleDownload = async () => {
    if (!canDownload || !appliedWellId) return;
    setIsDownloading(true);
    try {
      const blob = await exportXlsx({
        well_id: appliedWellId,
        case_type: appliedCase,
        processed_dataset_id: appliedCase === ExportCaseType.PROCESSED ? appliedProcessedId ?? undefined : undefined,
        include_all_columns: includeAllColumns,
        columns: includeAllColumns ? undefined : selectedColumns,
        include_outliers: appliedCase === ExportCaseType.PROCESSED ? includeOutliers : undefined,
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const wellName = wells.find((w) => w.id === appliedWellId)?.well_name ?? 'export';
      const safeName = wellName.toLowerCase().replace(/[^a-z0-9]+/gi, '-');
      link.href = url;
      link.download = `${safeName}-${appliedCase}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      addToast('Export downloaded successfully.', 'success');
    } catch {
      addToast('Failed to generate the export. Try again later.', 'error');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Exports"
          subtitle="Download drilling data in XLSX format"
        />

        <Card>
          <CardHeader>
            <CardTitle>Select source</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SearchableSelect
                  label="Well"
                  options={wellOptions}
                  value={selectedWellId}
                  onChange={(v) => {
                    setSelectedWellId(Number(v));
                    setSelectedDatasetId('raw');
                    setShowColumns(false);
                  }}
                  placeholder={wellsLoading ? 'Loading wells...' : 'Select a well'}
                  disabled={wellsLoading}
                />

                {selectedWellId && (
                  <SearchableSelect
                    label="Data source"
                    options={datasetOptions}
                    value={selectedDatasetId}
                    onChange={(v) => {
                      setSelectedDatasetId(v === 'raw' ? 'raw' : Number(v));
                      setShowColumns(false);
                    }}
                    placeholder={datasetsLoading ? 'Loading datasets...' : 'Select data source'}
                    disabled={datasetsLoading}
                  />
                )}
              </div>

              <div className="flex justify-end">
                <Button onClick={handleContinue} disabled={!canContinue}>
                  Continue
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {showColumns && (
          <Card>
            <CardHeader>
              <CardTitle>Select columns</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {(columnsLoading || columnsFetching) && (
                <InlineLoader message="Loading columns..." />
              )}

              {!columnsLoading && columnsData && columnsData.columns.length === 0 && (
                <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                  No columns available for this source.
                </p>
              )}

              {columnsData && columnsData.columns.length > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="w-full max-w-sm">
                      <Input
                        placeholder="Search columns..."
                        value={columnSearch}
                        onChange={(e) => setColumnSearch(e.target.value)}
                      />
                    </div>
                    <div className="flex items-center gap-4">
                      {appliedCase === ExportCaseType.PROCESSED && (
                        <label
                          className="flex items-center gap-2 text-sm cursor-pointer whitespace-nowrap"
                          style={{ color: 'var(--color-text)' }}
                        >
                          <input
                            type="checkbox"
                            checked={includeOutliers}
                            onChange={(e) => setIncludeOutliers(e.target.checked)}
                            style={{ accentColor: 'var(--color-primary)' }}
                          />
                          Include outliers
                        </label>
                      )}
                      <label
                        className="flex items-center gap-2 text-sm cursor-pointer whitespace-nowrap"
                        style={{ color: 'var(--color-text)' }}
                      >
                        <input
                          type="checkbox"
                          checked={includeAllColumns}
                          onChange={toggleAllColumns}
                          style={{ accentColor: 'var(--color-primary)' }}
                        />
                        Select all ({columnsData.columns.length})
                      </label>
                    </div>
                  </div>

                  <div
                    className="grid grid-cols-1 md:grid-cols-2 gap-2 overflow-y-auto pr-2"
                    style={{ maxHeight: '420px' }}
                  >
                    {availableColumns.map((col) => {
                      const checked = includeAllColumns || selectedColumns.includes(col.key);
                      return (
                        <label
                          key={col.key}
                          className="flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-md cursor-pointer"
                          style={{
                            border: '1px solid var(--color-border)',
                            backgroundColor: checked
                              ? 'rgba(74, 124, 255, 0.12)'
                              : 'transparent',
                            color: 'var(--color-text)',
                          }}
                        >
                          <span className="truncate" title={col.label}>
                            {col.label}
                          </span>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              if (includeAllColumns) {
                                setIncludeAllColumns(false);
                                const allKeys = columnsData.columns.map((c) => c.key);
                                setSelectedColumns(allKeys.filter((k) => k !== col.key));
                              } else {
                                toggleColumn(col.key);
                              }
                            }}
                            style={{ accentColor: 'var(--color-primary)' }}
                          />
                        </label>
                      );
                    })}
                  </div>

                  <div className="flex justify-end pt-2">
                    <Button
                      onClick={handleDownload}
                      disabled={!canDownload || isDownloading}
                      isLoading={isDownloading}
                    >
                      {isDownloading ? 'Generating...' : 'Download XLSX'}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
};
