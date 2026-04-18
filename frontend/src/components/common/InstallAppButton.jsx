import React, { useMemo } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from '../../hooks/useTranslation';
import usePwaInstallPrompt from '../../hooks/usePwaInstallPrompt';

function getIsIos() {
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function getIsStandalone() {
  if (typeof window === 'undefined') return false;
  // iOS Safari uses navigator.standalone. Modern browsers use display-mode.
  return Boolean(
    window.matchMedia?.('(display-mode: standalone)').matches ||
      window.navigator?.standalone
  );
}

export default function InstallAppButton({ className = '' }) {
  const { t } = useTranslation();
  const { canPromptInstall, isInstalled, promptInstall } = usePwaInstallPrompt();

  const isIos = useMemo(() => getIsIos(), []);
  const isStandalone = useMemo(() => getIsStandalone(), []);

  if (isInstalled || isStandalone) return null;

  const label = canPromptInstall
    ? t('nav.installApp', 'Install app')
    : t('nav.downloadApp', 'Download app');

  const handleClick = async () => {
    if (canPromptInstall) {
      const { outcome } = await promptInstall();
      if (outcome === 'accepted') {
        toast.success(t('nav.installAccepted', 'Installing…'));
      } else if (outcome === 'dismissed') {
        toast(t('nav.installDismissed', 'Install canceled'));
      }
      return;
    }

    if (isIos) {
      toast(t('nav.installIosHint', 'On iPhone: Share → Add to Home Screen'));
    } else {
      toast(t('nav.installHint', 'Open your browser menu → Install app / Add to Home Screen'));
    }
  };

  return (
    <button type="button" className={className} onClick={handleClick}>
      <span aria-hidden="true">⬇</span>
      <span>{label}</span>
    </button>
  );
}
