"use client";

import { useState, useEffect } from "react";

/**
 * PWA install prompt.
 * - Android/Chrome: captures beforeinstallprompt, shows an Install button.
 * - iOS Safari: no programmatic install exists, so we show instructions
 *   (Share -> Add to Home Screen).
 * Hidden once installed (standalone) or after the user dismisses it.
 */
export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showIOS, setShowIOS] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    // Already installed / running standalone?
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
    if (standalone) {
      setInstalled(true);
      return;
    }
    if (sessionStorage.getItem("pwa-dismissed")) {
      setDismissed(true);
      return;
    }

    const onPrompt = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);

    // iOS detection (Safari only, not standalone)
    const isIOS =
      /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.navigator.standalone;
    if (isIOS) setShowIOS(true);

    const onInstalled = () => setInstalled(true);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed || dismissed) return null;
  if (!deferredPrompt && !showIOS) return null;

  const install = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === "accepted") setDeferredPrompt(null);
    }
  };

  const dismiss = () => {
    sessionStorage.setItem("pwa-dismissed", "1");
    setDismissed(true);
  };

  return (
    <div className="fixed bottom-20 md:bottom-4 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-sm">
      <div className="bg-white border border-gray-200 rounded-xl shadow-xl p-3 flex items-start gap-2">
        <img src="/icon-192.png" alt="" className="w-9 h-9 rounded-lg" />
        <div className="flex-1 text-xs">
          <div className="font-semibold text-gray-900">
            Add to your home screen
          </div>
          {deferredPrompt ? (
            <div className="text-gray-500">
              One tap — opens like a native app.
            </div>
          ) : (
            <div className="text-gray-500">
              Tap <span className="font-medium">Share</span> then{" "}
              <span className="font-medium">"Add to Home Screen"</span>.
            </div>
          )}
        </div>
        {deferredPrompt && (
          <button
            onClick={install}
            className="bg-blue-600 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
          >
            Install
          </button>
        )}
        <button
          onClick={dismiss}
          className="text-gray-400 hover:text-gray-600 text-lg leading-none px-1"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
    </div>
  );
}
