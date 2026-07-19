import React from 'react';

export interface ErrorStateProps {
  // Error de la query (axios/React Query); se extrae el detail si existe
  error?: unknown;
  // Mensaje a mostrar si no se puede derivar uno del error
  message?: string;
  className?: string;
}

// Extrae un mensaje legible de un error de axios/React Query
export function getErrorMessage(error: unknown, fallback = 'Something went wrong while loading data.'): string {
  if (error && typeof error === 'object') {
    const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: unknown };
    const detail = maybeAxios.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (typeof maybeAxios.message === 'string' && maybeAxios.message) return maybeAxios.message;
  }
  return fallback;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ error, message, className = '' }) => {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 py-10 text-center ${className}`}
      role="alert"
      style={{ color: 'var(--color-text-muted)' }}
    >
      <span aria-hidden="true" style={{ fontSize: '24px' }}>⚠️</span>
      <p className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
        Failed to load data
      </p>
      <p className="text-sm">{message ?? getErrorMessage(error)}</p>
    </div>
  );
};
