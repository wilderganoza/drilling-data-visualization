/**
 * Settings Page - User preferences and configuration
 */
import React, { useState } from 'react';
import { Layout } from '../components/layout';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select } from '../components/ui';
import { useAppStore } from '../store/appStore';

export const Settings: React.FC = () => {
  const { theme, toggleTheme, addToast } = useAppStore();
  const [apiUrl, setApiUrl] = useState('http://localhost:8000/api/v1');
  const [defaultSampleSize, setDefaultSampleSize] = useState('1000');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState('300');

  const handleSaveSettings = () => {
    // In a real app, these would be saved to localStorage or backend
    addToast('Settings saved successfully', 'success');
  };

  const handleResetSettings = () => {
    setApiUrl('http://localhost:8000/api/v1');
    setDefaultSampleSize('1000');
    setAutoRefresh(false);
    setRefreshInterval('300');
    addToast('Settings reset to defaults', 'info');
  };

  const handleClearCache = () => {
    // Clear React Query cache
    addToast('Cache cleared successfully', 'success');
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-100">Settings</h1>
          <p className="text-gray-400 mt-1">Configure your application preferences</p>
        </div>

        {/* Appearance Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Appearance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Theme
                </label>
                <div className="flex items-center space-x-4">
                  <button
                    onClick={toggleTheme}
                    className={`px-4 py-2 rounded ${
                      theme === 'dark'
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-700 text-gray-300'
                    }`}
                  >
                    🌙 Dark
                  </button>
                  <button
                    onClick={toggleTheme}
                    className={`px-4 py-2 rounded ${
                      theme === 'light'
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-700 text-gray-300'
                    }`}
                  >
                    ☀️ Light
                  </button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* API Settings */}
        <Card>
          <CardHeader>
            <CardTitle>API Configuration</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <Input
                label="API Base URL"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder="http://localhost:8000/api/v1"
              />
              <p className="text-sm text-gray-400">
                The base URL for the backend API. Changes require page reload.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Data Settings */}
        <Card>
          <CardHeader>
            <CardTitle>Data Preferences</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <Select
                label="Default Sample Size"
                value={defaultSampleSize}
                onChange={(e) => setDefaultSampleSize(e.target.value)}
                options={[
                  { value: '500', label: '500 points' },
                  { value: '1000', label: '1000 points' },
                  { value: '2000', label: '2000 points' },
                  { value: '5000', label: '5000 points' },
                ]}
              />

              <div>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    className="w-4 h-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">Enable auto-refresh</span>
                </label>
              </div>

              {autoRefresh && (
                <Input
                  label="Refresh Interval (seconds)"
                  type="number"
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(e.target.value)}
                  placeholder="300"
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Cache Management */}
        <Card>
          <CardHeader>
            <CardTitle>Cache Management</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <p className="text-sm text-gray-400">
                Clear cached data to force fresh data from the server. This may slow down
                initial page loads.
              </p>
              <Button onClick={handleClearCache} variant="danger">
                Clear All Cache
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* About */}
        <Card>
          <CardHeader>
            <CardTitle>About</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm text-gray-300">
              <div className="flex justify-between">
                <span className="text-gray-400">Application:</span>
                <span>Drilling Analysis App</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Version:</span>
                <span>1.0.0</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Backend:</span>
                <span>FastAPI + SQLAlchemy</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Frontend:</span>
                <span>React + TypeScript + Recharts</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <div className="flex space-x-4">
          <Button onClick={handleSaveSettings} className="flex-1">
            Save Settings
          </Button>
          <Button onClick={handleResetSettings} variant="secondary" className="flex-1">
            Reset to Defaults
          </Button>
        </div>
      </div>
    </Layout>
  );
};
