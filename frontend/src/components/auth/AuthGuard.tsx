import React, { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

interface AuthGuardProps {
  children: React.ReactNode;
}

export const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const { isAuthenticated, loadFromStorage } = useAuthStore();

  useEffect(() => {
    loadFromStorage();
  }, []);

  // Check localStorage directly on first render (before store hydrates)
  const hasToken = localStorage.getItem('access_token');

  if (!isAuthenticated && !hasToken) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};
