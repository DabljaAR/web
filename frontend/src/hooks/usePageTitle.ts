import { useEffect } from 'react';
import { useTranslation } from './useTranslation';

/**
 * Custom hook to update the document title on page navigation.
 * Uses translation keys to ensure localized titles.
 * 
 * @param titleKey - The translation key for the page title (e.g. 'nav.dashboard')
 * @param fallback - A fallback string if translation is missing
 */
export const usePageTitle = (titleKey?: string, fallback: string = '') => {
  const { t } = useTranslation();

  useEffect(() => {
    const pageTitle = titleKey ? t(titleKey) : fallback;
    const siteName = 'DabljaAR';
    
    document.title = pageTitle && pageTitle !== titleKey 
      ? `${pageTitle} — ${siteName}` 
      : siteName;

    // Optional: cleanup to reset title when component unmounts
    return () => {
      document.title = siteName;
    };
  }, [titleKey, fallback, t]);
};
