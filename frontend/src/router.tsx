import { createBrowserRouter, Navigate } from 'react-router-dom';
import { WellVisualization, QualityAnalysis } from './pages';
import { WellLogs } from './pages/WellLogs';
import { WellLogsGeneral } from './pages/WellLogsGeneral';
import { QualityAnalysisGeneral } from './pages/QualityAnalysisGeneral';
import { ChartsGallery as Crossplots } from './pages/ChartsGallery';
import { Comparison } from './pages/Comparison';
import { WellVisualizationGeneral } from './pages/WellVisualizationGeneral';
import { Login } from './pages/Login';
import { UserManagement } from './pages/UserManagement';
import { AuthGuard } from './components/auth/AuthGuard';
import { OutlierDetection } from './pages/OutlierDetection';
import { Cases } from './pages/Cases';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: <Navigate to="/wells" replace />,
  },
  {
    path: '/wells',
    element: <AuthGuard><WellVisualizationGeneral /></AuthGuard>,
  },
  {
    path: '/wells/:wellId',
    element: <AuthGuard><WellVisualization /></AuthGuard>,
  },
  {
    path: '/wells/:wellId/quality',
    element: <AuthGuard><QualityAnalysis /></AuthGuard>,
  },
  {
    path: '/wells/:wellId/logs',
    element: <AuthGuard><WellLogs /></AuthGuard>,
  },
  {
    path: '/logs',
    element: <AuthGuard><WellLogsGeneral /></AuthGuard>,
  },
  {
    path: '/quality',
    element: <AuthGuard><QualityAnalysisGeneral /></AuthGuard>,
  },
  {
    path: '/crossplots',
    element: <AuthGuard><Crossplots /></AuthGuard>,
  },
  {
    path: '/comparison',
    element: <AuthGuard><Comparison /></AuthGuard>,
  },
  {
    path: '/outliers',
    element: <AuthGuard><OutlierDetection /></AuthGuard>,
  },
  {
    path: '/cases',
    element: <AuthGuard><Cases /></AuthGuard>,
  },
  {
    path: '/users',
    element: <AuthGuard><UserManagement /></AuthGuard>,
  },
]);
