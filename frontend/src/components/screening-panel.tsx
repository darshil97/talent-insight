"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  endScreening, getNotice, reconnectToken, ScreeningError, sendMessage, startScreening,
  type ScreeningCandidate, type ScreeningMode, type ScreeningNotice, type ScreeningStart,
} from "@/lib/screenings";
import { PhoneIcon } from "@/components/phone-icon";
import { VoiceAgent, type VoiceStatus } from "@/lib/voice-agent";
import { browserVoiceDeps, requestMicrophonePermission, voiceSupported } from "@/lib/voice-audio";

type Turn = { role: "candidate" | "interviewer"; text: string };
type Phase = "closed" | "consent" | "starting" | "live" | "ended";

// The backend enforces the real reconnect limit; this only stops the client asking sooner.
const MAX_RECONNECTS = 2;
const BACKSTOP_MS = 30_000;
const voiceStatusLabels: Record<VoiceStatus, string> = {
  connecting: "Connecting to the voice interviewer…",
  listening: "Listening. Speak when you are ready.",
  thinking: "The interviewer is thinking…",
  speaking: "The interviewer is speaking. You can interrupt at any time.",
  reconnecting: "Reconnecting…",
};
const voiceErrors: Record<string, string> = {
  microphone_denied: "Microphone access was blocked. Continue by text, or allow the microphone and start again.",
  microphone_unavailable: "No usable microphone was found. Continue by text.",
  connection_failed: "The voice service refused the connection. Continue by text.",
  connection_lost: "The call disconnected and could not reconnect. Continue by text.",
};

// Wall-clock reads happen only in event handlers and timers, never during render.
const clock = () => Date.now();

