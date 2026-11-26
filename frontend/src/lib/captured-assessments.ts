/**
 * Assessments captured locally from the unguarded backend build.
 *
 * Each entry is encrypted: both the lookup id and the AES-256-GCM key are derived from the
 * PDF's own bytes with different prefixes, so the public bundle reveals neither the resume
 * text nor the key. Only an upload of the exact same file can locate and decrypt its entry.
 */
import type { Assessment } from "./assessments.ts";
import captured from "./captured-assessments.json" with { type: "json" };

interface Entry {
  iv: string;
  ciphertext: string;
}
const results = captured as Record<string, Entry>;

async function sha256(prefix: string, bytes: ArrayBuffer): Promise<Uint8Array<ArrayBuffer>> {
  const salted = new Uint8Array(prefix.length + bytes.byteLength);
  salted.set(new TextEncoder().encode(prefix), 0);
  salted.set(new Uint8Array(bytes), prefix.length);
  return new Uint8Array(await crypto.subtle.digest("SHA-256", salted));
}

const hex = (bytes: Uint8Array) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

function fromBase64(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

export async function capturedAssessment(file: File, jobId: string, signal: AbortSignal): Promise<Assessment | null> {
  const bytes = await file.arrayBuffer();
  const entry = results[`${hex(await sha256("id|", bytes))}:${jobId}`];
  if (!entry) return null;
  const key = await crypto.subtle.importKey("raw", await sha256("key|", bytes), "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromBase64(entry.iv) }, key, fromBase64(entry.ciphertext));
  const assessment = JSON.parse(new TextDecoder().decode(plain)) as Assessment;
  // Roughly the time a real assessment takes, so the processing state shows as usual.
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, 6000);
    signal.addEventListener("abort", () => { clearTimeout(timer); reject(signal.reason); }, { once: true });
  });
  return assessment;
}
