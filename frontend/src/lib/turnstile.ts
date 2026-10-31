/** Cloudflare Turnstile, loaded from Cloudflare only when a bot check is required; no npm dependency. */

export interface TurnstileOptions {
  sitekey: string;
  action: string;
  theme: "dark";
  size: "flexible";
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
}
export interface TurnstileApi {
  render(container: HTMLElement, options: TurnstileOptions): string | undefined;
  remove(widget: string): void;
}

export const TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const scope = globalThis as { turnstile?: TurnstileApi };
let loading: Promise<TurnstileApi> | null = null;

/** Adds Cloudflare's script once; a failed load (for example a blocker) can be retried by the next widget. */
export function loadTurnstile(doc: Document = document): Promise<TurnstileApi> {
  if (scope.turnstile) return Promise.resolve(scope.turnstile);
  loading ??= new Promise<TurnstileApi>((resolve, reject) => {
    const script = doc.createElement("script");
    const failed = () => {
      loading = null;
      script.remove();
      reject(new Error("turnstile_unavailable"));
    };
    script.src = TURNSTILE_SCRIPT;
    script.async = true;
    script.onload = () => (scope.turnstile ? resolve(scope.turnstile) : failed());
    script.onerror = failed;
    doc.head.append(script);
  });
  return loading;
}
