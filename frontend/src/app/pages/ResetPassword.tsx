import { useState } from 'react';
import { Eye, EyeOff, Lock, CheckCircle2 } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { useLanguage } from '../i18n/LanguageContext';
import { LanguageSelector } from '../components/auth/LanguageSelector';
import { authApi, ApiError } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { PasswordStrengthMeter } from '../components/security/PasswordStrengthMeter';

export function ResetPassword() {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<{ password?: string; confirmPassword?: string }>({});
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useLanguage();

  const email: string = location.state?.email || '';
  const code: string = location.state?.code || '';

  // Server rules (src/security/password_policy.py) via the live meter; the leak check runs on submit
  const [passwordAcceptable, setPasswordAcceptable] = useState<boolean | null>(null);
  const validatePassword = (password: string): boolean => password.length >= 10 && passwordAcceptable !== false;

  const validateForm = (): boolean => {
    const newErrors: { password?: string; confirmPassword?: string } = {};

    if (!password) {
      newErrors.password = t.auth.passwordRequired;
    } else if (!validatePassword(password)) {
      newErrors.password = t.auth.passwordRequirements;
    }

    if (!confirmPassword) {
      newErrors.confirmPassword = t.auth.confirmPasswordRequired;
    } else if (password !== confirmPassword) {
      newErrors.confirmPassword = t.auth.passwordsDoNotMatch;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!validateForm()) {
      toast.error(t.auth.fixFormErrors);
      return;
    }

    setIsLoading(true);
    try {
      await authApi.confirmPasswordReset(email, code, password);
      toast.success(t.auth.passwordResetSuccess);
      navigate('/login');
    } catch (err) {
      const message = err instanceof ApiError && (err.status === 404 || err.status === 405) ? t.auth.resetNotAvailable : errorMessage(err, t);
      setErrors({ password: message });
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };


  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4 relative">
      {/* Language Selector */}
      <LanguageSelector />
      
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-600 to-purple-600 rounded-xl flex items-center justify-center">
              <Lock className="w-7 h-7 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">{t.auth.setNewPassword}</h1>
          <p className="text-gray-600 mt-2">
            {t.auth.createStrongPassword}
          </p>
        </div>

        {/* Reset Password Card */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-center">{t.auth.setNewPassword}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email Display */}
              <div className="p-3 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 text-center">
                  {t.auth.resettingFor}{' '}
                  <span className="font-medium text-gray-900">{email}</span>
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">{t.auth.newPassword}</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder={t.auth.passwordPlaceholder}
                    className={`pl-10 pr-10 ${
                      errors.password ? 'border-red-500 focus-visible:ring-red-500' : ''
                    }`}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (errors.password) {
                        setErrors({ ...errors, password: undefined });
                      }
                    }}
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    disabled={isLoading}
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                
                {/* Same live meter as on sign-up */}
                <PasswordStrengthMeter password={password} email={email} onResult={setPasswordAcceptable} />

                {errors.password ? (
                  <p className="text-sm text-red-600 flex items-center gap-1">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {errors.password}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">{t.auth.confirmPassword}</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <Input
                    id="confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    placeholder={t.auth.passwordPlaceholder}
                    className={`pl-10 pr-10 ${
                      errors.confirmPassword ? 'border-red-500 focus-visible:ring-red-500' : ''
                    }`}
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value);
                      if (errors.confirmPassword) {
                        setErrors({ ...errors, confirmPassword: undefined });
                      }
                    }}
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    disabled={isLoading}
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="w-5 h-5" />
                    ) : (
                      <Eye className="w-5 h-5" />
                    )}
                  </button>
                </div>
                {errors.confirmPassword && (
                  <p className="text-sm text-red-600 flex items-center gap-1">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {errors.confirmPassword}
                  </p>
                )}
              </div>

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    {t.auth.resettingPassword}
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    {t.auth.resetPasswordButton}
                  </>
                )}
              </Button>

              {/* Security Tips */}
              <div className="pt-4 border-t border-gray-100">
                <div className="space-y-2">
                  <p className="text-xs font-medium text-gray-700">{t.auth.passwordTips}</p>
                  <ul className="text-xs text-gray-600 space-y-1">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3 h-3 text-green-600" />
                      {t.auth.useMixLetters}
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3 h-3 text-green-600" />
                      {t.auth.includeNumber}
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3 h-3 text-green-600" />
                      {t.auth.minCharacters}
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3 h-3 text-green-600" />
                      {t.auth.considerSpecialChars}
                    </li>
                  </ul>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}