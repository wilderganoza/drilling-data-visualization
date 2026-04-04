// Importar hooks de React para manejo de estado y efectos
import { useState, useCallback, useRef, useEffect } from 'react';

// Interfaz para dominio del gráfico (rangos X e Y)
interface ChartDomain {
  x: [number, number]; // Rango del eje X
  y: [number, number]; // Rango del eje Y
}

// Interfaz para estado de sincronización de gráficos
interface ChartSyncState {
  zoom: ChartDomain | null; // Estado de zoom actual
  crosshair: { x: number; y: number } | null; // Posición del crosshair
  selection: { start: number; end: number } | null; // Rango de selección
}

// Hook para sincronizar estado entre múltiples gráficos
export const useChartSync = (chartId: string) => {
  // Estado de sincronización inicializado en null
  const [syncState, setSyncState] = useState<ChartSyncState>({
    zoom: null,
    crosshair: null,
    selection: null,
  });

  // Referencia a set de callbacks suscritos
  const subscribersRef = useRef<Set<(state: ChartSyncState) => void>>(new Set());

  // Función para suscribirse a cambios de estado
  const subscribe = useCallback((callback: (state: ChartSyncState) => void) => {
    // Agregar callback al set de suscriptores
    subscribersRef.current.add(callback);
    // Retornar función de limpieza para desuscribirse
    return () => {
      subscribersRef.current.delete(callback);
    };
  }, []);

  // Función para difundir cambios de estado a todos los suscriptores
  const broadcast = useCallback((newState: Partial<ChartSyncState>) => {
    // Combinar estado actual con nuevo estado
    const updatedState = { ...syncState, ...newState };
    // Actualizar estado local
    setSyncState(updatedState);
    // Notificar a todos los suscriptores
    subscribersRef.current.forEach(callback => callback(updatedState));
  }, [syncState]);

  // Función para establecer zoom y difundir cambio
  const setZoom = useCallback((domain: ChartDomain | null) => {
    broadcast({ zoom: domain });
  }, [broadcast]);

  // Función para establecer posición del crosshair y difundir cambio
  const setCrosshair = useCallback((position: { x: number; y: number } | null) => {
    broadcast({ crosshair: position });
  }, [broadcast]);

  // Función para establecer selección y difundir cambio
  const setSelection = useCallback((range: { start: number; end: number } | null) => {
    broadcast({ selection: range });
  }, [broadcast]);

  // Función para resetear toda la sincronización
  const resetSync = useCallback(() => {
    broadcast({ zoom: null, crosshair: null, selection: null });
  }, [broadcast]);

  // Retornar API del hook
  return {
    syncState, // Estado actual de sincronización
    setZoom, // Función para establecer zoom
    setCrosshair, // Función para establecer crosshair
    setSelection, // Función para establecer selección
    resetSync, // Función para resetear sincronización
    subscribe, // Función para suscribirse a cambios
  };
};

// Función para crear contexto de sincronización de gráficos
export const createChartSyncContext = () => {
  // Map de suscriptores por chartId
  const subscribers = new Map<string, Set<(state: ChartSyncState) => void>>();
  // Map de estados por chartId
  const states = new Map<string, ChartSyncState>();

  return {
    // Función para suscribirse a un gráfico específico
    subscribe: (chartId: string, callback: (state: ChartSyncState) => void) => {
      // Si el gráfico no existe, inicializarlo
      if (!subscribers.has(chartId)) {
        subscribers.set(chartId, new Set());
        states.set(chartId, { zoom: null, crosshair: null, selection: null });
      }
      // Agregar callback al set de suscriptores del gráfico
      subscribers.get(chartId)!.add(callback);

      // Retornar función de limpieza
      return () => {
        subscribers.get(chartId)?.delete(callback);
      };
    },

    // Función para difundir cambios a un gráfico específico
    broadcast: (chartId: string, newState: Partial<ChartSyncState>) => {
      // Obtener estado actual o usar estado por defecto
      const currentState = states.get(chartId) || { zoom: null, crosshair: null, selection: null };
      // Combinar con nuevo estado
      const updatedState = { ...currentState, ...newState };
      // Guardar estado actualizado
      states.set(chartId, updatedState);

      // Notificar a todos los suscriptores del gráfico
      subscribers.get(chartId)?.forEach(callback => callback(updatedState));
    },

    // Función para obtener estado de un gráfico
    getState: (chartId: string) => {
      return states.get(chartId) || { zoom: null, crosshair: null, selection: null };
    },
  };
};
