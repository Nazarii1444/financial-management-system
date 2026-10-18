import { createBrowserRouter, Navigate } from 'react-router';
import { MainLayout } from './components/layout/MainLayout';
import { Dashboard } from './pages/Dashboard';
import { Transactions } from './pages/Transactions';
import { Budgets } from './pages/Budgets';
import { Goals } from './pages/Goals';
import { Reports } from './pages/Reports';
import { Settings } from './pages/Settings';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { TwoFactorAuth } from './pages/TwoFactorAuth';
import { ForgotPassword } from './pages/ForgotPassword';
import { VerifyResetCode } from './pages/VerifyResetCode';
import { ResetPassword } from './pages/ResetPassword';
import { OAuthCallback } from './pages/OAuthCallback';
import { GuestRoute, ProtectedRoute } from './components/ProtectedRoute';

const guest = (element: React.ReactNode) => <GuestRoute>{element}</GuestRoute>;

export const router = createBrowserRouter([
  { path: '/login', element: guest(<Login />) },
  { path: '/register', element: guest(<Register />) },
  { path: '/2fa', element: guest(<TwoFactorAuth />) },
  { path: '/forgot-password', element: guest(<ForgotPassword />) },
  { path: '/forgot-password/verify', element: guest(<VerifyResetCode />) },
  { path: '/forgot-password/reset', element: guest(<ResetPassword />) },
  { path: '/oauth/callback', Component: OAuthCallback },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <MainLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, Component: Dashboard },
      { path: 'transactions', Component: Transactions },
      { path: 'budgets', Component: Budgets },
      { path: 'goals', Component: Goals },
      { path: 'reports', Component: Reports },
      { path: 'settings', Component: Settings },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
