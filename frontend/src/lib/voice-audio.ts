/** Browser audio for the voice screening: microphone capture at 16 kHz and agent playback at 24 kHz. */
import { createDownsampler, floatToInt16, pcmBytesToFloat } from "./pcm.ts";
import type { MicrophoneHandle, PlayerHandle, SocketLike, VoiceAgentDeps } from "./voice-agent.ts";

const INPUT_RATE = 16_000;
const OUTPUT_RATE = 24_000;
// Echo cancellation keeps the agent's own voice out of the transcript when speakers are used.
const CONSTRAINTS: MediaStreamConstraints = { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } };

export function voiceSupported(): boolean {
  return typeof window !== "undefined" && window.isSecureContext && typeof WebSocket !== "undefined" &&
    typeof AudioContext !== "undefined" && typeof AudioWorkletNode !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

/** Ask for microphone permission before a session exists, so the 30-second token is not spent waiting. */
export async function requestMicrophonePermission(): Promise<void> {
  const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
  stream.getTracks().forEach((track) => track.stop());
}

export async function startMicrophone(onFrame: (pcm: ArrayBuffer) => void): Promise<MicrophoneHandle> {
  const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
  let context: AudioContext | null = null;
  try {
    let source: MediaStreamAudioSourceNode;
    let downsample: ((input: Float32Array) => Float32Array) | null = null;
    try {
      // Let the browser resample where it can; some browsers refuse a cross-rate source.
      context = new AudioContext({ sampleRate: INPUT_RATE });
      source = context.createMediaStreamSource(stream);
    } catch {
      await context?.close().catch(() => undefined);
      context = new AudioContext();
      source = context.createMediaStreamSource(stream);
      downsample = createDownsampler(context.sampleRate, INPUT_RATE);
    }
    await context.audioWorklet.addModule("/voice/mic-processor.js");
    const node = new AudioWorkletNode(context, "mic-processor");
    const silent = context.createGain();
    silent.gain.value = 0;
    node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      const pcm = floatToInt16(downsample ? downsample(event.data) : event.data);
      if (pcm.length) onFrame(pcm.buffer as ArrayBuffer);
    };
    // A silent path to the destination keeps the worklet running without monitoring the microphone.
    source.connect(node).connect(silent).connect(context.destination);
    await context.resume();
    const running = context;
    return {
      stop() {
        node.port.onmessage = null;
        source.disconnect();
        node.disconnect();
        stream.getTracks().forEach((track) => track.stop());
        void running.close().catch(() => undefined);
      },
    };
  } catch (failure) {
    stream.getTracks().forEach((track) => track.stop());
    await context?.close().catch(() => undefined);
    throw failure;
  }
}

export function createPlayer(): PlayerHandle {
  const context = new AudioContext({ sampleRate: OUTPUT_RATE });
  const sources = new Set<AudioBufferSourceNode>();
  let playhead = 0;
  return {
    play(chunk) {
      const samples = pcmBytesToFloat(chunk);
      if (!samples.length || context.state === "closed") return;
      void context.resume().catch(() => undefined);
      const buffer = context.createBuffer(1, samples.length, OUTPUT_RATE);
      buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
      const node = context.createBufferSource();
      node.buffer = buffer;
      node.connect(context.destination);
      const start = Math.max(playhead, context.currentTime + 0.02);
      node.start(start);
      playhead = start + buffer.duration;
      sources.add(node);
      node.onended = () => sources.delete(node);
    },
    interrupt() {
      for (const node of sources) {
        try { node.stop(); } catch { /* not started yet */ }
      }
      sources.clear();
      playhead = 0;
    },
    idle: () => sources.size === 0,
    close() {
      this.interrupt();
      void context.close().catch(() => undefined);
    },
  };
}

export function browserVoiceDeps(reconnectToken: () => Promise<string>): VoiceAgentDeps {
  return {
    createSocket: (url, protocols) => new WebSocket(url, protocols) as unknown as SocketLike,
    startMicrophone,
    createPlayer,
    reconnectToken,
  };
}
