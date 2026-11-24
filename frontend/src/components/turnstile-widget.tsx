"use client";

import { useEffect, useRef, useState } from "react";
import { loadTurnstile, type TurnstileApi } from "@/lib/turnstile";

/**
 * Cloudflare's bot check. Reports each new token, or null when one expires or the check fails.
 * A token works once, so give the widget a new `key` after it has been spent.
 */
export function TurnstileWidget({ siteKey, action, onToken, help = "Cloudflare checks that you're a person before the screening starts." }: { siteKey: string; action: string; onToken: (token: string | null) => void; help?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const report = useRef(onToken);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    report.current = onToken;
  });

  useEffect(() => {
    let cancelled = false;
    let api: TurnstileApi | null = null;
    let widget: string | undefined;
    loadTurnstile().then(
      (loaded) => {
        if (cancelled || !container.current) return;
        api = loaded;
        widget = loaded.render(container.current, {
          sitekey: siteKey, action, theme: "dark", size: "flexible",
          callback: (token) => report.current(token),
          "expired-callback": () => report.current(null),
          "error-callback": () => report.current(null),
        });
      },
      () => { if (!cancelled) setFailed(true); },
    );
    return () => {
      cancelled = true;
      if (api && widget !== undefined) api.remove(widget);
    };
  }, [siteKey, action]);

  return (
    <div className="mission-bot-check">
      <div ref={container} />
      {failed
        ? <p role="alert" className="mission-help">The bot check could not load. Allow challenges.cloudflare.com in your browser, or try another browser.</p>
        : <p className="mission-help">{help}</p>}
    </div>
  );
}
