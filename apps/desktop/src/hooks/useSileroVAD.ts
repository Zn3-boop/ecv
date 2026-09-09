import { useState, useRef, useCallback, useEffect } from 'react';

// ===== 类型声明 =====
interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

interface SpeechRecognitionResultEvent {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResult[];
}

interface SpeechRecognitionErrorEvent {
  readonly error: string;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
    electron?: ElectronAPI;
  }
}

interface ElectronAPI {
  startVAD: () => Promise<{ success: boolean }>;
  stopVAD: () => Promise<void>;
  processVAD: (frame: number[]) => Promise<{ isSpeech: boolean; prob: number }>;
  onVADSpeechStart: (cb: () => void) => () => void;
  onVADSpeechEnd: (cb: () => void) => () => void;
}

interface UseSileroVADOptions {
  onSpeechStart?: () => void;
  onSpeechEnd?: (blob: Blob) => void;
  wakeWord?: string;
  onWakeWordDetected?: () => void;
  continuousMode?: boolean;
  silenceTimeout?: number;
}

export const useSileroVAD = ({
  onSpeechStart,
  onSpeechEnd,
  wakeWord = '开始语音',
  onWakeWordDetected,
  continuousMode = true,
  silenceTimeout = 2000,
}: UseSileroVADOptions = {}) => {
  const [isListening, setIsListening] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isWakeWordMode, setIsWakeWordMode] = useState(false);

  // Refs（避免闭包问题）
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const unsubsRef = useRef<(() => void)[]>([]);
  const startTimeRef = useRef<number>(0);
  const isRecordingRef = useRef(false);
  const isListeningRef = useRef(false);
  const continuousModeRef = useRef(continuousMode);
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 语音识别
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const wakeWordDetectedRef = useRef(false);

  // 同步 ref
  useEffect(() => { isRecordingRef.current = isRecording; }, [isRecording]);
  useEffect(() => { isListeningRef.current = isListening; }, [isListening]);
  useEffect(() => { continuousModeRef.current = continuousMode; }, [continuousMode]);

  const cleanup = useCallback(() => {
    if (audioContextRef.current?.state !== 'closed') {
      audioContextRef.current?.close();
    }
    streamRef.current?.getTracks().forEach(t => t.stop());
    workletNodeRef.current?.disconnect();
    audioContextRef.current = null;
    streamRef.current = null;
    workletNodeRef.current = null;
  }, []);

  const stopRecording = useCallback(() => {
    if (!isRecordingRef.current) return;
    console.log('[VAD] ⚪ 停止录音');
    mediaRecorderRef.current?.stop();
  }, []);

  // scheduleNextRound 必须在 startRecording 之前定义
  const scheduleNextRound = useCallback(() => {
    if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current);
    
    console.log(`[VAD] ${silenceTimeout}ms 后进入下一轮监听...`);
    silenceTimeoutRef.current = setTimeout(() => {
      if (!isListeningRef.current) return;
      console.log('[VAD] 进入下一轮监听');
      wakeWordDetectedRef.current = false;
      if (isWakeWordMode && recognitionRef.current) {
        try { recognitionRef.current.start(); } catch { /* ignore */ }
      }
    }, silenceTimeout);
  }, [silenceTimeout, isWakeWordMode]);

  const startRecording = useCallback(() => {
    if (!streamRef.current || isRecordingRef.current) return;

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';

    const mediaRecorder = new MediaRecorder(streamRef.current, { mimeType });
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];
    startTimeRef.current = Date.now();

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    mediaRecorder.onstop = () => {
      const duration = Date.now() - startTimeRef.current;
      console.log(`[VAD] 录音完成，时长 ${duration}ms`);

      if (duration < 300) {
        console.log('[VAD] 录音太短，丢弃');
        setIsRecording(false);
        if (continuousModeRef.current) scheduleNextRound();
        return;
      }

      const blob = new Blob(audioChunksRef.current, { type: mimeType });
      setIsRecording(false);
      onSpeechEnd?.(blob);

      if (continuousModeRef.current) scheduleNextRound();
    };

    mediaRecorder.start();
    setIsRecording(true);
    onSpeechStart?.();
    console.log('[VAD] 🔴 开始录音');
  }, [onSpeechStart, onSpeechEnd, scheduleNextRound]);

  const initSpeechRecognition = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      console.warn('[VAD] 浏览器不支持 Web Speech API');
      return null;
    }

    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'zh-CN';

    recognition.onresult = (event: SpeechRecognitionResultEvent) => {
      const result = event.results[event.results.length - 1];
      const transcript = result[0].transcript;
      
      console.log('[VAD] [唤醒词] 识别:', transcript, 'isFinal:', result.isFinal);

      if (transcript.includes(wakeWord) && !wakeWordDetectedRef.current) {
        console.log('[VAD] 🎤 唤醒词检测到:', wakeWord);
        wakeWordDetectedRef.current = true;
        
        try { recognition.stop(); } catch { /* ignore */ }
        
        onWakeWordDetected?.();
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'not-allowed') {
        console.error('[VAD] 麦克风权限被拒绝');
      } else if (event.error !== 'aborted' && event.error !== 'no-speech') {
        console.warn('[VAD] 语音识别错误:', event.error);
      }
    };

    recognition.onend = () => {
      if (isListeningRef.current && !wakeWordDetectedRef.current) {
        setTimeout(() => {
          if (isListeningRef.current && !wakeWordDetectedRef.current) {
            try { recognition.start(); } catch { /* ignore */ }
          }
        }, 300);
      }
    };

    return recognition;
  }, [wakeWord, onWakeWordDetected]);

  const startListening = useCallback(async () => {
    if (isListeningRef.current) return;

    try {
      const vadReady = await window.electron?.startVAD?.();
      if (!vadReady?.success) {
        console.warn('[VAD] VAD 初始化失败');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      await audioContext.audioWorklet.addModule('/audio-worklets/vad-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(audioContext, 'vad-processor');

      worklet.port.onmessage = async (event) => {
        if (event.data.type === 'batch') {
          const frames: number[][] = event.data.frames;
          for (const frame of frames) {
            await window.electron?.processVAD?.(frame);
          }
        }
      };

      source.connect(worklet);
      worklet.connect(audioContext.destination);
      workletNodeRef.current = worklet;

      const unsubStart = window.electron?.onVADSpeechStart?.(() => {
        console.log('[VAD] 前端收到：语音开始');
        if (isWakeWordMode && !wakeWordDetectedRef.current) {
          console.log('[VAD] 唤醒词未检测到，忽略语音');
          return;
        }
        startRecording();
      });

      const unsubEnd = window.electron?.onVADSpeechEnd?.(() => {
        console.log('[VAD] 前端收到：语音结束');
        stopRecording();
      });

      unsubsRef.current = [unsubStart, unsubEnd].filter(Boolean) as (() => void)[];

      if (isWakeWordMode) {
        wakeWordDetectedRef.current = false;
        const recognition = initSpeechRecognition();
        if (recognition) {
          recognitionRef.current = recognition;
          recognition.start();
          console.log('[VAD] 🎤 唤醒词模式已启用，说"', wakeWord, '"即可开始');
        }
      }

      setIsListening(true);
      console.log('[VAD] 监听已启动');

    } catch (err) {
      console.error('[VAD] 启动失败:', err);
      cleanup();
    }
  }, [isWakeWordMode, wakeWord, startRecording, stopRecording, cleanup, initSpeechRecognition]);

  const stopListening = useCallback(() => {
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }

    unsubsRef.current.forEach(fn => fn?.());
    unsubsRef.current = [];

    window.electron?.stopVAD?.();

    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }

    cleanup();
    setIsListening(false);
    setIsRecording(false);
    wakeWordDetectedRef.current = false;
    console.log('[VAD] 监听已停止');
  }, [cleanup]);

  const enableWakeWordMode = useCallback(() => {
    setIsWakeWordMode(true);
    console.log('[VAD] 唤醒词模式已启用');
  }, []);

  const disableWakeWordMode = useCallback(() => {
    setIsWakeWordMode(false);
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopListening();
  }, [stopListening]);

  return {
    isListening,
    isRecording,
    isWakeWordMode,
    startListening,
    stopListening,
    enableWakeWordMode,
    disableWakeWordMode,
  };
};
