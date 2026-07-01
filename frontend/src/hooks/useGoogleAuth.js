import { useState, useEffect, useCallback, useRef } from 'react';

const GOOGLE_SCRIPT_SRC = 'https://accounts.google.com/gsi/client';
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

let scriptLoaded = false;
let scriptLoading = false;
const pendingCallbacks = [];

function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (scriptLoaded) {
      resolve();
      return;
    }

    pendingCallbacks.push({ resolve, reject });

    if (scriptLoading) return;
    scriptLoading = true;

    const script = document.createElement('script');
    script.src = GOOGLE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      scriptLoaded = true;
      scriptLoading = false;
      const cbs = pendingCallbacks.splice(0);
      cbs.forEach(cb => cb.resolve());
    };
    script.onerror = () => {
      scriptLoading = false;
      const cbs = pendingCallbacks.splice(0);
      cbs.forEach(cb => cb.reject(new Error('Failed to load Google script')));
    };
    document.head.appendChild(script);
  });
}

export function useGoogleAuth(onCredential) {
  const [isReady, setIsReady] = useState(false);
  const onCredentialRef = useRef(onCredential);
  const initializedRef = useRef(false);
  const promptingRef = useRef(false);

  useEffect(() => {
    onCredentialRef.current = onCredential;
  });

  useEffect(() => {
    if (!CLIENT_ID) {
      console.warn('VITE_GOOGLE_CLIENT_ID is not configured');
      return;
    }

    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (!cancelled) setIsReady(true);
      })
      .catch((err) => {
        if (!cancelled) console.error('Google script load failed:', err);
      });

    return () => {
      cancelled = true;
      if (window.google?.accounts?.id) {
        window.google.accounts.id.cancel();
        initializedRef.current = false;
      }
    };
  }, []);

  const triggerGoogleSignIn = useCallback(() => {
    if (!window.google?.accounts?.id || !CLIENT_ID) return;
    if (promptingRef.current) return;
    promptingRef.current = true;

    window.google.accounts.id.cancel();

    window.google.accounts.id.initialize({
      client_id: CLIENT_ID,
      callback: (response) => {
        promptingRef.current = false;
        if (response.credential) {
          onCredentialRef.current(response.credential);
        }
      },
      cancel_on_tap_outside: true,
      context: 'signin',
    });
    initializedRef.current = true;

    window.google.accounts.id.prompt();
  }, []);

  return { triggerGoogleSignIn, isReady, clientConfigured: !!CLIENT_ID };
}
