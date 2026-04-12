import React, { useMemo, useState } from 'react';
import { Layout } from '../components/layout';
import { Card, CardHeader, CardTitle, CardContent, PageHeader, Button, ConfirmDialog } from '../components/ui';
import { useAppStore } from '../store/appStore';
import {
  useAllOutlierDatasets,
  useDeleteOutlierDatasetById,
} from '../hooks/useOutlierDetection';
import { useWells } from '../hooks/useWells';

export const Cases: React.FC = () => {
  const { addToast } = useAppStore();
  const { data: datasets, isLoading } = useAllOutlierDatasets();
  const { data: wellsData } = useWells(0, 1000);
  const deleteMutation = useDeleteOutlierDatasetById();
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);

  const wellNameById = useMemo(() => {
    const map = new Map<number, string>();
    wellsData?.wells.forEach((w) => map.set(w.id, w.well_name));
    return map;
  }, [wellsData]);

  const handleDelete = (datasetId: number, name: string) => {
    setDeleteTarget({ id: datasetId, name });
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => addToast('Case deleted', 'success'),
      onError: (err: any) => {
        const detail = err?.response?.data?.detail;
        addToast(typeof detail === 'string' ? detail : 'Error deleting case', 'error');
      },
    });
    setDeleteTarget(null);
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const rows = datasets ?? [];

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader
          title="Cases"
          subtitle="Manage saved outlier detection cases across all wells"
        />

        <Card>
          <CardHeader>
            <CardTitle>Cases ({rows.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p style={{ color: 'var(--color-text-muted)' }}>Loading cases...</p>
            ) : rows.length === 0 ? (
              <p style={{ color: 'var(--color-text-muted)' }}>No cases saved yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Name</th>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Well</th>
                      <th className="text-center py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Status</th>
                      <th className="text-right py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Records</th>
                      <th className="text-right py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Outliers</th>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Created</th>
                      <th className="text-right py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((ds) => {
                      const wellName = wellNameById.get(ds.well_id) ?? `Well ${ds.well_id}`;
                      const outliers = ds.metrics?.outlier_records ?? 0;
                      const pct = ds.metrics?.outlier_percentage;
                      return (
                        <tr
                          key={ds.id}
                          className="transition-colors"
                          style={{ borderBottom: '1px solid var(--color-border)' }}
                          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--color-surface-hover)')}
                          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                        >
                          <td className="py-3 px-4 font-medium" style={{ color: 'var(--color-text)' }}>{ds.name}</td>
                          <td className="py-3 px-4" style={{ color: 'var(--color-text)' }}>{wellName}</td>
                          <td className="py-3 px-4 text-center">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                              ds.status === 'completed'
                                ? 'bg-green-900/30 text-green-400'
                                : ds.status === 'failed'
                                ? 'bg-red-900/30 text-red-400'
                                : 'bg-gray-800 text-gray-400'
                            }`}>
                              {ds.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right" style={{ color: 'var(--color-text)' }}>
                            {ds.record_count ?? '-'}
                          </td>
                          <td className="py-3 px-4 text-right" style={{ color: 'var(--color-text)' }}>
                            {outliers}
                            {typeof pct === 'number' ? ` (${pct.toFixed(1)}%)` : ''}
                          </td>
                          <td className="py-3 px-4" style={{ color: 'var(--color-text-muted)' }}>
                            {formatDate(ds.created_at)}
                          </td>
                          <td className="py-3 px-4 text-right">
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => handleDelete(ds.id, ds.name)}
                              disabled={deleteMutation.isPending}
                            >
                              Delete
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete case"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </Layout>
  );
};
