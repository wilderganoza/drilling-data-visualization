import React, { useState, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui';
import { Button } from '../ui/Button';
import { getParameterLabel } from '../../constants/parameterLabels';
import { downloadDataAsCSV } from '../../utils/downloadUtils';

interface Track {
  id: string;
  name: string;
  parameters: string[];
  scaleType: 'linear' | 'logarithmic';
  minValue?: number;
  maxValue?: number;
  color: string;
}

interface WellLogViewProps {
  data: Array<{ [key: string]: any }>;
  depthKey: string;
  availableParameters: string[];
  height?: number;
}

export const WellLogView: React.FC<WellLogViewProps> = ({
  data,
  depthKey,
  availableParameters,
  height = 600,
}) => {
  const [tracks, setTracks] = useState<Track[]>([
    {
      id: '1',
      name: 'Track 1',
      parameters: [],
      scaleType: 'linear',
      color: '#3B82F6',
    },
  ]);

  const [tooltip, setTooltip] = useState<{
    visible: boolean;
    x: number;
    y: number;
    depth: number;
    param: string;
    value: number;
  } | null>(null);

  const [zoomRange, setZoomRange] = useState<{ min: number; max: number } | null>(null);
  const [dragSelection, setDragSelection] = useState<{ startY: number; currentY: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRefs = useRef<Map<string, SVGSVGElement>>(new Map());
  const trackColors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

  const addTrack = () => {
    const newTrack: Track = {
      id: Date.now().toString(),
      name: `Track ${tracks.length + 1}`,
      parameters: [],
      scaleType: 'linear',
      color: trackColors[tracks.length % trackColors.length],
    };
    setTracks([...tracks, newTrack]);
  };

  const removeTrack = (trackId: string) => {
    if (tracks.length > 1) {
      setTracks(tracks.filter(t => t.id !== trackId));
    }
  };

  const updateTrack = (trackId: string, updates: Partial<Track>) => {
    setTracks(tracks.map(t => (t.id === trackId ? { ...t, ...updates } : t)));
  };

  const addParameterToTrack = (trackId: string, parameter: string) => {
    setTracks(
      tracks.map(t =>
        t.id === trackId && !t.parameters.includes(parameter)
          ? { ...t, parameters: [...t.parameters, parameter] }
          : t
      )
    );
  };

  const removeParameterFromTrack = (trackId: string, parameter: string) => {
    setTracks(
      tracks.map(t =>
        t.id === trackId
          ? { ...t, parameters: t.parameters.filter(p => p !== parameter) }
          : t
      )
    );
  };

  const exportToImage = () => {
    // Get all unique parameters from all tracks
    const allParameters = Array.from(new Set(tracks.flatMap(t => t.parameters)));
    
    // Create columns array with depth key and all parameters
    const columns = [depthKey, ...allParameters];
    
    // Export the data as CSV
    downloadDataAsCSV(data, 'well_log_data', columns);
  };

  const depthValues = data.map(d => d[depthKey]).filter(v => v != null);
  const fullMinDepth = Math.min(...depthValues);
  const fullMaxDepth = Math.max(...depthValues);
  
  const minDepth = zoomRange?.min ?? fullMinDepth;
  const maxDepth = zoomRange?.max ?? fullMaxDepth;
  const depthRange = maxDepth - minDepth;

  const scaleDepth = (depth: number) => {
    return ((depth - minDepth) / depthRange) * (height - 60);
  };

  const handleResetZoom = () => {
    setZoomRange(null);
  };

  const yToDepth = (y: number, svgHeight: number) => {
    const relativeY = y - 30;
    const fraction = relativeY / (svgHeight - 60);
    return minDepth + fraction * depthRange;
  };

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const y = e.clientY - rect.top;
    
    setIsDragging(true);
    setDragSelection({ startY: y, currentY: y });
    setTooltip(null);
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging || !dragSelection) return;
    
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const y = e.clientY - rect.top;
    
    setDragSelection({ ...dragSelection, currentY: y });
  };

  const handleMouseUp = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging || !dragSelection) return;
    
    const svg = e.currentTarget;
    const svgHeight = svg.getBoundingClientRect().height;
    
    const depth1 = yToDepth(dragSelection.startY, svgHeight);
    const depth2 = yToDepth(dragSelection.currentY, svgHeight);
    
    const newMin = Math.max(fullMinDepth, Math.min(depth1, depth2));
    const newMax = Math.min(fullMaxDepth, Math.max(depth1, depth2));
    
    if (Math.abs(newMax - newMin) > 10) {
      setZoomRange({ min: newMin, max: newMax });
    }
    
    setIsDragging(false);
    setDragSelection(null);
  };

  const handleMouseLeave = () => {
    if (isDragging) {
      setIsDragging(false);
      setDragSelection(null);
    }
  };

  const renderTrack = (track: Track, index: number) => {
    const trackWidth = 260; // Increased to match selectbox width
    const trackX = index * (trackWidth + 20);
    const svgHeight = height + 40; // Extra space for labels at bottom

    const trackData = track.parameters.map(param => {
      const values = data.map(d => d[param]).filter(v => v !== null && v !== undefined && !isNaN(v));
      const minVal = track.minValue ?? Math.min(...values);
      const maxVal = track.maxValue ?? Math.max(...values);
      const range = maxVal - minVal;

      const scaleValue = (value: number) => {
        if (track.scaleType === 'logarithmic') {
          const logMin = Math.log10(minVal || 0.1);
          const logMax = Math.log10(maxVal || 1);
          const logValue = Math.log10(value || 0.1);
          return ((logValue - logMin) / (logMax - logMin)) * (trackWidth - 20) + 10;
        }
        return ((value - minVal) / range) * (trackWidth - 20) + 10;
      };

      return { param, values, minVal, maxVal, scaleValue };
    });

    return (
      <div key={track.id} style={{ width: trackWidth }}>
        <svg 
          width={trackWidth} 
          height={svgHeight} 
          className="rounded"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          onDoubleClick={handleResetZoom}
          style={{ 
            cursor: isDragging ? 'ns-resize' : 'crosshair',
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)'
          }}
        >
          <rect width={trackWidth} height={svgHeight} fill="var(--color-surface)" />
          
          {/* Selection rectangle during drag */}
          {isDragging && dragSelection && (
            <rect
              x="0"
              y={Math.min(dragSelection.startY, dragSelection.currentY)}
              width={trackWidth}
              height={Math.abs(dragSelection.currentY - dragSelection.startY)}
              fill="rgba(59, 130, 246, 0.2)"
              stroke="#3B82F6"
              strokeWidth="2"
              strokeDasharray="5,5"
            />
          )}

          {/* Depth grid lines and labels */}
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map(fraction => {
            const y = 30 + fraction * (height - 60);
            const depth = minDepth + fraction * depthRange;
            return (
              <g key={fraction}>
                <line
                  x1="10"
                  y1={y}
                  x2={trackWidth - 10}
                  y2={y}
                  stroke="var(--color-border)"
                  strokeWidth={fraction === 0 || fraction === 1 ? "2" : "1"}
                  strokeDasharray={fraction === 0 || fraction === 1 ? "0" : "3 3"}
                />
                <text
                  x={trackWidth - 12}
                  y={y + 12}
                  fill="var(--color-text-muted)"
                  fontSize="10"
                  textAnchor="end"
                >
                  {depth.toFixed(0)} ft
                </text>
              </g>
            );
          })}

          {/* Vertical grid lines for value scale */}
          <line x1="10" y1="30" x2="10" y2={height - 30} stroke="var(--color-border)" strokeWidth="1" />
          <line x1={trackWidth - 10} y1="30" x2={trackWidth - 10} y2={height - 30} stroke="var(--color-border)" strokeWidth="1" />

          {/* Clip path to prevent overflow */}
          <defs>
            <clipPath id={`clip-${track.id}`}>
              <rect x="0" y="30" width={trackWidth} height={height - 60} />
            </clipPath>
          </defs>

          {/* Parameter curves */}
          {trackData.map(({ param, scaleValue, minVal, maxVal }, paramIndex) => {
            const color = trackColors[paramIndex % trackColors.length];
            const points = data
              .filter(d => {
                const depth = d[depthKey];
                return depth != null && depth >= minDepth && depth <= maxDepth;
              })
              .map((d) => {
                const depth = d[depthKey];
                const value = d[param];
                if (depth === null || depth === undefined || value === null || value === undefined || isNaN(value)) return null;
                return {
                  x: scaleValue(value),
                  y: 30 + scaleDepth(depth),
                  depth,
                  value,
                };
              })
              .filter(p => p !== null)
              .sort((a, b) => a!.depth - b!.depth); // Sort by depth to avoid erratic lines

            const pathData = points
              .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p!.x} ${p!.y}`)
              .join(' ');

            return (
              <g key={param} clipPath={`url(#clip-${track.id})`}>
                <path 
                  d={pathData} 
                  stroke={color} 
                  strokeWidth="2" 
                  fill="none"
                  style={{ cursor: 'crosshair' }}
                />
                
                {/* Invisible wider path for easier mouse interaction */}
                <path 
                  d={pathData} 
                  stroke="transparent" 
                  strokeWidth="10" 
                  fill="none"
                  style={{ cursor: 'crosshair' }}
                  onMouseMove={(e) => {
                    const svg = e.currentTarget.ownerSVGElement;
                    if (!svg) return;
                    const pt = svg.createSVGPoint();
                    pt.x = e.clientX;
                    pt.y = e.clientY;
                    const svgP = pt.matrixTransform(svg.getScreenCTM()?.inverse());
                    
                    // Find closest point
                    let closestPoint = points[0];
                    let minDist = Infinity;
                    points.forEach(p => {
                      if (!p) return;
                      const dist = Math.sqrt(Math.pow(p.x - svgP.x, 2) + Math.pow(p.y - svgP.y, 2));
                      if (dist < minDist) {
                        minDist = dist;
                        closestPoint = p;
                      }
                    });
                    
                    if (closestPoint && minDist < 20) {
                      setTooltip({
                        visible: true,
                        x: e.clientX,
                        y: e.clientY,
                        depth: closestPoint.depth,
                        param,
                        value: closestPoint.value,
                      });
                    }
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
                
              </g>
            );
          })}

          {/* Min/Max labels at top */}
          {trackData.map(({ minVal, maxVal, param }, paramIndex) => {
            const color = trackColors[paramIndex % trackColors.length];
            const yPos = 20 + (paramIndex * 14);
            return (
              <g key={`labels-${paramIndex}`}>
                {/* Min label with background */}
                <rect
                  x="8"
                  y={yPos - 10}
                  width="45"
                  height="13"
                  fill="var(--color-surface-hover)"
                  stroke="var(--color-border)"
                  strokeWidth="0.5"
                  rx="2"
                />
                <text
                  x="12"
                  y={yPos}
                  fill="var(--color-text)"
                  fontSize="11"
                  fontWeight="bold"
                >
                  {minVal.toFixed(1)}
                </text>
                
                {/* Max label with background */}
                <rect
                  x={trackWidth - 53}
                  y={yPos - 10}
                  width="45"
                  height="13"
                  fill="var(--color-surface-hover)"
                  stroke="var(--color-border)"
                  strokeWidth="0.5"
                  rx="2"
                />
                <text
                  x={trackWidth - 12}
                  y={yPos}
                  fill="var(--color-text)"
                  fontSize="11"
                  fontWeight="bold"
                  textAnchor="end"
                >
                  {maxVal.toFixed(1)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Well Log View</CardTitle>
            <p className="text-sm mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Click and drag vertically to zoom • Double-click to reset
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={handleResetZoom} disabled={!zoomRange}>
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Reset Zoom
            </Button>
            <Button variant="secondary" size="sm" onClick={addTrack}>
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Track
            </Button>
            <Button variant="secondary" size="sm" onClick={exportToImage}>
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Controls section */}
          <div className="flex gap-5 p-4 pb-0">
            {tracks.map((track) => (
              <div key={`controls-${track.id}`} style={{ width: 260 }}>
                <div className="rounded-lg p-3" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      type="text"
                      value={track.name}
                      onChange={e => updateTrack(track.id, { name: e.target.value })}
                      className="px-3 py-2 rounded text-sm flex-1 font-sans"
                      style={{ backgroundColor: 'var(--color-surface-hover)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                    />
                    <button
                      onClick={() => removeTrack(track.id)}
                      disabled={tracks.length === 1}
                      className="flex-shrink-0 p-2 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      style={{ color: 'var(--color-text-muted)' }}
                      onMouseEnter={(e) => !e.currentTarget.disabled && (e.currentTarget.style.backgroundColor = 'var(--color-surface-hover)')}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>

                  <select
                    className="px-3 py-2 rounded text-sm w-full mb-2 font-sans appearance-none cursor-pointer"
                    style={{ 
                      backgroundColor: 'var(--color-surface)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                      backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'%239CA3AF\'%3E%3Cpath stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'2\' d=\'M19 9l-7 7-7-7\'/%3E%3C/svg%3E")', 
                      backgroundRepeat: 'no-repeat', 
                      backgroundPosition: 'right 0.5rem center', 
                      backgroundSize: '1.5em 1.5em', 
                      paddingRight: '2.5rem' 
                    }}
                    onChange={e => {
                      if (e.target.value) {
                        addParameterToTrack(track.id, e.target.value);
                        e.target.value = '';
                      }
                    }}
                  >
                    <option value="">Add parameter...</option>
                    {availableParameters
                      .filter(p => !track.parameters.includes(p))
                      .map(p => (
                        <option key={p} value={p}>
                          {getParameterLabel(p)}
                        </option>
                      ))}
                  </select>

                  <div className="space-y-1 mb-2">
                    {track.parameters.map(param => (
                      <div key={param} className="flex items-center justify-between px-3 py-2 rounded" style={{ backgroundColor: 'var(--color-surface-hover)', border: '1px solid var(--color-border)' }}>
                        <span className="text-sm truncate flex-1 font-sans" style={{ color: 'var(--color-text)' }}>{getParameterLabel(param)}</span>
                        <button
                          onClick={() => removeParameterFromTrack(track.id, param)}
                          className="text-red-400 hover:text-red-300 ml-2 flex-shrink-0 w-5 h-5 flex items-center justify-center"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>

                  <select
                    value={track.scaleType}
                    onChange={e => updateTrack(track.id, { scaleType: e.target.value as 'linear' | 'logarithmic' })}
                    className="px-3 py-2 rounded text-sm w-full font-sans appearance-none cursor-pointer"
                    style={{ 
                      backgroundColor: 'var(--color-surface)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                      backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 24 24\' stroke=\'%239CA3AF\'%3E%3Cpath stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'2\' d=\'M19 9l-7 7-7-7\'/%3E%3C/svg%3E")', 
                      backgroundRepeat: 'no-repeat', 
                      backgroundPosition: 'right 0.5rem center', 
                      backgroundSize: '1.5em 1.5em', 
                      paddingRight: '2.5rem' 
                    }}
                  >
                    <option value="linear">Linear</option>
                    <option value="logarithmic">Logarithmic</option>
                  </select>
                </div>
              </div>
            ))}
          </div>

          {/* SVG section - all aligned */}
          <div
            ref={containerRef}
            className="overflow-x-auto overflow-y-hidden"
            style={{ maxHeight: height + 100 }}
          >
            <div className="flex gap-5 p-4 pt-2">
              {tracks.map((track, index) => renderTrack(track, index))}
            </div>
          </div>

          {/* Tooltip */}
          {tooltip && (
            <div
              className="fixed rounded-lg p-3 shadow-xl z-50 pointer-events-none"
              style={{
                backgroundColor: 'var(--color-tooltip-bg)',
                border: '1px solid var(--color-tooltip-border)',
                left: tooltip.x + 10,
                top: tooltip.y + 10,
              }}
            >
              <div className="text-xs space-y-1">
                <p className="font-semibold text-blue-400">
                  {getParameterLabel(tooltip.param)}
                </p>
                <p className="text-gray-300">
                  <span className="text-gray-500">Depth:</span> {tooltip.depth.toFixed(2)} ft
                </p>
                <p className="text-gray-300">
                  <span className="text-gray-500">Value:</span> {tooltip.value.toFixed(3)}
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
