"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  endScreening, getNotice, reconnectToken, ScreeningError, sendMessage, startScreening, voiceErrorMessage, appendTurn, requestReport,
  type ScreeningCandidate, type ScreeningMode, type TranscriptTurn, type ScreeningReport, type ScreeningNotice, type ScreeningStart,
} from "@/lib/screenings";
import { MicIcon } from "@/components/mic-icon";
import { PhoneIcon } from "@/components/phone-icon";
import { ScreeningReportView } from "@/components/screening-report";
import { VoiceAgent, type VoiceStatus } from "@/lib/voice-agent";
import { browserVoiceDeps, requestMicrophonePermission, voiceSupported } from "@/lib/voice-audio";

type Phase = "closed" | "consent" | "starting" | "live" | "ended";
type ReportState = { state: "idle" | "loading" } | { state: "ready"; report: ScreeningReport } | { state: "error"; message: string };

// The backend enforces the real reconnect limit; this only stops the client asking sooner.
const MAX_RECONNECTS = 2;
const BACKSTOP_MS = 30_000;
// The meter rises with each louder frame and falls back gradually, so speech reads as a steady glow.
const LEVEL_DECAY = 0.85;
const voiceStatusLabels: Record<VoiceStatus, string> = {
  connecting: "Connecting to the voice interviewer…",
  listening: "Listening. Start speaking whenever you're ready.",
  thinking: "The interviewer is thinking…",
  speaking: "The interviewer is speaking. You're muted until they finish.",
  reconnecting: "Reconnecting…",
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
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [voiceLost, setVoiceLost] = useState(false);
  const [deadline, setDeadline] = useState(0);
  const [now, setNow] = useState(0);
  const [report, setReport] = useState<ReportState>({ state: "idle" });
  const panel = useRef<HTMLElement>(null);
  const log = useRef<HTMLOListElement>(null);
  // Follow new lines only while the reader is at the bottom, so scrolling back is not undone.
  const following = useRef(true);
  const session = useRef<ScreeningStart | null>(null);
  const voice = useRef<VoiceAgent | null>(null);
  const requests = useRef<AbortController | null>(null);
  const backstop = useRef<ReturnType<typeof setTimeout> | null>(null);
  const micButton = useRef<HTMLButtonElement>(null);
  const micLevel = useRef(0);
  const reportRequest = useRef<AbortController | null>(null);
  const endedSession = useRef<ScreeningStart | null>(null);

  const release = useCallback(() => {
    voice.current?.stop();
    voice.current = null;
    requests.current?.abort();
    requests.current = null;
    if (backstop.current !== null) clearTimeout(backstop.current);
    backstop.current = null;
    if (session.current) endScreening(session.current);
    session.current = null;
    reportRequest.current?.abort();
    reportRequest.current = null;
  }, []);

  /** The report lives only in this component's state; the backend keeps it in memory until expiry. */
  const loadReport = useCallback((ended: ScreeningStart) => {
    reportRequest.current?.abort();
    const controller = new AbortController();
    reportRequest.current = controller;
    setReport({ state: "loading" });
    requestReport(ended, jobId, controller.signal).then(
      (loaded) => { if (!controller.signal.aborted) setReport({ state: "ready", report: loaded }); },
      (failure: unknown) => {
        if (!controller.signal.aborted) setReport({ state: "error", message: failure instanceof ScreeningError ? failure.message : "The report could not be prepared. Try again." });
      },
    );
  }, [jobId]);

  const finish = useCallback((message?: string) => {
    const ended = session.current;
    release();
    setSending(false);
    if (message) setError(message);
    setPhase("ended");
    endedSession.current = ended;
    if (ended) loadReport(ended);
  }, [release, loadReport]);

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
    setReport({ state: "idle" });
    endedSession.current = null;
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

  useEffect(() => {
    const element = log.current;
    if (element && following.current) element.scrollTop = element.scrollHeight;
  }, [transcript]);

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

  function addTurn(turn: TranscriptTurn) {
    setTranscript((turns) => appendTurn(turns, turn));
  }

  async function begin() {
    if (!notice || !candidate) return;
    setError("");
    setPhase("starting");
    if (mode === "voice") {
      try {
        await requestMicrophonePermission();
      } catch {
        setError(voiceErrorMessage("microphone_denied"));
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
    following.current = true;
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
        // About 25 updates a second go straight to a CSS variable, without re-rendering the transcript.
        level: (value) => {
          micLevel.current = Math.max(value, micLevel.current * LEVEL_DECAY);
          micButton.current?.style.setProperty("--mic-level", micLevel.current.toFixed(3));
        },
        ended: (reason, code) => {
          if (voice.current !== agent) return;
          voice.current = null;
          if (reason === "interviewer") finish();
          else if (reason === "failed") {
            setVoiceLost(true);
            setError(voiceErrorMessage(code));
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
  const held = voiceStatus === "speaking";
  const micState = muted ? "muted" : held ? "held" : "live";
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
        <ol
          ref={log}
          className="mission-transcript"
          role="log"
          aria-live="polite"
          aria-label="Screening transcript"
          onScroll={(event) => {
            const element = event.currentTarget;
            following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
          }}
        >
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
          {!voiceLost && (
            <button type="button" ref={micButton} className="mission-mic" data-state={micState} onClick={toggleMute} aria-pressed={muted} aria-label={muted ? "Unmute microphone" : "Mute microphone"} title={muted ? "Unmute microphone" : "Mute microphone"}>
              <MicIcon off={micState !== "live"} />
            </button>
          )}
          <p role="status" className="mission-help">{voiceLost ? "Voice is disconnected." : held ? voiceStatusLabels.speaking : muted ? "Microphone muted." : voiceStatusLabels[voiceStatus]}</p>
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

      {phase === "ended" && <p role="status" className="mission-review-note">Screening ended. Nothing from this conversation is stored: the transcript and report are discarded when you close this panel, refresh or leave the page.</p>}
      {phase === "ended" && report.state === "loading" && <p role="status" className="mission-help">Preparing the screening report… this can take up to a minute.</p>}
      {phase === "ended" && report.state === "error" && (
        <div className="mission-screening-controls">
          <p role="alert" className="mission-error">{report.message}</p>
          <button type="button" className="mission-outline-button" onClick={() => { if (endedSession.current) loadReport(endedSession.current); }}>Try again</button>
        </div>
      )}
      {phase === "ended" && report.state === "ready" && <ScreeningReportView report={report.report} />}
      {error && <p role="alert" className="mission-error">{error}</p>}
    </section>
  );
}
