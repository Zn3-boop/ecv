import * as path from 'path';
import * as fs from 'fs';

export interface VADCallbacks {
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
}

export class VADEngine {
  private session: any = null;
  private h: any = null;
  private c: any = null;
  private sr: any = null;
  private ort: any = null;

  private speechFrames = 0;
  private silenceFrames = 0;
  private isSpeaking = false;

  // 阈值配置（可调）
  private readonly SPEECH_THRESHOLD = 0.5;
  private readonly SPEECH_FRAMES_REQUIRED = 3;   // 约 100ms 确认开始
  private readonly SILENCE_FRAMES_REQUIRED = 15;  // 约 500ms 确认结束（关键参数）
  private readonly FRAME_SIZE = 512;

  private callbacks: VADCallbacks = {};
  private useFallback: boolean = false;

  // 能量检测参数（降级方案）
  private energyHistory: number[] = [];
  private readonly ENERGY_WINDOW = 10;
  private readonly SPEECH_ENERGY_THRESHOLD = 0.02;
  private readonly SILENCE_ENERGY_THRESHOLD = 0.005;

  async init(): Promise<void> {
    // 尝试加载 ONNX Runtime
    try {
      this.ort = await import('onnxruntime-node');
      const modelPath = path.join(process.cwd(), 'models', 'silero_vad.onnx');

      if (!fs.existsSync(modelPath)) {
        console.log('[VAD] Model not found, using energy-based fallback');
        this.useFallback = true;
        return;
      }

      this.session = await this.ort.InferenceSession.create(modelPath, {
        executionProviders: ['cpu'],
        graphOptimizationLevel: 'all'
      });

      const hData = new Float32Array(2 * 1 * 64).fill(0);
      const cData = new Float32Array(2 * 1 * 64).fill(0);
      this.h = new this.ort.Tensor('float32', hData, [2, 1, 64]);
      this.c = new this.ort.Tensor('float32', cData, [2, 1, 64]);
      this.sr = new this.ort.Tensor('int64', BigInt(16000), [1]);

      console.log('[VAD] Silero VAD 模型加载完成');
    } catch (ortErr) {
      console.log('[VAD] ONNX Runtime 不可用，使用能量检测降级方案');
      this.useFallback = true;
    }
  }

  setCallbacks(callbacks: VADCallbacks): void {
    this.callbacks = callbacks;
  }

  async process(frame: Float32Array): Promise<{ isSpeech: boolean; prob: number }> {
    if (this.useFallback || !this.session) {
      return this.processEnergyBased(frame);
    }

    try {
      const input = new this.ort.Tensor('float32', frame, [1, this.FRAME_SIZE]);
      const feeds = { input, sr: this.sr!, h: this.h, c: this.c };
      const results = await this.session.run(feeds);
      const prob = (results.output.data as Float32Array)[0];

      if (results.hn) this.h = results.hn;
      if (results.cn) this.c = results.cn;

      return this.processResult(prob);
    } catch (err) {
      console.error('[VAD] Process error:', err);
      return this.processEnergyBased(frame);
    }
  }

  private processResult(prob: number): { isSpeech: boolean; prob: number } {
    let triggered = false;

    if (prob > this.SPEECH_THRESHOLD) {
      this.speechFrames++;
      this.silenceFrames = 0;

      if (!this.isSpeaking && this.speechFrames >= this.SPEECH_FRAMES_REQUIRED) {
        this.isSpeaking = true;
        triggered = true;
        this.callbacks.onSpeechStart?.();
        console.log('[VAD] 🔴 语音开始');
      }
    } else {
      this.silenceFrames++;
      this.speechFrames = 0;

      if (this.isSpeaking && this.silenceFrames >= this.SILENCE_FRAMES_REQUIRED) {
        this.isSpeaking = false;
        triggered = true;
        this.callbacks.onSpeechEnd?.();
        console.log('[VAD] ⚪ 语音结束');
      }
    }

    return { isSpeech: this.isSpeaking, prob };
  }

  private processEnergyBased(frame: Float32Array): { isSpeech: boolean; prob: number } {
    let sum = 0;
    for (let i = 0; i < frame.length; i++) {
      sum += frame[i] * frame[i];
    }
    const energy = Math.sqrt(sum / frame.length);

    this.energyHistory.push(energy);
    if (this.energyHistory.length > this.ENERGY_WINDOW) {
      this.energyHistory.shift();
    }

    const avgEnergy = this.energyHistory.reduce((a, b) => a + b, 0) / this.energyHistory.length;

    const prob = Math.min(1, energy * 10);

    if (this.isSpeaking) {
      if (energy < this.SILENCE_ENERGY_THRESHOLD) {
        this.silenceFrames++;
        if (this.silenceFrames >= this.SILENCE_FRAMES_REQUIRED) {
          this.isSpeaking = false;
          this.callbacks.onSpeechEnd?.();
          console.log('[VAD] ⚪ 语音结束 (能量)');
        }
      } else {
        this.silenceFrames = 0;
      }
    } else {
      if (energy > this.SPEECH_ENERGY_THRESHOLD && energy > avgEnergy * 1.5) {
        this.isSpeaking = true;
        this.silenceFrames = 0;
        this.callbacks.onSpeechStart?.();
        console.log('[VAD] 🔴 语音开始 (能量)');
      }
    }

    return { isSpeech: this.isSpeaking, prob };
  }

  reset(): void {
    this.speechFrames = 0;
    this.silenceFrames = 0;
    this.isSpeaking = false;
    this.energyHistory = [];
    if (this.h?.data) this.h.data.fill(0);
    if (this.c?.data) this.c.data.fill(0);
  }

  get isRunning(): boolean {
    return this.session !== null && !this.useFallback;
  }
}

export const vadEngine = new VADEngine();
