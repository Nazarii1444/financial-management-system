import { useState } from 'react';
import { Shield, ArrowLeft } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { LanguageSelector } from '../components/auth/LanguageSelector';
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from '../components/ui/input-otp';

// Mock 2FA code for testing
const MOCK_2FA_CODE = '123456';

export function TwoFactorAuth() {
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { t } = useLanguage();

  const email = location.state?.email || 'demo@financehub.com';

  const handleVerify = () => {
    if (code.length !== 6) {
      setError(t.auth.enterCompleteCode);
      return;
    }

    setIsLoading(true);
    setError('');

    // Simulate API call
    setTimeout(() => {
      if (code === MOCK_2FA_CODE) {
        login();
        toast.success(t.auth.authenticationSuccess);
        navigate('/');
      } else {
        setError(t.auth.invalidVerificationCode);
        toast.error(t.auth.invalidVerificationCode);
        setCode('');
      }
      setIsLoading(false);
    }, 1000);
  };

  const handleResendCode = () => {
    toast.success(t.auth.newCodeSent);
    setCode('');
    setError('');
  };

  const handleBackToLogin = () => {
    navigate('/login');
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
          <h1 className="text-3xl font-bold text-gray-900">{t.auth.verify2FA}</h1>
          <p className="text-gray-600 mt-2">
            {t.auth.verify2FADescription}
          </p>
        </div>

        {/* Demo Code Info */}
        <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div className="flex-1">
              <h4 className="text-sm font-medium text-blue-900 mb-1">{t.auth.demoAccount}</h4>
              <p className="text-xs text-blue-700 mb-2">
                {t.auth.demoCodeHint}
              </p>
              <div className="text-lg text-blue-800 font-mono bg-white rounded px-3 py-2 text-center tracking-widest">
                {MOCK_2FA_CODE}
              </div>
            </div>
          </div>
        </div>

        {/* 2FA Card */}
        <Card className="border-0 shadow-xl">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t.auth.verify2FA}</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBackToLogin}
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
                    <svg
                      className="w-4 h-4"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
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
                  <>
                    <Shield className="w-4 h-4 mr-2" />
                    {t.auth.verifyCode}
                  </>
                )}
              </Button>
            </div>

            {/* Resend Code */}
            <div className="text-center space-y-3">
              <p className="text-sm text-gray-600">{t.auth.havingTrouble}</p>
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

            {/* Security Notice */}
            <div className="pt-4 border-t border-gray-100">
              <div className="flex items-start gap-3 p-3 bg-amber-50 rounded-lg">
                <svg
                  className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <div>
                  <p className="text-xs text-amber-800">
                    <strong>{t.auth.contactSupport}:</strong> {t.auth.demoCodeHint}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Help Text */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            {t.auth.havingTrouble}{' '}
            <a href="#" className="text-blue-600 hover:text-blue-700 font-medium">
              {t.auth.contactSupport}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}