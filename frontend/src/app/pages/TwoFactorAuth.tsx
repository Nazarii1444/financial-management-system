import { useState } from 'react';
import { Shield, ArrowLeft, Smartphone } from 'lucide-react';
import { Navigate, useNavigate, useLocation } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { LanguageSelector } from '../components/auth/LanguageSelector';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '../components/ui/input-otp';
import { ApiError } from '../lib/api';
import { errorMessage } from '../lib/errors';

interface TwoFaState {
  email?: string;
  tempToken?: string;
  remember?: boolean;
}

export function TwoFactorAuth() {
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  // Remounting the OTP input after a failed attempt puts the cursor back into it
  const [attempt, setAttempt] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const { complete2fa } = useAuth();
  const { t } = useLanguage();

  const { email, tempToken, remember = true } = (location.state as TwoFaState | null) ?? {};

  // Reached /2fa directly (or after reload) — there is no pending login to finish
  if (!tempToken) return <Navigate to="/login" replace />;

  const handleVerify = async (value = code) => {
    if (value.length !== 6) {
      setError(t.auth.enterCompleteCode);
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      await complete2fa(tempToken, value, remember);
      toast.success(t.auth.authenticationSuccess);
      navigate('/', { replace: true });
    } catch (err) {
      const message = errorMessage(err, t);
      setError(message);
      toast.error(message);
      setCode('');
      setAttempt((n) => n + 1);
      // The temp token lives 5 minutes — after that only a fresh login helps
      if (err instanceof ApiError && message === t.errors.twoFaSessionExpired) {
        navigate('/login', { replace: true });
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4 relative">
      <LanguageSelector />

      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-600 to-purple-600 rounded-xl flex items-center justify-center">
              <Shield className="w-7 h-7 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">{t.auth.verify2FA}</h1>
          <p className="text-gray-600 mt-2">{t.auth.verify2FADescription}</p>
        </div>

        <Card className="border-0 shadow-xl">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t.auth.verify2FA}</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/login')}
                className="text-gray-500 hover:text-gray-700"
                title={t.auth.backToLogin}
              >
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="p-3 bg-gray-50 rounded-lg flex items-center gap-3">
              <Smartphone className="w-5 h-5 text-blue-600 flex-shrink-0" />
              <div>
                <p className="text-sm text-gray-700">{t.auth.enterCodeBelow}</p>
                {email && <p className="text-xs text-gray-500 mt-0.5">{email}</p>}
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex flex-col items-center gap-4">
                <InputOTP
                  key={attempt}
                  maxLength={6}
                  value={code}
                  autoFocus
                  onChange={(value) => {
                    setCode(value);
                    setError('');
                  }}
                  onComplete={(value: string) => void handleVerify(value)}
                  disabled={isLoading}
                >
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot key={i} index={i} />
                    ))}
                  </InputOTPGroup>
                </InputOTP>

                {error && <div className="text-red-600 text-sm text-center">{error}</div>}
                <p className="text-xs text-gray-500">{t.auth.codeRefreshHint}</p>
              </div>

              <Button onClick={() => handleVerify()} className="w-full" disabled={isLoading || code.length !== 6}>
                <Shield className="w-4 h-4 mr-2" />
                {isLoading ? t.auth.verifying : t.auth.verifyCode}
              </Button>
            </div>

            <div className="text-center">
              <Button type="button" variant="link" size="sm" onClick={() => navigate('/login')}>
                {t.auth.backToLogin}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