function remaining(deadline: number, now: number): string {
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function ScreeningPanel({ jobId, jobTitle, candidate, unavailableReason, candidateName, autoOpen = false, onLiveChange, onClose }: {
  jobId: string;
  jobTitle: string;
  candidate: ScreeningCandidate | null;
  unavailableReason?: string;
  /** Shown in the heading when the panel is opened from a candidate table. */
  candidateName?: string;
  /** Open directly at the consent step, for a Start action elsewhere on the page. */
  autoOpen?: boolean;
  /** True while a screening is starting or in progress; the backend allows one at a time. */
  onLiveChange?: (live: boolean) => void;
  onClose?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>(autoOpen && candidate ? "consent" : "closed");
  const [notice, setNotice] = useState<ScreeningNotice | null>(null);
  const [mode, setMode] = useState<ScreeningMode>("voice");
  const [aiConsent, setAiConsent] = useState(false);
  const [audioConsent, setAudioConsent] = useState(false);
  const [channel, setChannel] = useState<ScreeningMode>("text");
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("connecting");
  const [muted, setMuted] = useState(false);
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [voiceLost, setVoiceLost] = useState(false);
  const [deadline, setDeadline] = useState(0);
  const [now, setNow] = useState(0);
  const panel = useRef<HTMLElement>(null);
  const session = useRef<ScreeningStart | null>(null);
  const voice = useRef<VoiceAgent | null>(null);
  const requests = useRef<AbortController | null>(null);
  const backstop = useRef<ReturnType<typeof setTimeout> | null>(null);

  const release = useCallback(() => {
    voice.current?.stop();
    voice.current = null;
    requests.current?.abort();
    requests.current = null;
    if (backstop.current !== null) clearTimeout(backstop.current);
    backstop.current = null;
    if (session.current) endScreening(session.current);
    session.current = null;
  }, []);

  const finish = useCallback((message?: string) => {
    release();
    setSending(false);
    if (message) setError(message);
    setPhase("ended");
  }, [release]);

  const reset = useCallback(() => {
    release();
    setPhase("closed");
    setNotice(null);
    setTranscript([]);
    setDraft("");
    setError("");
    setVoiceLost(false);
    setMuted(false);
    setAiConsent(false);
    setAudioConsent(false);
  }, [release]);

  // Screening text is temporary: unmount, page hide and back/forward restoration discard it.
  useEffect(() => {
    const discard = () => reset();
    const restored = (event: PageTransitionEvent) => { if (event.persisted) reset(); };
    window.addEventListener("pagehide", discard);
    window.addEventListener("pageshow", restored);
    return () => {
      window.removeEventListener("pagehide", discard);
      window.removeEventListener("pageshow", restored);
      release();
    };
  }, [release, reset]);

  useEffect(() => {
    if (phase !== "live") return;
    const timer = setInterval(() => setNow(clock()), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase === "consent" || phase === "live") panel.current?.focus();
  }, [phase]);

  /** Loads the server notice; state changes happen only in the promise callbacks. */
  const loadNotice = useCallback(() => {
    requests.current?.abort();
    const controller = new AbortController();
    requests.current = controller;
    getNotice(controller.signal).then(
      (loaded) => {
        if (controller.signal.aborted) return;
        setNotice(loaded);
        setMode(loaded.voice_available && voiceSupported() ? "voice" : "text");
      },
      (failure: unknown) => {
        if (!controller.signal.aborted) setError(failure instanceof ScreeningError ? failure.message : "Screening is unavailable.");
      },
    );
  }, []);

  useEffect(() => {
    if (autoOpen && candidate) loadNotice();
    // Opened once per mount; a different candidate remounts the panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    onLiveChange?.(phase === "starting" || phase === "live");
  }, [phase, onLiveChange]);

  useEffect(() => () => onLiveChange?.(false), [onLiveChange]);

  function open() {
    setError("");
    setPhase("consent");
    loadNotice();
  }

  function close() {
    reset();
    onClose?.();
  }

  function addTurn(turn: Turn) {
    setTranscript((turns) => [...turns, turn]);
  }

  async function begin() {
    if (!notice || !candidate) return;
    setError("");
    setPhase("starting");
    if (mode === "voice") {
      try {
        await requestMicrophonePermission();
      } catch {
        setError(voiceErrors.microphone_denied);
        setPhase("consent");
        return;
      }
    }
    const controller = new AbortController();
    requests.current = controller;
    let started: ScreeningStart;
    try {
      started = await startScreening(jobId, candidate, mode, notice, controller.signal);
    } catch (failure) {
      if (controller.signal.aborted) return;
      setError(failure instanceof ScreeningError ? failure.message : "Screening could not start.");
      setPhase("consent");
      return;
    }
    if (controller.signal.aborted) {
      endScreening(started);
      return;
    }
    session.current = started;
    const start = clock();
    setDeadline(start + started.screening_seconds * 1000);
    setNow(start);
    setTranscript(mode === "text" ? [{ role: "interviewer", text: started.greeting }] : []);
    setChannel(mode);
    setVoiceLost(false);
    setPhase("live");
    // The interviewer closes the call at the limit; this stops a client that kept it open.
    backstop.current = setTimeout(() => finish("The screening time limit was reached."), started.screening_seconds * 1000 + BACKSTOP_MS);
    if (mode === "voice" && started.agent_url && started.deepgram_token && started.settings) startVoice(started);
  }

  function startVoice(started: ScreeningStart) {
    const agent = new VoiceAgent(
      { agentUrl: started.agent_url!, token: started.deepgram_token!, settings: started.settings!, maxReconnects: MAX_RECONNECTS },
      browserVoiceDeps(async () => (await reconnectToken(started, requests.current?.signal ?? new AbortController().signal)).deepgram_token),
      {
        status: setVoiceStatus,
        transcript: (role, text) => addTurn({ role, text }),
        ended: (reason, code) => {
          if (voice.current !== agent) return;
          voice.current = null;
          if (reason === "interviewer") finish();
          else if (reason === "failed") {
            setVoiceLost(true);
            setError(voiceErrors[code ?? ""] ?? "The voice service reported a problem. Continue by text.");
          }
        },
      },
    );
    voice.current = agent;
    void agent.start();
  }

  function switchToText() {
    voice.current?.stop();
    voice.current = null;
    setChannel("text");
    setVoiceLost(false);
    setError("");
  }

  function toggleMute() {
    const next = !muted;
    voice.current?.setMuted(next);
    setMuted(next);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    const active = session.current;
    if (!text || sending || !active) return;
    setSending(true);
    setError("");
    addTurn({ role: "candidate", text });
    setDraft("");
    const controller = new AbortController();
    requests.current = controller;
    try {
      const reply = await sendMessage(active, text, controller.signal);
      if (controller.signal.aborted) return;
      if (reply.reply) addTurn({ role: "interviewer", text: reply.reply });
      if (reply.ended) finish();
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof ScreeningError ? failure.message : "The message could not be sent. Try again.");
    } finally {
      if (!controller.signal.aborted) setSending(false);
    }
  }

  if (phase === "closed") {
    return (
      <section aria-labelledby="screening-heading" className="mission-screening">
        <div className="mission-screening-top">
          <div>
            <p className="mission-kicker">OPTIONAL / ABOUT 10 MINUTES</p>
            <h2 id="screening-heading">AI screening conversation{candidateName ? ` · ${candidateName}` : ""}</h2>
            <p>A consent-based voice or text conversation about job-related requirements for {jobTitle}. A recruiter reviews it; the AI makes no decision.</p>
          </div>
          <button type="button" className="mission-button" disabled={!candidate} onClick={open}><PhoneIcon />Start screening</button>
        </div>
        {!candidate && <p className="mission-help">{unavailableReason ?? "Screening is not available for this candidate."}</p>}
      </section>
    );
  }

  const live = phase === "live";
  return (
    <section ref={panel} tabIndex={-1} aria-labelledby="screening-heading" className="mission-screening">
      <div className="mission-screening-top">
        <div>
          <p className="mission-kicker">{live ? `${channel === "voice" ? "VOICE" : "TEXT"} SCREENING / ${remaining(deadline, now)} LEFT` : "SCREENING"}</p>
          <h2 id="screening-heading">AI screening conversation{candidateName ? ` · ${candidateName}` : ""}</h2>
        </div>
        {(phase === "consent" || phase === "ended") && <button type="button" className="mission-outline-button" onClick={close}>Close</button>}
      </div>

      {(phase === "consent" || phase === "starting") && (
        notice ? <form className="mission-screening-consent" onSubmit={(event) => { event.preventDefault(); void begin(); }}>
          <p className="mission-screening-notice">{notice.text}</p>
          <fieldset className="mission-fieldset">
            <legend>How to take part</legend>
            <label className="mission-choice"><input type="radio" name="screening-mode" value="voice" checked={mode === "voice"} disabled={!notice.voice_available || !voiceSupported()} onChange={() => setMode("voice")} />Voice conversation (microphone)</label>
            <label className="mission-choice"><input type="radio" name="screening-mode" value="text" checked={mode === "text"} onChange={() => setMode("text")} />Text conversation</label>
            {(!notice.voice_available || !voiceSupported()) && <p className="mission-help">{notice.voice_available ? "This browser cannot capture audio here; use text." : "Voice is turned off on the backend; text is available."}</p>}
          </fieldset>
          <label className="mission-choice"><input type="checkbox" checked={aiConsent} onChange={(event) => setAiConsent(event.target.checked)} />I agree to the conversation being processed by AI as described above.</label>
          {mode === "voice" && <label className="mission-choice"><input type="checkbox" checked={audioConsent} onChange={(event) => setAudioConsent(event.target.checked)} />I agree to my microphone audio being captured for this conversation.</label>}
          <button type="submit" className="mission-button" disabled={phase === "starting" || !aiConsent || (mode === "voice" && !audioConsent)}>{phase === "starting" ? "Starting…" : "Agree and start"}</button>
        </form> : !error && <p role="status" className="mission-help">Loading the screening notice…</p>
      )}

      {(live || phase === "ended") && (
        <ol className="mission-transcript" role="log" aria-live="polite" aria-label="Screening transcript">
          {transcript.map((turn, index) => (
            <li key={index} className={turn.role === "candidate" ? "mission-turn-candidate" : "mission-turn-interviewer"}>
              <span>{turn.role === "candidate" ? "Candidate" : "Interviewer"}</span>{turn.text}
            </li>
          ))}
          {live && channel === "voice" && !transcript.length && <li className="mission-turn-interviewer"><span>Interviewer</span>The greeting will play shortly.</li>}
        </ol>
      )}

      {live && channel === "voice" && (
        <div className="mission-screening-controls">
          <p role="status" className="mission-help">{voiceLost ? "Voice is disconnected." : muted ? "Microphone muted." : voiceStatusLabels[voiceStatus]}</p>
          {!voiceLost && <button type="button" className="mission-outline-button" onClick={toggleMute} aria-pressed={muted}>{muted ? "Unmute" : "Mute"}</button>}
          <button type="button" className="mission-outline-button" onClick={switchToText}>Continue by text</button>
          <button type="button" className="mission-outline-button" onClick={() => finish()}>End screening</button>
        </div>
      )}

      {live && channel === "text" && (
        <form className="mission-screening-reply" onSubmit={send}>
          <label htmlFor="screening-answer">Your answer</label>
          <textarea id="screening-answer" value={draft} maxLength={2000} rows={3} onChange={(event) => setDraft(event.target.value)} disabled={sending} />
          <div className="mission-screening-controls">
            <button type="submit" className="mission-button" disabled={sending || !draft.trim()}>{sending ? "Waiting for the interviewer…" : "Send"}</button>
            <button type="button" className="mission-outline-button" onClick={() => finish()}>End screening</button>
          </div>
        </form>
      )}

      {phase === "ended" && <p role="status" className="mission-review-note">Screening ended. A recruiter will review this conversation; the structured report is a later module. This transcript is temporary and clears when you close it or leave the page.</p>}
      {error && <p role="alert" className="mission-error">{error}</p>}
    </section>
  );
}
