import { useLanguage } from '../contexts/LanguageContext';
import { translations } from '../utils/translations';
import logger from '../utils/logger';

export type TranslationKey = string;

export const useTranslation = () => {
  const { language } = useLanguage();

  const t = (key: TranslationKey, fallback?: string): string => {
    const keys = key.split('.');
    let value: any = translations[language as keyof typeof translations];

    for (const k of keys) {
      value = value?.[k];
      if (value === undefined) {
        logger.warn(`Translation missing for key: ${key}`);
        return fallback ?? key;
      }
    }

    return typeof value === 'string' ? value : (fallback ?? key);
  };

  return { t, language };
};
