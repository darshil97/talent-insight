/** Linear PCM helpers for the voice screening: microphone samples out, agent speech in. */

/** Float samples in [-1, 1] to little-endian 16-bit PCM, clipping out-of-range values. */
export function floatToInt16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index]));
    output[index] = sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff);
  }
  return output;
}

export function int16ToFloat(input: Int16Array): Float32Array {
  const output = new Float32Array(input.length);
  for (let index = 0; index < input.length; index += 1) output[index] = input[index] / (input[index] < 0 ? 0x8000 : 0x7fff);
  return output;
}

const LEVEL_FLOOR_DB = -55;
const LEVEL_CEILING_DB = -15;

/** Loudness of a 16-bit PCM frame in [0, 1]: RMS in dBFS mapped linearly from -55 dB to -15 dB. */
export function micLevel(bytes: ArrayBuffer): number {
  const samples = new Int16Array(bytes, 0, Math.floor(bytes.byteLength / 2));
  if (!samples.length) return 0;
  let sum = 0;
  for (const sample of samples) sum += (sample / 0x8000) ** 2;
  const rms = Math.sqrt(sum / samples.length);
  if (rms === 0) return 0;
  const db = 20 * Math.log10(rms);
  return Math.max(0, Math.min(1, (db - LEVEL_FLOOR_DB) / (LEVEL_CEILING_DB - LEVEL_FLOOR_DB)));
}

/** Agent audio as samples; a trailing odd byte from a split frame is dropped. */
export function pcmBytesToFloat(bytes: ArrayBuffer): Float32Array {
  return int16ToFloat(new Int16Array(bytes, 0, Math.floor(bytes.byteLength / 2)));
}

/**
 * Average-and-decimate from the device rate to the agent's input rate, keeping state across
 * chunks. The averaging window acts as a simple low-pass filter before decimation.
 */
export function createDownsampler(inputRate: number, outputRate = 16_000): (input: Float32Array) => Float32Array {
  if (!Number.isFinite(inputRate) || !Number.isFinite(outputRate) || outputRate <= 0 || inputRate < outputRate) {
    throw new RangeError("The input rate must be at least the output rate.");
  }
  const step = inputRate / outputRate;
  let boundary = step;
  let consumed = 0;
  let sum = 0;
  let count = 0;
  return (input) => {
    const output: number[] = [];
    for (const sample of input) {
      sum += sample;
      count += 1;
      consumed += 1;
      if (consumed >= boundary) {
        output.push(sum / count);
        sum = 0;
        count = 0;
        boundary += step;
      }
    }
    return Float32Array.from(output);
  };
}
