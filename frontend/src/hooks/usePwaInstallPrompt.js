import { useCallback, useEffect, useState } from 'react';

/**
 * Captures the browser PWA install prompt (Chrome/Edge/Android).
 * On iOS/Safari there is no install prompt event; use a manual hint.
 */
export default function usePwaInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    const onBeforeInstallPrompt = (event) => {
      // Allow us to trigger the prompt from a user gesture.
      event.preventDefault();
      setDeferredPrompt(event);
    };

    const onAppInstalled = () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const promptInstall = useCallback(async () => {
    if (!deferredPrompt) return { outcome: 'unavailable' };

    deferredPrompt.prompt();

    try {
      const choice = await deferredPrompt.userChoice;
      setDeferredPrompt(null);
      return choice;
    } catch {
      setDeferredPrompt(null);
      return { outcome: 'dismissed' };
    }
  }, [deferredPrompt]);

  return {
    canPromptInstall: Boolean(deferredPrompt) && !isInstalled,
    isInstalled,
    promptInstall,
  };
}
