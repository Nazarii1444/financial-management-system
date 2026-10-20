import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from 'react';
import { ApiError, authApi, passkeysApi, SESSION_EXPIRED_EVENT, tokenStore, usersApi } from '../lib/api';
import { getPasskey } from '../lib/webauthn';
import type { UserOut } from '../types/api';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

export type LoginResult = { requires2fa: false } | { requires2fa: true; tempToken: string };

interface AuthContextType {
  status: AuthStatus;
  isAuthenticated: boolean;
  user: UserOut | null;
  login: (email: string, password: string, remember: boolean) => Promise<LoginResult>;
  complete2fa: (tempToken: string, code: string, remember: boolean) => Promise<void>;
  /** Passwordless sign-in: the browser shows the passkeys it has for this site */
  loginWithPasskey: (remember: boolean) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  /** Store tokens obtained elsewhere (OAuth redirect) and load the user */
  acceptTokens: (access: string, refresh: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setUser: (user: UserOut) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<UserOut | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (tokenStore.get() ? 'loading' : 'anonymous'));

  const loadUser = useCallback(async () => {
    try {
      const me = await usersApi.me();
      setUserState(me);
      setStatus('authenticated');
    } catch (err) {
      // Keep tokens if the backend is just unreachable — a reload will restore the session
      if (err instanceof ApiError && err.status !== 0) tokenStore.clear();
      setUserState(null);
      setStatus('anonymous');
    }
  }, []);

  // Restore session on page load
  useEffect(() => {
    if (tokenStore.get()) void loadUser();
  }, [loadUser]);

  // Refresh token expired somewhere deep in the app → drop the session
  useEffect(() => {
    const onExpired = () => {
      setUserState(null);
      setStatus('anonymous');
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback<AuthContextType['login']>(
    async (email, password, remember) => {
      const res = await authApi.login(email.trim().toLowerCase(), password);
      if (res.requires_2fa && res.temp_token) return { requires2fa: true, tempToken: res.temp_token };
      tokenStore.set({ access: res.access_token!, refresh: res.refresh_token! }, remember);
      await loadUser();
      return { requires2fa: false };
    },
    [loadUser],
  );

  const complete2fa = useCallback<AuthContextType['complete2fa']>(
    async (tempToken, code, remember) => {
      const pair = await authApi.complete2fa(tempToken, code);
      tokenStore.set({ access: pair.access_token, refresh: pair.refresh_token }, remember);
      await loadUser();
    },
    [loadUser],
  );

  const loginWithPasskey = useCallback<AuthContextType['loginWithPasskey']>(
    async (remember) => {
      const options = await passkeysApi.loginOptions();
      const credential = await getPasskey(options.public_key);
      const pair = await passkeysApi.login(options.challenge_id, credential);
      tokenStore.set({ access: pair.access_token, refresh: pair.refresh_token }, remember);
      await loadUser();
    },
    [loadUser],
  );

  const register = useCallback<AuthContextType['register']>(
    async (username, email, password) => {
      const res = await authApi.signup(username.trim(), email.trim().toLowerCase(), password);
      tokenStore.set({ access: res.access_token!, refresh: res.refresh_token! }, true);
      await loadUser();
    },
    [loadUser],
  );

  const acceptTokens = useCallback<AuthContextType['acceptTokens']>(
    async (access, refresh) => {
      tokenStore.set({ access, refresh }, true);
      await loadUser();
    },
    [loadUser],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Stateless JWT — discarding tokens locally is what actually logs out
    }
    tokenStore.clear();
    setUserState(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo<AuthContextType>(
    () => ({
      status,
      isAuthenticated: status === 'authenticated',
      user,
      login,
      complete2fa,
      loginWithPasskey,
      register,
      acceptTokens,
      logout,
      refreshUser: loadUser,
      setUser: setUserState,
    }),
    [status, user, login, complete2fa, loginWithPasskey, register, acceptTokens, logout, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
