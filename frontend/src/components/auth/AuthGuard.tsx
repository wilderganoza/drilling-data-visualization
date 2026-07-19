import React, { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { isTokenValid } from '../../utils/jwt';

interface AuthGuardProps {
  children: React.ReactNode;
}

export const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const { isAuthenticated, loadFromStorage } = useAuthStore();

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  // Check localStorage directly on first render (before store hydrates).
  // Un token expirado cuenta como no autenticado: expulsar al login ya,
  // en vez de esperar al primer 401 de la API.
  const hasValidToken = isTokenValid(localStorage.getItem('access_token'));

  if (!isAuthenticated && !hasValidToken) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};
