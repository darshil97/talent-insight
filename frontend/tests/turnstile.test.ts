import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTurnstile, TURNSTILE_SCRIPT, type TurnstileApi } from "../src/lib/turnstile.ts";

type FakeScript = { src: string; async: boolean; onload: (() => void) | null; onerror: (() => void) | null; removed: boolean; remove(): void };

function fakeDocument() {
  const scripts: FakeScript[] = [];
  const doc = {
    createElement: () => {
      const script: FakeScript = { src: "", async: false, onload: null, onerror: null, removed: false, remove() { this.removed = true; } };
      return script;
    },
    head: { append: (script: FakeScript) => scripts.push(script) },
  };
  return { doc: doc as unknown as Document, scripts };
}

test("Cloudflare's script loads once, and a failed load can be retried", async () => {
  const scope = globalThis as { turnstile?: TurnstileApi };
  const { doc, scripts } = fakeDocument();
  const failed = loadTurnstile(doc);
  assert.equal(loadTurnstile(doc), failed);
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].src, TURNSTILE_SCRIPT);
  scripts[0].onerror?.();
  await assert.rejects(failed);
  assert.ok(scripts[0].removed);

  const retried = loadTurnstile(doc);
  assert.equal(scripts.length, 2);
  const api: TurnstileApi = { render: () => "widget-1", remove: () => undefined };
  scope.turnstile = api;
  scripts[1].onload?.();
  assert.equal(await retried, api);
  assert.equal(await loadTurnstile(doc), api);
  assert.equal(scripts.length, 2);
  delete scope.turnstile;
});
