import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { translations, Language, TranslationKey } from './translations';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: TranslationKey;
  translateCategory: (categoryName: string) => string;
  translateGoalIcon: (iconLabel: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    try {
      const saved = localStorage.getItem('language');
      return (saved as Language) || 'en';
    } catch {
      return 'en';
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('language', language);
    } catch {
      // Ignore localStorage errors
    }
  }, [language]);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
  };

  const translateCategory = (categoryName: string): string => {
    // First, try to use it directly as a translation key (for mockData format)
    const directKey = categoryName as keyof typeof translations.en.categories;
    if (translations[language].categories[directKey]) {
      return translations[language].categories[directKey];
    }
    
    // Map category names to translation keys (for display format)
    const categoryMap: Record<string, keyof typeof translations.en.categories> = {
      'Salary': 'salary',
      'Freelance': 'freelance',
      'Investment': 'investment',
      'Food & Dining': 'foodDining',
      'Transportation': 'transportation',
      'Shopping': 'shopping',
      'Entertainment': 'entertainment',
      'Bills & Utilities': 'billsUtilities',
      'Healthcare': 'healthcare',
      'Education': 'education',
    };

    const key = categoryMap[categoryName];
    return key ? translations[language].categories[key] : categoryName;
  };

  const translateGoalIcon = (iconLabel: string): string => {
    // Map goal icon labels to translation keys
    const iconMap: Record<string, keyof typeof translations.en.goalIcons> = {
      'Emergency Fund': 'emergencyFund',
      'Travel': 'travel',
      'Electronics': 'electronics',
      'Gifts': 'gifts',
      'Home': 'home',
      'Vehicle': 'vehicle',
    };

    const key = iconMap[iconLabel];
    return key ? translations[language].goalIcons[key] : iconLabel;
  };

  const value = {
    language,
    setLanguage,
    t: translations[language],
    translateCategory,
    translateGoalIcon,
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}