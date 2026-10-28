import assert from "node:assert/strict";
import { test } from "node:test";
import { END_FUNCTION, VoiceAgent, type SocketLike, type VoiceAgentDeps } from "../src/lib/voice-agent.ts";

class FakeSocket implements SocketLike {
  binaryType = "blob";
  readyState = 1;
  sent: (string | ArrayBuffer)[] = [];
  closedWith: number | undefined;
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  url: string;
  protocols: string[];
  constructor(url: string, protocols: string[]) { this.url = url; this.protocols = protocols; }
  send(data: string | ArrayBuffer) { this.sent.push(data); }
  close(code?: number) { this.closedWith = code; this.readyState = 3; }
  receive(message: unknown) { this.onmessage?.({ data: message instanceof ArrayBuffer ? message : JSON.stringify(message) }); }
  json() { return this.sent.filter((item): item is string => typeof item === "string").map((item) => JSON.parse(item)); }
}

function harness(options: { tokens?: string[]; micError?: Error; maxReconnects?: number } = {}) {
  const sockets: FakeSocket[] = [];
  const events: unknown[][] = [];
  const played: ArrayBuffer[] = [];
  let frame: ((pcm: ArrayBuffer) => void) | null = null;
  let micStopped = false;
  let interrupted = 0;
  const tokens = [...(options.tokens ?? [])];
  const deps: VoiceAgentDeps = {
    createSocket: (url, protocols) => { const socket = new FakeSocket(url, protocols); sockets.push(socket); return socket; },
    startMicrophone: async (onFrame) => {
      if (options.micError) throw options.micError;
      frame = onFrame;
      return { stop: () => { micStopped = true; } };
    },
    createPlayer: () => ({ play: (chunk) => played.push(chunk), interrupt: () => { interrupted += 1; }, idle: () => true, close: () => undefined }),
    reconnectToken: async () => { const token = tokens.shift(); if (!token) throw new Error("limit"); return token; },
  };
  const settings = { type: "Settings", agent: { greeting: "Hello", think: {} } };
  const agent = new VoiceAgent({ agentUrl: "wss://agent.deepgram.com/v1/agent/converse", token: "jwt1", settings, maxReconnects: options.maxReconnects ?? 2 }, deps, {
    status: (status) => events.push(["status", status]),
    transcript: (role, text) => events.push(["transcript", role, text]),
    ended: (reason, code) => events.push(["ended", reason, code]),
  });
  return { agent, sockets, events, played, settings, frame: () => frame, micStopped: () => micStopped, interrupted: () => interrupted };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test("connects with the bearer subprotocol and sends server Settings unchanged", async () => {
  const h = harness();
  await h.agent.start();
  const socket = h.sockets[0];
  assert.deepEqual(socket.protocols, ["bearer", "jwt1"]);
  assert.equal(socket.binaryType, "arraybuffer");
  socket.receive({ type: "Welcome", request_id: "r" });
  assert.deepEqual(socket.json()[0], h.settings);
  // Audio is held until the agent has applied the settings.
  h.frame()!(new ArrayBuffer(4));
  assert.equal(socket.sent.length, 1);
  socket.receive({ type: "SettingsApplied" });
  h.frame()!(new ArrayBuffer(4));
  assert.ok(socket.sent[1] instanceof ArrayBuffer);
});

test("reports transcript turns, plays audio and stops playback when the candidate interrupts", async () => {
  const h = harness();
  await h.agent.start();
  const socket = h.sockets[0];
  socket.receive({ type: "Welcome" });
  socket.receive({ type: "SettingsApplied" });
  socket.receive({ type: "ConversationText", role: "assistant", content: "Tell me about an API." });
  socket.receive({ type: "ConversationText", role: "user", content: "I built one." });
  socket.receive(new ArrayBuffer(8));
  socket.receive({ type: "UserStartedSpeaking" });
  assert.equal(h.played.length, 1);
  assert.equal(h.interrupted(), 1);
  assert.deepEqual(h.events.filter((event) => event[0] === "transcript"), [
    ["transcript", "interviewer", "Tell me about an API."],
    ["transcript", "candidate", "I built one."],
  ]);
});

test("end_screening is acknowledged and ends after the closing audio", async () => {
  const h = harness();
  await h.agent.start();
  const socket = h.sockets[0];
  socket.receive({ type: "Welcome" });
  socket.receive({ type: "FunctionCallRequest", functions: [
    { id: "f1", name: END_FUNCTION, arguments: "{}", client_side: true },
    { id: "f2", name: "other", arguments: "{}", client_side: true },
  ] });
  assert.deepEqual(socket.json().slice(1), [
    { type: "FunctionCallResponse", id: "f1", name: END_FUNCTION, content: "ended" },
    { type: "FunctionCallResponse", id: "f2", name: "other", content: "unsupported" },
  ]);
  socket.receive({ type: "AgentAudioDone" });
  assert.deepEqual(h.events.at(-1), ["ended", "interviewer", undefined]);
  assert.equal(socket.closedWith, 1000);
  assert.ok(h.micStopped());
});

test("microphone refusal fails before any connection", async () => {
  const denied = Object.assign(new Error("denied"), { name: "NotAllowedError" });
  const h = harness({ micError: denied });
  await h.agent.start();
  assert.equal(h.sockets.length, 0);
  assert.deepEqual(h.events.at(-1), ["ended", "failed", "microphone_denied"]);
});

test("a refused connection fails fast; a dropped one reconnects with history and no greeting", async () => {
  const refused = harness({ tokens: ["jwt2"] });
  await refused.agent.start();
  refused.sockets[0].onclose?.({});
  assert.deepEqual(refused.events.at(-1), ["ended", "failed", "connection_failed"]);

  const h = harness({ tokens: ["jwt2"], maxReconnects: 1 });
  await h.agent.start();
  h.sockets[0].receive({ type: "Welcome" });
  h.sockets[0].receive({ type: "ConversationText", role: "assistant", content: "First question?" });
  h.sockets[0].onclose?.({});
  await flush();
  const second = h.sockets[1];
  assert.deepEqual(second.protocols, ["bearer", "jwt2"]);
  second.receive({ type: "Welcome" });
  const settings = second.json()[0];
  assert.equal(settings.agent.greeting, undefined);
  assert.deepEqual(settings.agent.context, { messages: [{ type: "History", role: "assistant", content: "First question?" }] });
  assert.equal(h.settings.agent.greeting, "Hello");
  second.onclose?.({});
  assert.deepEqual(h.events.at(-1), ["ended", "failed", "connection_lost"]);
});

test("agent errors end with a safe code, mute holds audio, and stop is idempotent", async () => {
  const h = harness();
  await h.agent.start();
  const socket = h.sockets[0];
  socket.receive({ type: "Welcome" });
  socket.receive({ type: "SettingsApplied" });
  h.agent.setMuted(true);
  h.frame()!(new ArrayBuffer(4));
  assert.equal(socket.sent.length, 1);
  h.agent.setMuted(false);
  socket.receive({ type: "Error", code: "BAD THING <script>", description: "private text" });
  assert.deepEqual(h.events.at(-1), ["ended", "failed", "agent_error"]);
  h.agent.stop();
  assert.equal(h.events.filter((event) => event[0] === "ended").length, 1);
});
