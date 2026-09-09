/**
 * AudioWorklet: 16kHz → 512 样本/帧 (32ms) → 批量缓冲 → 主线程
 */
class VADAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(512);
    this.bufferIndex = 0;
    this.batchBuffer = [];
    this.batchSize = 5;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0][0];
    if (!input) return true;

    for (let i = 0; i < input.length; i++) {
      this.buffer[this.bufferIndex++] = input[i];
      
      if (this.bufferIndex >= 512) {
        this.batchBuffer.push(this.buffer.slice());
        this.bufferIndex = 0;
        
        if (this.batchBuffer.length >= this.batchSize) {
          this.port.postMessage({
            type: 'batch',
            frames: this.batchBuffer.map(f => Array.from(f))
          });
          this.batchBuffer = [];
        }
      }
    }
    return true;
  }
}

registerProcessor('vad-processor', VADAudioProcessor);
