// Decodifica el payload de un JWT sin verificar la firma (la verificación
// real la hace el backend); aquí solo se usa para leer la expiración.
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

// Un token malformado o con `exp` vencido no sirve: mejor expulsar al login
// de inmediato que dejar una UI "logueada" que fallará en la primera petición.
export function isTokenValid(token: string | null): boolean {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload) return false;
  const exp = payload.exp;
  if (typeof exp !== 'number') return true; // sin exp no podemos juzgar: lo decide el backend
  return exp * 1000 > Date.now();
}
