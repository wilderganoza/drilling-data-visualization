// Importar cliente de API
import { apiClient } from '../client';

// Interfaz para datos de un pozo individual
export interface Well {
  id: number; // ID único del pozo
  well_name: string; // Nombre del pozo
  filename?: string | null; // Nombre del archivo importado (opcional)
  total_rows?: number | null; // Total de filas importadas (opcional)
  total_columns?: number | null; // Total de columnas importadas (opcional)
  date_imported?: string | null; // Fecha de importación (opcional)
}

// Interfaz para respuesta de lista de pozos
export interface WellsListResponse {
  total: number; // Total de pozos en la base de datos
  wells: Well[]; // Array de pozos
  message?: string; // Mensaje opcional
}

// Función para obtener lista de todos los pozos
export const getWells = async (
  skip: number = 0, // Número de registros a saltar (paginación)
  limit: number = 100, // Límite de registros a retornar
  search?: string // Término de búsqueda opcional
): Promise<WellsListResponse> => {
  // Construir parámetros de query
  const params: any = { skip, limit };
  // Agregar término de búsqueda si existe
  if (search) {
    params.search = search;
  }
  // Hacer petición GET al endpoint /wells
  const response = await apiClient.get<WellsListResponse>('/wells', { params });
  // Retornar datos de la respuesta
  return response.data;
};

// Función para obtener detalles de un pozo específico
export const getWell = async (wellId: number): Promise<Well> => {
  // Hacer petición GET al endpoint /wells/:wellId
  const response = await apiClient.get<Well>(`/wells/${wellId}`);
  // Retornar datos de la respuesta
  return response.data;
};
