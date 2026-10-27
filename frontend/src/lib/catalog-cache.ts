import { fetchCatalog } from "./catalog.ts";

// Only curated synthetic catalog GETs qualify. Uploads, limits and availability bypass this cache.
const syntheticPath = /^\/jobs(?:\/demo_[a-z0-9_]+(?:\/candidates(?:\/demo_[a-z0-9_]+)?)?)?$/;
type Pending = { controller: AbortController; promise: Promise<unknown>; readers: number };

export function createCatalogCache(now = Date.now, ttl = 60_000, capacity = 64) {
  const completed = new Map<string, { value: unknown; expires: number }>();
  const pending = new Map<string, Pending>();

  async function read<T>(path: string, decode: (value: unknown) => T, signal: AbortSignal, refresh = false): Promise<T> {
    signal.throwIfAborted();
    if (!syntheticPath.test(path)) return fetchCatalog(path, decode, signal);
    if (refresh) completed.delete(path);
    const stored = completed.get(path);
    if (stored && stored.expires > now()) {
      try { return decode(stored.value); }
      catch (error) { completed.delete(path); throw error; }
    }
    completed.delete(path);
    let active = pending.get(path);
    if (!active) {
      const controller = new AbortController();
      const promise = fetchCatalog(path, (value) => value, controller.signal);
      active = { controller, promise, readers: 0 };
      pending.set(path, active);
    }
    const request = active;
    request.readers++;
    return new Promise<T>((resolve, reject) => {
      let finished = false;
      function release() {
        if (finished) return;
        finished = true;
        signal.removeEventListener("abort", abort);
        request.readers--;
        // React development effects can immediately subscribe again after cleanup.
        queueMicrotask(() => {
          if (request.readers === 0 && pending.get(path) === request) {
            pending.delete(path);
            request.controller.abort();
          }
        });
      }
      function abort() { release(); reject(signal.reason); }
      signal.addEventListener("abort", abort, { once: true });
      request.promise.then((value) => {
        if (finished) return;
        try {
          const data = decode(value);
          if (!completed.has(path)) {
            completed.set(path, { value, expires: now() + ttl });
            while (completed.size > capacity) completed.delete(completed.keys().next().value!);
          }
          resolve(data);
        } catch (error) { completed.delete(path); reject(error); }
        finally { release(); }
      }, (error: unknown) => { if (!finished) { release(); reject(error); } });
    });
  }
  return { read };
}

// Module memory only: a full reload clears it. No uploaded content or browser storage.
export const catalogCache = createCatalogCache();

export function prefetchCatalog<T>(path: string, decode: (value: unknown) => T) {
  void catalogCache.read(path, decode, new AbortController().signal).catch(() => {
    // An intentional navigation retries normally if speculative loading failed.
  });
}
