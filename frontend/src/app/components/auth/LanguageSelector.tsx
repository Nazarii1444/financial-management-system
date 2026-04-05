import { motion } from 'motion/react';
import { useLanguage } from '../../i18n/LanguageContext';

export function LanguageSelector() {
  const { language, setLanguage } = useLanguage();

  const languages = [
    { code: 'en', label: 'EN' },
    { code: 'uk', label: 'УКР' }
  ];

  return (
    <div className="absolute top-6 right-6">
      <div className="relative flex gap-1 p-1.5 bg-gradient-to-br from-white/90 via-gray-50/80 to-gray-100/90 rounded-xl border border-white/20 shadow-lg" style={{ backdropFilter: 'blur(20px)' }}>
        {languages.map((lang) => {
          const isActive = language === lang.code;
          
          return (
            <button
              key={lang.code}
              onClick={() => setLanguage(lang.code as 'en' | 'uk')}
              className="relative px-6 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 z-10 min-w-[60px]"
            >
              {isActive && (
                <motion.div
                  layoutId="activeLanguageBg"
                  className="absolute inset-0 rounded-lg bg-gradient-to-br from-blue-500 via-blue-600 to-purple-600 shadow-lg"
                  style={{
                    boxShadow: '0 4px 16px rgba(59, 130, 246, 0.4)',
                  }}
                  transition={{
                    type: 'spring',
                    stiffness: 400,
                    damping: 30,
                  }}
                />
              )}
              
              <span className={`relative z-10 transition-all duration-200 ${isActive ? 'text-white font-semibold' : 'text-gray-600'}`}>
                {lang.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}