import { Navigate, useLocation } from 'react-router';
import { useAuth } from '../context/AuthContext';
import { LoadingState } from './common/States';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <LoadingState className="h-screen" />;
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Auth pages (login, register…) redirect to the app when already signed in */
export function GuestRoute({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  if (status === 'loading') return <LoadingState className="h-screen" />;
  if (status === 'authenticated') return <Navigate to="/" replace />;
  return <>{children}</>;
}
