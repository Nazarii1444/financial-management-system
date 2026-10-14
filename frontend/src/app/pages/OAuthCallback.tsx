import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { LoadingState } from '../components/common/States';

/** Backend OAuth callbacks redirect here with tokens in the URL fragment */
export function OAuthCallback() {
  const { acceptTokens } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const access = params.get('access_token');
    const refresh = params.get('refresh_token');
    // Drop tokens from the address bar / history right away
    window.history.replaceState(null, '', window.location.pathname);

    if (!access || !refresh) {
      toast.error(t.auth.oauthFailed);
      navigate('/login', { replace: true });
      return;
    }
    acceptTokens(access, refresh)
      .then(() => {
        toast.success(t.auth.loginSuccess);
        navigate('/', { replace: true });
      })
      .catch(() => {
        toast.error(t.auth.oauthFailed);
        navigate('/login', { replace: true });
      });
  }, [acceptTokens, navigate, t]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-2">
      <LoadingState />
      <p className="text-sm text-gray-500">{t.auth.oauthSigningIn}</p>
    </div>
  );
}
