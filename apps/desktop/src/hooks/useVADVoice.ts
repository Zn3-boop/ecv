import { useState, useRef, useCallback, useEffect } from 'react';

interface UseVADVoiceOptions {
  onSpeechStart?: () => void;
  onSpeechEnd?: (audioBlob: Blob) => void;
}

export const useVADVoice = ({
  onSpeechStart,
  onSpeechEnd,
}: UseVADVoiceOptions = {}) => {
  const [isListening, setIsListening] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  
  const listeningRef = useRef(false);
  const recordingRef = useRef(false);

  useEffect(() => { listeningRef.current = isListening; }, [isListening]);
  useEffect(() => { recordingRef.current = isRecording; }, [isRecording]);

  const doStartRecording = useCallback(() => {
    if (!streamRef.current || recordingRef.current) return;
    
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';
    
    const mediaRecorder = new MediaRecorder(streamRef.current, { mimeType });
    
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];
    
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunksRef.current, { type: mimeType });
      setIsRecording(false);
      setIsProcessing(false);
      
      if (onSpeechEnd) {
        onSpeechEnd(blob);
      }
    };
    
    mediaRecorder.start();
    setIsRecording(true);
    setIsProcessing(true);
    onSpeechStart?.();
    console.log('[VAD] 开始录音');
  }, [onSpeechStart, onSpeechEnd]);

  const doStopRecording = useCallback(() => {
    if (!recordingRef.current) return;
    mediaRecorderRef.current?.stop();
    console.log('[VAD] 停止录音');
  }, []);

  const startListening = useCallback(async () => {
    if (listeningRef.current) return;
    
    try {
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
      
      worklet.port.onmessage = async (event: MessageEvent) => {
        if (event.data.type === 'batch') {
          const frames: number[][] = event.data.frames;
          
          for (const frame of frames) {
            const result = await (window as unknown as { electron?: { processVADFrame?: (f: number[]) => Promise<{ triggered: boolean; isSpeech: boolean }> } }).electron?.processVADFrame?.(frame);
            
            if (result?.triggered && result?.isSpeech && !recordingRef.current) {
              doStartRecording();
            } else if (result?.triggered && !result?.isSpeech && recordingRef.current) {
              doStopRecording();
            }
          }
        }
      };
      
      source.connect(worklet);
      worklet.connect(audioContext.destination);
      workletNodeRef.current = worklet;
      
      setIsListening(true);
      console.log('[VAD] 开始监听');
      
    } catch (err) {
      console.error('[VAD] 启动失败:', err);
    }
  }, [doStartRecording, doStopRecording]);

  const stopListening = useCallback(() => {
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
    }
    workletNodeRef.current?.disconnect();
    setIsListening(false);
    console.log('[VAD] 停止监听');
  }, []);

  useEffect(() => {
    const unsubscribe = (window as unknown as { electron?: { onToggleListening?: (cb: () => void) => () => void } }).electron?.onToggleListening?.(() => {
      if (listeningRef.current) {
        stopListening();
      } else {
        startListening();
      }
    });
    return () => unsubscribe?.();
  }, [startListening, stopListening]);

  useEffect(() => {
    return () => {
      stopListening();
    };
  }, [stopListening]);

  return {
    isListening,
    isRecording,
    isProcessing,
    startListening,
    stopListening,
  };
};
