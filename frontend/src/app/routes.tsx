import { createBrowserRouter } from 'react-router';
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
import { ProtectedRoute } from './components/ProtectedRoute';

export const router = createBrowserRouter([
  {
    path: '/login',
    Component: Login,
  },
  {
    path: '/register',
    Component: Register,
  },
  {
    path: '/2fa',
    Component: TwoFactorAuth,
  },
  {
    path: '/forgot-password',
    Component: ForgotPassword,
  },
  {
    path: '/forgot-password/verify',
    Component: VerifyResetCode,
  },
  {
    path: '/forgot-password/reset',
    Component: ResetPassword,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <MainLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        Component: Dashboard,
      },
      {
        path: 'transactions',
        Component: Transactions,
      },
      {
        path: 'budgets',
        Component: Budgets,
      },
      {
        path: 'goals',
        Component: Goals,
      },
      {
        path: 'reports',
        Component: Reports,
      },
      {
        path: 'settings',
        Component: Settings,
      },
    ],
  },
]);