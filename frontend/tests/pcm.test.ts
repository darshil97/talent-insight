import assert from "node:assert/strict";
import { test } from "node:test";
import { createDownsampler, floatToInt16, int16ToFloat, micLevel, pcmBytesToFloat } from "../src/lib/pcm.ts";

test("float samples convert to clipped 16-bit PCM and back", () => {
  assert.deepEqual(Array.from(floatToInt16(new Float32Array([0, 1, -1, 0.5, 2, -3]))), [0, 32767, -32768, 16384, 32767, -32768]);
  const back = int16ToFloat(new Int16Array([0, 32767, -32768]));
  assert.deepEqual(Array.from(back), [0, 1, -1]);
});

test("agent audio bytes drop a trailing odd byte", () => {
  const bytes = new Uint8Array([0xff, 0x7f, 0x00, 0x80, 0x01]).buffer;
  assert.deepEqual(Array.from(pcmBytesToFloat(bytes)), [1, -1]);
});

test("downsampling averages windows and keeps state across chunks", () => {
  const downsample = createDownsampler(48_000, 16_000);
  assert.deepEqual(Array.from(downsample(new Float32Array([0.3, 0.3, 0.3, 0.6]))), [0.30000001192092896]);
  // The fourth sample starts the next window, completed by the next chunk.
  assert.deepEqual(Array.from(downsample(new Float32Array([0.6, 0.6]))).map((v) => Number(v.toFixed(5))), [0.6]);
  const odd = createDownsampler(44_100, 16_000);
  const total = [0, 1, 2, 3].reduce((sum) => sum + odd(new Float32Array(441)).length, 0);
  assert.equal(total, 640);
  assert.throws(() => createDownsampler(8_000, 16_000), RangeError);
});

test("microphone level maps frame loudness to [0, 1]", () => {
  assert.equal(micLevel(new ArrayBuffer(0)), 0);
  assert.equal(micLevel(new Int16Array(640).buffer), 0);
  assert.equal(micLevel(new Int16Array(640).fill(0x7fff).buffer), 1);
  // About -35 dBFS sits in the middle of the -55 to -15 dB range.
  const middle = micLevel(new Int16Array(640).fill(Math.round(0x8000 * 10 ** (-35 / 20))).buffer);
  assert.ok(middle > 0.45 && middle < 0.55);
  assert.equal(micLevel(new Int16Array(640).fill(3).buffer), 0);
});
