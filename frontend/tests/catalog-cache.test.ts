import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { createCatalogCache } from "../src/lib/catalog-cache.ts";
const signal = () => new AbortController().signal;
const decode = (value: unknown) => {
  assert.equal(typeof value, "number");
  return value as number;
};
afterEach(() => mock.restoreAll());

test("shares concurrent reads and expires or explicitly refreshes successful catalog data", async () => {
  let time = 0;
  const cache = createCatalogCache(() => time, 60);
  const fetch = mock.method(globalThis, "fetch", async () => Response.json(42));
  assert.deepEqual(await Promise.all([cache.read("/jobs", decode, signal()), cache.read("/jobs", decode, signal())]), [42, 42]);
  await cache.read("/jobs", decode, signal());
  assert.equal(fetch.mock.callCount(), 1);
  time = 60;
  await cache.read("/jobs", decode, signal());
  assert.equal(fetch.mock.callCount(), 2);
  await cache.read("/jobs", decode, signal(), true);
  assert.equal(fetch.mock.callCount(), 3);
});

test("cancelling one subscriber leaves another active; cancelling the last aborts transport", async () => {
  const cache = createCatalogCache();
  let complete!: (value: Response) => void;
  let transport!: AbortSignal;
  mock.method(globalThis, "fetch", (_url: unknown, options?: RequestInit) => {
    transport = options!.signal!;
    return new Promise<Response>((resolve, reject) => {
      complete = resolve;
      transport.addEventListener("abort", () => reject(transport.reason));
    });
  });
  const first = new AbortController();
  const a = cache.read("/jobs", decode, first.signal);
  const b = cache.read("/jobs", decode, signal());
  first.abort();
  await assert.rejects(a, { name: "AbortError" });
  assert.equal(transport.aborted, false);
  complete(Response.json(42));
  assert.equal(await b, 42);
  const last = new AbortController();
  const c = cache.read("/jobs/demo_ds", decode, last.signal);
  last.abort();
  await assert.rejects(c, { name: "AbortError" });
  assert.equal(transport.aborted, true);
});

test("immediate resubscription reuses transport after development effect cleanup", async () => {
  const cache = createCatalogCache();
  const fetch = mock.method(globalThis, "fetch", async () => Response.json(42));
  const first = new AbortController();
  const a = cache.read("/jobs", decode, first.signal);
  first.abort();
  const b = cache.read("/jobs", decode, signal());
  await assert.rejects(a, { name: "AbortError" });
  assert.equal(await b, 42);
  assert.equal(fetch.mock.callCount(), 1);
});

test("failed requests and invalid payloads are retried instead of cached", async () => {
  const cache = createCatalogCache();
  const fetch = mock.method(globalThis, "fetch", async () => new Response("unavailable", { status: 503 }));
  await assert.rejects(cache.read("/jobs", decode, signal()));
  fetch.mock.mockImplementation(async () => Response.json("bad"));
  await assert.rejects(cache.read("/jobs", decode, signal()));
  fetch.mock.mockImplementation(async () => Response.json(42));
  assert.equal(await cache.read("/jobs", decode, signal()), 42);
  assert.equal(fetch.mock.callCount(), 3);
});

test("capacity is bounded and non-catalog paths never enter the shared cache", async () => {
  const cache = createCatalogCache(Date.now, 60_000, 1);
  const fetch = mock.method(globalThis, "fetch", async () => Response.json(42));
  for (const path of ["/jobs", "/jobs/demo_ds", "/jobs", "/resumes/limits", "/resumes/limits", "/jobs/demo_ds/resumes/assess", "/jobs/demo_ds/resumes/assess"]) {
    await cache.read(path, decode, signal());
  }
  assert.equal(fetch.mock.callCount(), 7);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(cache.read("/jobs", decode, controller.signal), { name: "AbortError" });
});
