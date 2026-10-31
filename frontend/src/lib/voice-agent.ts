/**
 * Minimal Deepgram Voice Agent client. The backend builds the complete Settings message; this
 * client sends it unchanged, streams microphone PCM, plays agent audio and reports transcript
 * turns. Socket, microphone and player are injected so the protocol can be tested without audio.
 * The call is half duplex: while the interviewer's audio plays, the microphone is held and silence
 * is sent instead, so echo or background noise cannot interrupt the question.
 */
import { micLevel } from "./pcm.ts";

export interface SocketLike {
  binaryType: string;
  readyState: number;
  send(data: string | ArrayBuffer): void;
  close(code?: number): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
}
export interface MicrophoneHandle { stop(): void }
export interface PlayerHandle { play(chunk: ArrayBuffer): void; interrupt(): void; idle(): boolean; close(): void }
export interface VoiceAgentDeps {
  createSocket(url: string, protocols: string[]): SocketLike;
  startMicrophone(onFrame: (pcm: ArrayBuffer) => void): Promise<MicrophoneHandle>;
  createPlayer(): PlayerHandle;
  /** A fresh short-lived token for a reconnect; rejects when the backend allows no more. */
  reconnectToken(): Promise<string>;
}
export type VoiceStatus = "connecting" | "listening" | "thinking" | "speaking" | "reconnecting";
export type VoiceEnd = "interviewer" | "local" | "failed";
export interface VoiceAgentEvents {
  status(status: VoiceStatus): void;
  transcript(role: "candidate" | "interviewer", text: string): void;
  /** Loudness in [0, 1] of each microphone frame actually sent; 0 while held, muted or not connected. */
  level?(value: number): void;
  /** Called once. `code` is a safe identifier, never transcript or provider text. */
  ended(reason: VoiceEnd, code?: string): void;
}
export interface VoiceAgentOptions { agentUrl: string; token: string; settings: Record<string, unknown>; maxReconnects: number }

export const END_FUNCTION = "end_screening";
const OPEN = 1;
const KEEPALIVE_MS = 5_000;
const END_GRACE_MS = 8_000;
const PLAYBACK_POLL_MS = 100;
// Lets room echo of the interviewer's last syllable fade before the microphone opens.
const UNMUTE_TAIL_MS = 250;
// If AgentAudioDone never arrives, silence this long after playback still opens the microphone.
const HOLD_FALLBACK_MS = 2_000;
// Text-to-speech can be slow to start; before any audio of a turn arrives, wait much longer.
const FIRST_AUDIO_FALLBACK_MS = 10_000;

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

