import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from 'react';
import { translations, Language, Translations } from './translations';

export type DateFormat = 'DD.MM.YYYY' | 'DD/MM/YYYY' | 'MM/DD/YYYY' | 'YYYY-MM-DD';
export const DATE_FORMATS: DateFormat[] = ['DD.MM.YYYY', 'DD/MM/YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD'];

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
  locale: string;
  dateFormat: DateFormat;
  setDateFormat: (format: DateFormat) => void;
  translateCategory: (categoryName: string) => string;
  formatMoney: (amount: number | string, currency?: string | null, opts?: { signed?: boolean; compact?: boolean }) => string;
  formatDate: (value: string | Date | null | undefined) => string;
  monthLabel: (month: number) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

function readPref<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const saved = localStorage.getItem(key) as T | null;
    return saved && allowed.includes(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Ignore localStorage errors
  }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() =>
    readPref<Language>('language', navigator.language?.toLowerCase().startsWith('uk') ? 'uk' : 'en', ['en', 'uk']),
  );
  const [dateFormat, setDateFormatState] = useState<DateFormat>(() =>
    readPref<DateFormat>('dateFormat', 'DD.MM.YYYY', DATE_FORMATS),
  );

  useEffect(() => {
    writePref('language', language);
    document.documentElement.lang = language;
  }, [language]);

  const setDateFormat = useCallback((format: DateFormat) => {
    setDateFormatState(format);
    writePref('dateFormat', format);
  }, []);

  const value = useMemo<LanguageContextType>(() => {
    const t = translations[language];
    const locale = language === 'uk' ? 'uk-UA' : 'en-US';

    const translateCategory = (categoryName: string) => {
      const key = categoryName?.toLowerCase() as keyof Translations['categories'];
      return t.categories[key] ?? categoryName;
    };

    const formatMoney: LanguageContextType['formatMoney'] = (amount, currency, opts = {}) => {
      const num = typeof amount === 'string' ? Number(amount) : amount;
      const safe = Number.isFinite(num) ? num : 0;
      const formatter = new Intl.NumberFormat(locale, {
        style: currency ? 'currency' : 'decimal',
        currency: currency || undefined,
        notation: opts.compact ? 'compact' : 'standard',
        minimumFractionDigits: opts.compact ? 0 : 2,
        maximumFractionDigits: opts.compact ? 1 : 2,
      });
      const text = formatter.format(opts.signed ? Math.abs(safe) : safe);
      if (!opts.signed) return text;
      return `${safe < 0 ? '−' : '+'}${text}`;
    };

    const formatDate: LanguageContextType['formatDate'] = (input) => {
      if (!input) return '';
      const d = typeof input === 'string' ? new Date(input) : input;
      if (Number.isNaN(d.getTime())) return '';
      const dd = String(d.getDate()).padStart(2, '0');
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const yyyy = String(d.getFullYear());
      switch (dateFormat) {
        case 'DD/MM/YYYY':
          return `${dd}/${mm}/${yyyy}`;
        case 'MM/DD/YYYY':
          return `${mm}/${dd}/${yyyy}`;
        case 'YYYY-MM-DD':
          return `${yyyy}-${mm}-${dd}`;
        default:
          return `${dd}.${mm}.${yyyy}`;
      }
    };

    return {
      language,
      setLanguage: setLanguageState,
      t,
      locale,
      dateFormat,
      setDateFormat,
      translateCategory,
      formatMoney,
      formatDate,
      monthLabel: (month: number) => t.months.short[(month - 1 + 12) % 12],
    };
  }, [language, dateFormat, setDateFormat]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}
