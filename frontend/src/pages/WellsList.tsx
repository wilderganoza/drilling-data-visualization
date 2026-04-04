/**
 * Wells List Page - Browse and select wells for analysis
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/layout';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, PageHeader } from '../components/ui';
import { useWells } from '../hooks';
import { useAppStore } from '../store/appStore';

export const WellsList: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: wellsData, isLoading, error } = useWells(page * pageSize, pageSize, search);
  const { setSelectedWell } = useAppStore();

  const handleWellClick = (well: any) => {
    setSelectedWell(well);
    navigate(`/wells/${well.id}`);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader 
          title="Wells" 
          subtitle="Select a well to visualize drilling data" 
        />

        {/* Search and Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center space-x-4">
              <div className="flex-1">
                <Input
                  placeholder="Search wells by name..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <Button onClick={() => setPage(0)}>Search</Button>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <Card>
            <CardContent className="py-12">
              <div className="flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                <p className="ml-4 text-gray-400">Loading wells...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error State */}
        {error && (
          <Card>
            <CardContent className="py-12">
              <div className="text-center">
                <p className="text-red-400 text-lg">Failed to load wells</p>
                <Button className="mt-4" onClick={() => window.location.reload()}>
                  Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Wells Grid */}
        {!isLoading && wellsData && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {wellsData.wells.map((well) => (
                <Card
                  key={well.id}
                  hover
                  className="cursor-pointer"
                  onClick={() => handleWellClick(well)}
                >
                  <CardHeader>
                    <CardTitle>{well.well_name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-400">Well ID:</span>
                        <span className="text-sm text-gray-200">{well.id}</span>
                      </div>
                      {well.total_rows && (
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Records:</span>
                          <span className="text-sm text-gray-200">
                            {well.total_rows.toLocaleString()}
                          </span>
                        </div>
                      )}
                      {well.total_columns && (
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Columns:</span>
                          <span className="text-sm text-gray-200">{well.total_columns}</span>
                        </div>
                      )}
                      {well.filename && (
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">File:</span>
                          <span className="text-sm text-gray-200 truncate max-w-[150px]">
                            {well.filename}
                          </span>
                        </div>
                      )}
                    </div>
                    <Button className="w-full mt-4" size="sm">
                      View Details
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Pagination */}
            <Card>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-400">
                    Showing {page * pageSize + 1} to{' '}
                    {Math.min((page + 1) * pageSize, wellsData.total)} of {wellsData.total} wells
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setPage(Math.max(0, page - 1))}
                      disabled={page === 0}
                    >
                      Previous
                    </Button>
                    <span className="text-sm text-gray-400">
                      Page {page + 1} of {Math.ceil(wellsData.total / pageSize)}
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setPage(page + 1)}
                      disabled={(page + 1) * pageSize >= wellsData.total}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
};
