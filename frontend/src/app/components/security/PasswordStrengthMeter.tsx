import { useEffect, useState } from 'react';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { securityApi } from '../../lib/api';
import type { PasswordStrength } from '../../types/api';

const BAR_COLORS = ['bg-red-500', 'bg-orange-500', 'bg-amber-400', 'bg-green-500', 'bg-emerald-600'];
const TEXT_COLORS = ['text-red-600', 'text-orange-600', 'text-amber-600', 'text-green-600', 'text-emerald-700'];

type Durations = { instant: string; centuries: string; second: string; minute: string; hour: string; day: string; month: string; year: string };

/** zxcvbn's English duration ("3 hours", "less than a second", "centuries") → the UI language */
function localizeDuration(text: string, d: Durations): string {
  if (text === 'less than a second') return d.instant;
  if (text === 'centuries') return d.centuries;
  const m = /^(\d+) (second|minute|hour|day|month|year)s?$/.exec(text);
  return m ? `${m[1]} ${d[m[2] as keyof Durations]}` : text;
}

interface Props {
  password: string;
  username?: string;
  email?: string;
  /** Reports whether the server would accept the password (offline checks; the leak check runs on submit) */
  onResult?: (acceptable: boolean | null) => void;
}

/** Live strength meter: the same rules as the server (zxcvbn score, length, name/email, common lists). */
export function PasswordStrengthMeter({ password, username, email, onResult }: Props) {
  const { t } = useLanguage();
  const [result, setResult] = useState<PasswordStrength | null>(null);

  useEffect(() => {
    if (!password) {
      setResult(null);
      onResult?.(null);
      return;
    }
    let cancelled = false;
    // Debounced: one request after typing pauses, not one per key
    const timer = setTimeout(() => {
      securityApi
        .passwordStrength(password, username || undefined, email || undefined)
        .then((r) => {
          if (cancelled) return;
          setResult(r);
          onResult?.(r.acceptable);
        })
        .catch(() => !cancelled && onResult?.(null));
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // onResult is a callback prop; re-running on its identity would refetch on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [password, username, email]);

  if (!password) return <p className="text-xs text-gray-500">{fmt(t.security.rules, { min: 10 })}</p>;

  const score = result?.score ?? 0;
  const codes = (result?.codes ?? []) as (keyof typeof t.security.codes)[];
  return (
    <div className="space-y-1.5" aria-live="polite">
      <div className="flex gap-1" role="meter" aria-valuemin={0} aria-valuemax={4} aria-valuenow={score} aria-label={t.security.strengthLabel.replace('{level}', '')}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-1.5 flex-1 rounded-full transition-colors ${result && score > i ? BAR_COLORS[score] : 'bg-gray-200'}`} />
        ))}
      </div>
      {result && (
        <>
          <p className={`text-xs font-medium ${TEXT_COLORS[score]}`}>
            {fmt(t.security.strengthLabel, { level: t.security.strength[score] })}
            {result.crack_time && <span className="font-normal text-gray-500"> · {fmt(t.security.crackTime, { time: localizeDuration(result.crack_time, t.security.durations) })}</span>}
          </p>
          {codes.length > 0 && (
            <ul className="text-xs text-red-600 list-disc pl-4">
              {codes.map((code) => (
                <li key={code}>{fmt(t.security.codes[code] ?? code, { min: result.min_length })}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
