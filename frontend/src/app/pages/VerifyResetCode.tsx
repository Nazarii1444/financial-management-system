import { useState } from 'react';
import { Shield, ArrowLeft } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { useLanguage } from '../i18n/LanguageContext';
import { LanguageSelector } from '../components/auth/LanguageSelector';
import { authApi, ApiError } from '../lib/api';
import { errorMessage } from '../lib/errors';
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from '../components/ui/input-otp';

export function VerifyResetCode() {
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useLanguage();

  const email: string = location.state?.email || '';

  const handleVerify = async () => {
    if (code.length !== 6) {
      setError(t.auth.enterCompleteCode);
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      await authApi.verifyPasswordReset(email, code);
      toast.success(t.auth.codeVerifiedSuccess);
      navigate('/forgot-password/reset', { state: { email, code } });
    } catch (err) {
      const message = err instanceof ApiError && (err.status === 404 || err.status === 405) ? t.auth.resetNotAvailable : errorMessage(err, t);
      setError(message);
      toast.error(message);
      setCode('');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendCode = async () => {
    setCode('');
    setError('');
    try {
      await authApi.requestPasswordReset(email);
      toast.success(t.auth.newCodeSent);
    } catch (err) {
      toast.error(err instanceof ApiError && (err.status === 404 || err.status === 405) ? t.auth.resetNotAvailable : errorMessage(err, t));
    }
  };

  const handleBack = () => {
    navigate('/forgot-password');
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
              <Shield className="w-7 h-7 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">{t.auth.verifyResetCode}</h1>
          <p className="text-gray-600 mt-2">
            {t.auth.verifyResetCodeDescription}
          </p>
        </div>

        {/* Verify Card */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t.auth.verifyResetCode}</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBack}
                className="text-gray-500 hover:text-gray-700"
              >
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Email Info */}
            <div className="p-3 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600 text-center">
                {t.auth.sentCodeTo} <span className="font-medium text-gray-900">{email}</span>
              </p>
            </div>

            {/* OTP Input */}
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-4">
                <InputOTP
                  maxLength={6}
                  value={code}
                  onChange={(value) => {
                    setCode(value);
                    setError('');
                  }}
                  disabled={isLoading}
                >
                  <InputOTPGroup>
                    <InputOTPSlot index={0} />
                    <InputOTPSlot index={1} />
                    <InputOTPSlot index={2} />
                    <InputOTPSlot index={3} />
                    <InputOTPSlot index={4} />
                    <InputOTPSlot index={5} />
                  </InputOTPGroup>
                </InputOTP>

                {error && (
                  <div className="flex items-center gap-2 text-red-600 text-sm">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {error}
                  </div>
                )}
              </div>

              <Button
                onClick={handleVerify}
                className="w-full"
                disabled={isLoading || code.length !== 6}
              >
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
                    {t.auth.verifying}
                  </>
                ) : (
                  t.auth.verifyAndContinue
                )}
              </Button>
            </div>

            {/* Resend Code */}
            <div className="text-center space-y-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleResendCode}
                disabled={isLoading}
              >
                {t.auth.resendCode}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}