const path = require('path');
const fs = require('fs');

class VADEngine {
  constructor() {
    this.session = null;
    this.ort = null;
    this.modelPath = '';
    this.useFallback = false;
    
    // 能量检测参数（降级方案）
    this.energyHistory = [];
    this.ENERGY_WINDOW = 10;
    this.SPEECH_ENERGY_THRESHOLD = 0.02;
    this.SILENCE_ENERGY_THRESHOLD = 0.005;
    
    // 状态机
    this.speechBuffer = [];
    this.MIN_SPEECH_FRAMES = 3;
    this.MAX_SILENCE_FRAMES = 5;
    this.silenceFrames = 0;
    this.isSpeaking = false;
    
    // 回调函数
    this.callbacks = {
      onSpeechStart: null,
      onSpeechEnd: null
    };
  }

  async init() {
    // 尝试加载 ONNX Runtime
    try {
      this.ort = require('onnxruntime-node');
      this.modelPath = path.join(process.cwd(), 'models', 'silero_vad.onnx');
      
      // 检查模型文件是否存在
      if (!fs.existsSync(this.modelPath)) {
        console.log('[VAD] Model not found, using energy-based fallback');
        this.useFallback = true;
        return;
      }
      
      // 尝试加载模型
      try {
        this.session = await this.ort.InferenceSession.create(this.modelPath);
        console.log('[VAD] Silero VAD model loaded from:', this.modelPath);
      } catch (loadErr) {
        console.log('[VAD] Failed to load model, using energy-based fallback');
        this.useFallback = true;
      }
    } catch (ortErr) {
      console.log('[VAD] ONNX Runtime not available, using energy-based fallback');
      this.useFallback = true;
    }
  }

  async process(frame) {
    if (this.useFallback) {
      return this.processEnergyBased(frame);
    }
    
    if (!this.session) {
      return this.processEnergyBased(frame);
    }
    
    try {
      // Silero VAD expects 512 samples at 16kHz = 32ms frame
      const inputTensor = new this.ort.Tensor('float32', frame, [1, frame.length]);
      const results = await this.session.run({ input: inputTensor });
      const prob = results[0].data[0];
      
      // 状态机逻辑
      const triggered = prob > 0.5;
      return {
        triggered,
        isSpeech: triggered,
        prob,
      };
    } catch (err) {
      console.error('[VAD] Process error:', err);
      return this.processEnergyBased(frame);
    }
  }

  processEnergyBased(frame) {
    // 计算 RMS 能量
    let sum = 0;
    for (let i = 0; i < frame.length; i++) {
      sum += frame[i] * frame[i];
    }
    const energy = Math.sqrt(sum / frame.length);
    
    // 维护历史
    this.energyHistory.push(energy);
    if (this.energyHistory.length > this.ENERGY_WINDOW) {
      this.energyHistory.shift();
    }
    
    // 计算平均能量
    const avgEnergy = this.energyHistory.reduce((a, b) => a + b, 0) / this.energyHistory.length;
    
    // 简单的双阈值状态机
    if (this.isSpeaking) {
      if (energy < this.SILENCE_ENERGY_THRESHOLD) {
        this.silenceFrames++;
        if (this.silenceFrames >= this.MAX_SILENCE_FRAMES) {
          this.isSpeaking = false;
          this.silenceFrames = 0;
          if (this.callbacks.onSpeechEnd) {
            this.callbacks.onSpeechEnd();
          }
        }
      } else {
        this.silenceFrames = 0;
      }
    } else {
      if (energy > this.SPEECH_ENERGY_THRESHOLD && energy > avgEnergy * 1.5) {
        this.isSpeaking = true;
        this.silenceFrames = 0;
        if (this.callbacks.onSpeechStart) {
          this.callbacks.onSpeechStart();
        }
      }
    }
    
    return {
      triggered: this.isSpeaking,
      isSpeech: this.isSpeaking,
      prob: Math.min(1, energy * 10),
    };
  }

  setCallbacks(callbacks) {
    this.callbacks = callbacks || {};
  }

  reset() {
    this.energyHistory = [];
    this.speechBuffer = [];
    this.silenceFrames = 0;
    this.isSpeaking = false;
  }
}

module.exports = { VADEngine };