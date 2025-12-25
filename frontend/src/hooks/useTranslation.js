import { useContext } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { translations } from '../utils/translations';

export const useTranslation = () => {
  const { language } = useLanguage();

  const t = (key) => {
    const keys = key.split('.');
    let value = translations[language];
    
    for (const k of keys) {
      value = value?.[k];
      if (value === undefined) {
        console.warn(`Translation missing for key: ${key}`);
        return key;
      }
    }
    
    return value;
  };

  return { t, language };
};

