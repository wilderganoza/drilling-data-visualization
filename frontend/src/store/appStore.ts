// Importar función create de Zustand para crear store
import { create } from 'zustand';
// Importar middlewares de Zustand para devtools y persistencia
import { devtools, persist } from 'zustand/middleware';

// Interfaz para datos de un pozo
export interface Well {
  id: number; // ID único del pozo
  well_name: string; // Nombre del pozo
  filename?: string | null; // Nombre del archivo importado (opcional)
  total_rows?: number | null; // Total de filas importadas (opcional)
  total_columns?: number | null; // Total de columnas importadas (opcional)
  date_imported?: string | null; // Fecha de importación (opcional)
}

// Interfaz para el estado global de la aplicación
export interface AppState {
  // Pozo seleccionado actualmente
  selectedWell: Well | null;
  setSelectedWell: (well: Well | null) => void;

  // Estado de la interfaz de usuario
  sidebarOpen: boolean; // Estado de apertura del sidebar
  toggleSidebar: () => void; // Función para alternar sidebar
  setSidebarOpen: (open: boolean) => void; // Función para establecer estado del sidebar

  // Tema de la aplicación
  theme: 'light' | 'dark'; // Tema actual
  toggleTheme: () => void; // Función para alternar tema

  // Estados de carga
  isLoading: boolean; // Indicador de carga global
  setIsLoading: (loading: boolean) => void; // Función para establecer estado de carga

  // Manejo de errores
  error: string | null; // Mensaje de error actual
  setError: (error: string | null) => void; // Función para establecer error
  clearError: () => void; // Función para limpiar error

  // Filtros de datos
  depthRange: { min: number; max: number } | null; // Rango de profundidad
  setDepthRange: (range: { min: number; max: number } | null) => void; // Función para establecer rango de profundidad

  timeRange: { start: string; end: string } | null; // Rango de tiempo
  setTimeRange: (range: { start: string; end: string } | null) => void; // Función para establecer rango de tiempo

  // Columnas seleccionadas para visualización
  selectedColumns: string[]; // Array de columnas seleccionadas
  setSelectedColumns: (columns: string[]) => void; // Función para establecer columnas

  // Notificaciones toast
  toasts: Array<{
    id: string; // ID único del toast
    message: string; // Mensaje del toast
    type: 'success' | 'error' | 'warning' | 'info'; // Tipo de toast
  }>;
  addToast: (message: string, type: 'success' | 'error' | 'warning' | 'info') => void; // Función para agregar toast
  removeToast: (id: string) => void; // Función para remover toast

  addColumn: (column: string) => void; // Función para agregar columna
  removeColumn: (column: string) => void; // Función para remover columna
}

// Crear y exportar store de Zustand con devtools y persistencia
export const useAppStore = create<AppState>()(
  // Middleware de devtools para debugging
  devtools(
    // Middleware de persistencia para guardar estado en localStorage
    persist(
      (set) => ({
        // Estado inicial: Pozo seleccionado
        selectedWell: null,
        setSelectedWell: (well) => set({ selectedWell: well }),

        // Estado inicial: UI
        sidebarOpen: true,
        toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
        setSidebarOpen: (open) => set({ sidebarOpen: open }),

        // Estado inicial: Tema
        theme: 'dark',
        toggleTheme: () =>
          set((state) => ({
            theme: state.theme === 'light' ? 'dark' : 'light',
          })),

        // Estado inicial: Carga
        isLoading: false,
        setIsLoading: (loading) => set({ isLoading: loading }),

        // Estado inicial: Errores
        error: null,
        setError: (error) => set({ error }),
        clearError: () => set({ error: null }),

        // Estado inicial: Filtros de profundidad
        depthRange: null,
        setDepthRange: (range) => set({ depthRange: range }),

        // Estado inicial: Filtros de tiempo
        timeRange: null,
        setTimeRange: (range) => set({ timeRange: range }),

        // Estado inicial: Columnas seleccionadas
        selectedColumns: [],
        setSelectedColumns: (columns) => set({ selectedColumns: columns }),
        // Agregar columna al array
        addColumn: (column) =>
          set((state) => ({
            selectedColumns: [...state.selectedColumns, column],
          })),
        // Remover columna del array
        removeColumn: (column) =>
          set((state) => ({
            selectedColumns: state.selectedColumns.filter((c) => c !== column),
          })),

        // Estado inicial: Notificaciones toast
        toasts: [],
        // Agregar nuevo toast con ID único
        addToast: (message, type) =>
          set((state) => ({
            toasts: [
              ...state.toasts,
              {
                id: `${Date.now()}-${Math.random()}`,
                message,
                type,
              },
            ],
          })),
        // Remover toast por ID
        removeToast: (id) =>
          set((state) => ({
            toasts: state.toasts.filter((toast) => toast.id !== id),
          })),
      }),
      {
        // Nombre de la clave en localStorage
        name: 'drilling-app-storage',
        // Especificar qué partes del estado persistir
        partialize: (state) => ({
          theme: state.theme,
          sidebarOpen: state.sidebarOpen,
          selectedWell: state.selectedWell,
        }),
      }
    ),
    // Nombre para devtools
    { name: 'DrillingApp' }
  )
);