export class VoiceAgent {
  #options: VoiceAgentOptions;
  #deps: VoiceAgentDeps;
  #events: VoiceAgentEvents;
  #socket: SocketLike | null = null;
  #microphone: MicrophoneHandle | null = null;
  #player: PlayerHandle | null = null;
  #ready = false;
  #welcomed = false;
  #muted = false;
  #agentSpeaking = false;
  #agentTurn = 0;
  #holdId = 0;
  #lastAudioAt = 0;
  #finished = false;
  #ending = false;
  #reconnects = 0;
  #history: { role: "user" | "assistant"; content: string }[] = [];
  #keepAlive: ReturnType<typeof setInterval> | null = null;
  #endTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: VoiceAgentOptions, deps: VoiceAgentDeps, events: VoiceAgentEvents) {
    this.#options = options;
    this.#deps = deps;
    this.#events = events;
  }

  /** Requests the microphone first, so a refusal fails before any billed connection opens. */
  async start(): Promise<void> {
    try {
      this.#microphone = await this.#deps.startMicrophone((frame) => this.#sendAudio(frame));
    } catch (failure) {
      this.#finish("failed", failure instanceof Error && failure.name === "NotAllowedError" ? "microphone_denied" : "microphone_unavailable");
      return;
    }
    if (this.#finished) {
      this.#microphone.stop();
      return;
    }
    this.#player = this.#deps.createPlayer();
    this.#connect(this.#options.token);
  }

  get muted(): boolean { return this.#muted; }

  setMuted(muted: boolean): void {
    this.#muted = muted;
    if (this.#keepAlive !== null) clearInterval(this.#keepAlive);
    this.#keepAlive = null;
    // Without audio frames the agent still needs a sign of life.
    if (muted) this.#keepAlive = setInterval(() => this.#sendJson({ type: "KeepAlive" }), KEEPALIVE_MS);
  }

  stop(): void { this.#finish("local"); }

  #connect(token: string): void {
    this.#ready = false;
    this.#welcomed = false;
    this.#releaseHold();
    this.#events.status(this.#reconnects ? "reconnecting" : "connecting");
    let socket: SocketLike;
    try {
      socket = this.#deps.createSocket(this.#options.agentUrl, ["bearer", token]);
    } catch {
      this.#finish("failed", "connection_failed");
      return;
    }
    socket.binaryType = "arraybuffer";
    socket.onmessage = (event) => this.#receive(socket, event.data);
    socket.onclose = () => this.#closed(socket);
    socket.onerror = () => undefined;
    this.#socket = socket;
  }

  #settings(): Record<string, unknown> {
    if (!this.#reconnects) return this.#options.settings;
    // A new connection starts a new agent conversation: carry the history, skip the greeting.
    const agent = object(this.#options.settings.agent) ? { ...this.#options.settings.agent } : {};
    delete agent.greeting;
    agent.context = { messages: this.#history.map((turn) => ({ type: "History", ...turn })) };
    return { ...this.#options.settings, agent };
  }

  #receive(socket: SocketLike, data: unknown): void {
    if (socket !== this.#socket || this.#finished) return;
    if (data instanceof ArrayBuffer) {
      this.#player?.play(data);
      // The greeting can arrive without AgentStartedSpeaking; any agent audio holds the microphone.
      this.#hold();
      this.#lastAudioAt = Date.now();
      return;
    }
    let message: unknown;
    try {
      message = typeof data === "string" ? JSON.parse(data) : null;
    } catch {
      return;
    }
    if (!object(message)) return;
    switch (message.type) {
      case "Welcome":
        this.#welcomed = true;
        this.#sendJson(this.#settings());
        break;
      case "SettingsApplied":
        this.#ready = true;
        this.#events.status("listening");
        break;
      case "ConversationText":
        if ((message.role === "user" || message.role === "assistant") && typeof message.content === "string" && message.content.trim()) {
          this.#history.push({ role: message.role, content: message.content });
          this.#events.transcript(message.role === "user" ? "candidate" : "interviewer", message.content);
        }
        break;
      case "UserStartedSpeaking":
        // Only reachable when the candidate began just before the agent; their turn wins.
        this.#player?.interrupt();
        this.#releaseHold();
        this.#events.status("listening");
        break;
      case "AgentThinking":
        if (!this.#agentSpeaking) this.#events.status("thinking");
        break;
      case "AgentStartedSpeaking":
        this.#hold();
        break;
      case "AgentAudioDone":
        // Deepgram has sent the last audio, but queued speech may still be playing.
        if (this.#ending) this.#afterPlayback(() => this.#finish("interviewer"));
        else this.#listenAfterPlayback();
        break;
      case "FunctionCallRequest":
        this.#functionCalls(message.functions);
        break;
      case "Error":
        this.#finish("failed", typeof message.code === "string" && /^[A-Za-z0-9_.-]{1,64}$/.test(message.code) ? message.code : "agent_error");
        break;
      default:
        break;
    }
  }

  #functionCalls(functions: unknown): void {
    if (!Array.isArray(functions)) return;
    for (const call of functions) {
      if (!object(call) || call.client_side !== true || typeof call.id !== "string" || typeof call.name !== "string") continue;
      const known = call.name === END_FUNCTION;
      this.#sendJson({ type: "FunctionCallResponse", id: call.id, name: call.name, content: known ? "ended" : "unsupported" });
      if (known && !this.#ending) {
        // Let the closing line finish playing before hanging up.
        this.#ending = true;
        this.#endTimer = setTimeout(() => this.#finish("interviewer"), END_GRACE_MS);
      }
    }
  }

  #afterPlayback(done: () => void): void {
    const check = () => {
      if (this.#finished) return;
      if (!this.#player || this.#player.idle()) done();
      else setTimeout(check, PLAYBACK_POLL_MS);
    };
    check();
  }

  #hold(): void {
    // Any new agent audio also cancels a pending unmute from the previous turn.
    this.#agentTurn += 1;
    if (this.#agentSpeaking) return;
    this.#agentSpeaking = true;
    this.#events.status("speaking");
    this.#watchHold();
  }

  /**
   * Releases a hold whose AgentAudioDone was lost: after the player has been idle for the fallback
   * since the last audio, or for the longer first-audio fallback when none has arrived this turn.
   */
  #watchHold(): void {
    const id = ++this.#holdId;
    const started = Date.now();
    let idleSince: number | null = null;
    const check = () => {
      if (this.#finished || !this.#agentSpeaking || id !== this.#holdId) return;
      if (this.#ending || (this.#player && !this.#player.idle())) idleSince = null;
      else {
        const now = Date.now();
        if (idleSince === null || idleSince < this.#lastAudioAt) idleSince = now;
        const limit = this.#lastAudioAt >= started ? HOLD_FALLBACK_MS : FIRST_AUDIO_FALLBACK_MS;
        if (now - idleSince >= limit) {
          this.#releaseHold();
          this.#events.status("listening");
          return;
        }
      }
      setTimeout(check, PLAYBACK_POLL_MS);
    };
    setTimeout(check, PLAYBACK_POLL_MS);
  }

  #releaseHold(): void {
    this.#agentSpeaking = false;
    this.#agentTurn += 1;
  }

  #listenAfterPlayback(): void {
    const turn = this.#agentTurn;
    this.#afterPlayback(() => setTimeout(() => {
      // A newer agent turn, an interruption or a reconnect has taken over.
      if (this.#finished || turn !== this.#agentTurn) return;
      this.#releaseHold();
      this.#events.status("listening");
    }, UNMUTE_TAIL_MS));
  }

  #sendAudio(frame: ArrayBuffer): void {
    if (!this.#ready || this.#muted || this.#socket?.readyState !== OPEN) {
      this.#events.level?.(0);
      return;
    }
    if (this.#agentSpeaking) {
      // Silence keeps the audio stream continuous without letting the microphone reach the agent.
      this.#socket.send(new ArrayBuffer(frame.byteLength));
      this.#events.level?.(0);
      return;
    }
    this.#socket.send(frame);
    this.#events.level?.(micLevel(frame));
  }

  #sendJson(message: Record<string, unknown>): void {
    if (this.#socket?.readyState === OPEN) this.#socket.send(JSON.stringify(message));
  }

  #closed(socket: SocketLike): void {
    if (socket !== this.#socket || this.#finished) return;
    if (this.#ending) {
      this.#finish("interviewer");
      return;
    }
    // A connection refused before Welcome is an authentication or protocol problem, not a dropout.
    if (!this.#welcomed) {
      this.#finish("failed", "connection_failed");
      return;
    }
    if (this.#reconnects >= this.#options.maxReconnects) {
      this.#finish("failed", "connection_lost");
      return;
    }
    this.#reconnects += 1;
    this.#socket = null;
    this.#events.status("reconnecting");
    this.#deps.reconnectToken().then(
      (token) => { if (!this.#finished) this.#connect(token); },
      () => this.#finish("failed", "connection_lost"),
    );
  }

  #finish(reason: VoiceEnd, code?: string): void {
    if (this.#finished) return;
    this.#finished = true;
    if (this.#keepAlive !== null) clearInterval(this.#keepAlive);
    if (this.#endTimer !== null) clearTimeout(this.#endTimer);
    const socket = this.#socket;
    this.#socket = null;
    if (socket) {
      socket.onmessage = socket.onclose = socket.onerror = null;
      try { socket.close(1000); } catch { /* already closed */ }
    }
    this.#microphone?.stop();
    this.#player?.close();
    this.#events.ended(reason, code);
  }
}
