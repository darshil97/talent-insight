// Batches mono microphone samples into ~40 ms frames for the voice screening page.
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Float32Array(Math.round(sampleRate / 25));
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      let offset = 0;
      while (offset < channel.length) {
        const take = Math.min(channel.length - offset, this.frame.length - this.filled);
        this.frame.set(channel.subarray(offset, offset + take), this.filled);
        this.filled += take;
        offset += take;
        if (this.filled === this.frame.length) {
          this.port.postMessage(this.frame.slice(0));
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
