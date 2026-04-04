// Importar hooks de TanStack Query para manejo de estado del servidor
import { useQuery } from '@tanstack/react-query';
// Importar funciones de API para obtener datos de pozos
import { getWells, getWell } from '../api/endpoints/wells';
import type { WellsListResponse } from '../api/endpoints/wells';

// Hook personalizado para obtener lista de pozos con paginación y búsqueda
export const useWells = (skip: number = 0, limit: number = 1000, search?: string) => {
  return useQuery<WellsListResponse>({
    // Clave única para el cache de la query
    queryKey: ['wells', skip, limit, search],
    // Función que ejecuta la petición a la API
    queryFn: () => getWells(skip, limit, search),
    // Tiempo que los datos se consideran frescos (5 minutos)
    staleTime: 5 * 60 * 1000,
  });
};

// Hook personalizado para obtener detalles de un pozo específico
export const useWell = (wellId: number | null) => {
  return useQuery({
    // Clave única para el cache de la query
    queryKey: ['well', wellId],
    // Función que ejecuta la petición a la API
    queryFn: () => {
      // Validar que wellId existe
      if (!wellId) throw new Error('Well ID is required');
      return getWell(wellId);
    },
    // Solo ejecutar la query si wellId no es null
    enabled: wellId !== null,
    // Tiempo que los datos se consideran frescos (10 minutos)
    staleTime: 10 * 60 * 1000,
  });
};

// Hook personalizado para búsqueda de pozos
export const useWellsSearch = (searchTerm: string) => {
  return useQuery({
    // Clave única para el cache de la query de búsqueda
    queryKey: ['wells', 'search', searchTerm],
    // Función que ejecuta la petición a la API (máximo 50 resultados)
    queryFn: () => getWells(0, 50, searchTerm),
    // Solo ejecutar la query si hay término de búsqueda
    enabled: searchTerm.length > 0,
    // Tiempo que los datos se consideran frescos (2 minutos)
    staleTime: 2 * 60 * 1000,
  });
};
