/**
 * Events Timeline Component - Visualize detected drilling events
 */
import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui';

interface DrillingEvent {
  event_type: string;
  start_index: number;
  end_index: number;
  duration_points?: number;
  start_depth?: number;
  end_depth?: number;
  avg_wob?: number;
  avg_rop?: number;
  [key: string]: any;
}

interface EventsTimelineProps {
  events: {
    connections?: DrillingEvent[];
    stuck_pipe?: DrillingEvent[];
    rop_anomalies?: DrillingEvent[];
    wob_anomalies?: DrillingEvent[];
  };
  title?: string;
}

export const EventsTimeline: React.FC<EventsTimelineProps> = ({
  events,
  title = 'Detected Events',
}) => {
  const eventTypeColors: Record<string, string> = {
    connection: 'bg-blue-500',
    stuck_pipe: 'bg-red-500',
    anomaly: 'bg-yellow-500',
  };

  const eventTypeIcons: Record<string, string> = {
    connection: '🔗',
    stuck_pipe: '⚠️',
    anomaly: '📊',
  };

  const allEvents: Array<DrillingEvent & { category: string; param?: string }> = [
    ...(events.connections || []).map((e) => ({ ...e, category: 'connection' })),
    ...(events.stuck_pipe || []).map((e) => ({ ...e, category: 'stuck_pipe' })),
    ...(events.rop_anomalies || []).map((e) => ({ ...e, category: 'anomaly', param: 'ROP' })),
    ...(events.wob_anomalies || []).map((e) => ({ ...e, category: 'anomaly', param: 'WOB' })),
  ].sort((a, b) => (a.start_depth || 0) - (b.start_depth || 0));

  const getEventColor = (category: string) => {
    return eventTypeColors[category] || 'bg-gray-500';
  };

  const getEventIcon = (category: string) => {
    return eventTypeIcons[category] || '📍';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {allEvents.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400">No events detected</p>
          </div>
        ) : (
          <div className="space-y-4">
            {allEvents.map((event, index) => (
              <div key={index} className="flex items-start space-x-4">
                {/* Event Icon */}
                <div
                  className={`flex-shrink-0 w-10 h-10 rounded-full ${getEventColor(
                    event.category
                  )} flex items-center justify-center text-white text-lg`}
                >
                  {getEventIcon(event.category)}
                </div>

                {/* Event Details */}
                <div className="flex-1 bg-gray-700 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-lg font-semibold text-gray-100 capitalize">
                      {event.category === 'anomaly'
                        ? `${event.param} Anomaly`
                        : event.category.replace('_', ' ')}
                    </h4>
                    {event.duration_points && (
                      <span className="text-sm text-gray-400">
                        {event.duration_points} points
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {/* For anomalies */}
                    {event.category === 'anomaly' && event.depth !== undefined && (
                      <div>
                        <span className="text-gray-400">Depth:</span>
                        <span className="ml-2 text-gray-200">
                          {typeof event.depth === 'number' ? event.depth.toFixed(2) : event.depth} ft
                        </span>
                      </div>
                    )}
                    {event.category === 'anomaly' && event.value !== undefined && (
                      <div>
                        <span className="text-gray-400">Value:</span>
                        <span className="ml-2 text-gray-200">
                          {typeof event.value === 'number' ? event.value.toFixed(2) : event.value}
                        </span>
                      </div>
                    )}
                    {event.category === 'anomaly' && event.index !== undefined && (
                      <div>
                        <span className="text-gray-400">Index:</span>
                        <span className="ml-2 text-gray-200">
                          {event.index}
                        </span>
                      </div>
                    )}
                    {event.category === 'anomaly' && event.method && (
                      <div>
                        <span className="text-gray-400">Method:</span>
                        <span className="ml-2 text-gray-200">
                          {event.method}
                        </span>
                      </div>
                    )}
                    
                    {/* For connections and stuck pipe */}
                    {event.category !== 'anomaly' && event.start_depth !== undefined && (
                      <div>
                        <span className="text-gray-400">Start Depth:</span>
                        <span className="ml-2 text-gray-200">
                          {event.start_depth.toFixed(2)} ft
                        </span>
                      </div>
                    )}
                    {event.category !== 'anomaly' && event.end_depth !== undefined && (
                      <div>
                        <span className="text-gray-400">End Depth:</span>
                        <span className="ml-2 text-gray-200">
                          {event.end_depth.toFixed(2)} ft
                        </span>
                      </div>
                    )}
                    {event.avg_wob !== undefined && (
                      <div>
                        <span className="text-gray-400">Avg WOB:</span>
                        <span className="ml-2 text-gray-200">
                          {event.avg_wob.toFixed(2)} klbs
                        </span>
                      </div>
                    )}
                    {event.avg_rop !== undefined && (
                      <div>
                        <span className="text-gray-400">Avg ROP:</span>
                        <span className="ml-2 text-gray-200">
                          {event.avg_rop.toFixed(2)} ft/hr
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
