import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { decodeStart, endScreening, getNotice, reconnectToken, ScreeningError, sendMessage, startScreening, voiceErrorMessage } from "../src/lib/screenings.ts";

const notice = { notice_version: "2026-10-27", text: "AI screening notice; a human recruiter decides.", screening_minutes: 10, voice_available: true, text_available: true };
const session = { session_id: "S".repeat(22), capability: "C".repeat(43) };
const voiceStart = {
  ...session, mode: "voice", expires_at: "2026-10-28T10:00:00Z", greeting: "Hello, I'm an AI screening assistant.",
  screening_seconds: 600, max_turns: 40, agent_url: "wss://agent.deepgram.com/v1/agent/converse", deepgram_token: "jwt", token_expires_in: 30,
  settings: { type: "Settings", agent: {} },
};
const textStart = { ...voiceStart, mode: "text", agent_url: null, deepgram_token: null, token_expires_in: null, settings: null };
afterEach(() => mock.restoreAll());

function expectRequest(options: RequestInit | undefined, method: string) {
  assert.equal(options?.method, method);
  assert.equal(options?.cache, "no-store"); assert.equal(options?.credentials, "omit"); assert.equal(options?.redirect, "error");
}

test("start sends consent for the chosen mode and decodes the session", async () => {
  const fetch = mock.method(globalThis, "fetch", async (url: unknown, options?: RequestInit) => {
    expectRequest(options, "POST");
    assert.ok(String(url).endsWith("/screenings"));
    const body = JSON.parse(String(options?.body));
    return Response.json(body.mode === "voice" ? voiceStart : textStart, { status: 201 });
  });
  const candidate = { kind: "demo", candidate_id: "demo_ds_avery" } as const;
  assert.deepEqual(await startScreening("demo_ds", candidate, "voice", notice, new AbortController().signal), voiceStart);
  assert.deepEqual(JSON.parse(String(fetch.mock.calls[0].arguments[1]?.body)), {
    job_id: "demo_ds", candidate, mode: "voice", consent: { audio_capture: true, ai_processing: true, notice_version: "2026-10-27" },
  });
  assert.deepEqual(await startScreening("demo_ds", candidate, "text", notice, new AbortController().signal), textStart);
  assert.equal(JSON.parse(String(fetch.mock.calls[1].arguments[1]?.body)).consent.audio_capture, false);
});

test("decoders reject mismatched modes, foreign agent hosts and malformed sessions", () => {
  assert.throws(() => decodeStart(voiceStart, "text"), ScreeningError);
  assert.throws(() => decodeStart({ ...voiceStart, agent_url: "wss://evil.example/v1/agent/converse" }, "voice"), ScreeningError);
  assert.throws(() => decodeStart({ ...voiceStart, settings: { type: "Other" } }, "voice"), ScreeningError);
  assert.throws(() => decodeStart({ ...textStart, deepgram_token: "jwt" }, "text"), ScreeningError);
  assert.throws(() => decodeStart({ ...textStart, capability: "short" }, "text"), ScreeningError);
});

test("notice, token and messages use the capability in the body, never the URL", async () => {
  const fetch = mock.method(globalThis, "fetch", async (url: unknown, options?: RequestInit) => {
    assert.ok(!String(url).includes(session.capability));
    if (String(url).endsWith("/screenings/notice")) { expectRequest(options, "GET"); return Response.json(notice); }
    expectRequest(options, "POST");
    const body = JSON.parse(String(options?.body));
    assert.equal(body.capability, session.capability);
    if (String(url).endsWith("/token")) return Response.json({ deepgram_token: "jwt2", token_expires_in: 30 });
    if (String(url).endsWith("/messages")) { assert.equal(body.text, "My answer"); return Response.json({ reply: "Next question?", ended: false }); }
    throw new Error("Unexpected request");
  });
  const signal = new AbortController().signal;
  assert.deepEqual(await getNotice(signal), notice);
  assert.deepEqual(await reconnectToken(session, signal), { deepgram_token: "jwt2", token_expires_in: 30 });
  assert.deepEqual(await sendMessage(session, "My answer", signal), { reply: "Next question?", ended: false });
  assert.equal(fetch.mock.callCount(), 3);
});

test("errors map to safe messages without server text", async () => {
  const fetch = mock.method(globalThis, "fetch", async () => Response.json({ error: { code: "voice_busy", message: "private-secret" } }, { status: 503 }));
  await assert.rejects(getNotice(new AbortController().signal), (error: unknown) =>
    error instanceof ScreeningError && error.code === "voice_busy" && /in progress/.test(error.message) && !error.message.includes("private-secret"));
  fetch.mock.mockImplementation(async () => new Response("private-secret", { status: 500 }));
  await assert.rejects(getNotice(new AbortController().signal), (error: unknown) => error instanceof ScreeningError && !error.message.includes("private-secret"));
  fetch.mock.mockImplementation(async () => { throw new TypeError("network"); });
  await assert.rejects(getNotice(new AbortController().signal), ScreeningError);
  const controller = new AbortController();
  controller.abort();
  fetch.mock.mockImplementation(async () => { throw new DOMException("aborted", "AbortError"); });
  await assert.rejects(getNotice(controller.signal), (error: unknown) => error instanceof DOMException);
});

test("end is fire-and-forget with keepalive", async () => {
  const fetch = mock.method(globalThis, "fetch", async (_url: unknown, options?: RequestInit) => {
    assert.equal(options?.keepalive, true);
    throw new TypeError("offline");
  });
  endScreening(session);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(fetch.mock.callCount(), 1);
});

test("voice errors name known causes and show provider codes, never other text", () => {
  assert.match(voiceErrorMessage("microphone_denied"), /Microphone access was blocked/);
  assert.equal(voiceErrorMessage("FAILED_TO_THINK"), "The voice service reported a problem (code: FAILED_TO_THINK). Continue by text.");
  assert.equal(voiceErrorMessage(undefined), "The voice service reported a problem. Continue by text.");
  assert.equal(voiceErrorMessage("<b>provider text</b>"), "The voice service reported a problem. Continue by text.");
});
