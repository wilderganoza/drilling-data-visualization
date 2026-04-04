/**
 * Events Summary Component - Statistics of detected events
 */
import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui';

interface EventsSummaryProps {
  summary: {
    total_events: number;
    by_type: {
      [key: string]: number;
    };
  };
}

export const EventsSummary: React.FC<EventsSummaryProps> = ({ summary }) => {
  const eventTypeLabels: Record<string, string> = {
    connections: 'Pipe Connections',
    stuck_pipe: 'Stuck Pipe Events',
    rop_anomalies: 'ROP Anomalies',
    wob_anomalies: 'WOB Anomalies',
  };

  const eventTypeColors: Record<string, string> = {
    connections: 'text-blue-500',
    stuck_pipe: 'text-red-500',
    rop_anomalies: 'text-yellow-500',
    wob_anomalies: 'text-orange-500',
  };

  const eventTypeBgColors: Record<string, string> = {
    connections: 'bg-blue-500',
    stuck_pipe: 'bg-red-500',
    rop_anomalies: 'bg-yellow-500',
    wob_anomalies: 'bg-orange-500',
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Events Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Total Events */}
          <div className="text-center pb-4 border-b border-gray-700">
            <p className="text-4xl font-bold text-blue-500">{summary.total_events}</p>
            <p className="text-sm text-gray-400 mt-1">Total Events Detected</p>
          </div>

          {/* Events by Type */}
          <div className="space-y-3">
            {Object.entries(summary.by_type).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div
                    className={`w-3 h-3 rounded-full ${
                      eventTypeBgColors[type] || 'bg-gray-500'
                    }`}
                  />
                  <span className="text-gray-300">
                    {eventTypeLabels[type] || type}
                  </span>
                </div>
                <span className={`font-semibold ${eventTypeColors[type] || 'text-gray-400'}`}>
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
