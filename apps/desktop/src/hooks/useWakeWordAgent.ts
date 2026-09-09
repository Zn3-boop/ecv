import { useState, useCallback, useRef, useEffect } from 'react';
import { useVADVoice } from './useVADVoice';

const WAKE_WORDS = ['小助手', '小智', '助手', 'hey assistant', '清理内存', '打开微信'];
const COMMAND_TIMEOUT = 8000;

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = (reader.result as string).split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export const useWakeWordAgent = () => {
  const [isAwake, setIsAwake] = useState(false);
  const [lastReply, setLastReply] = useState('');
  const [lastTranscript, setLastTranscript] = useState('');
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const transcribe = useCallback(async (blob: Blob): Promise<string> => {
    try {
      const base64 = await blobToBase64(blob);
      const mimeType = blob.type || 'audio/webm';
      
      const res = await fetch(`${API_BASE}/voice/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_base64: base64,
          filename: `voice.${mimeType.split('/')[1]}`,
          mime_type: mimeType,
        }),
      });
      const data = await res.json();
      return data.transcript || '';
    } catch (err) {
      console.error('[WakeWord] 转写失败:', err);
      return '';
    }
  }, []);

  const sendCommand = useCallback(async (text: string) => {
    try {
      const res = await fetch(`${API_BASE}/voice/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          transcript: text,
          mode: 'voice',
          source: 'wake-word',
        }),
      });
      return res.json();
    } catch (err) {
      console.error('[WakeWord] 命令发送失败:', err);
      return { reply: '处理失败，请重试' };
    }
  }, []);

  const speak = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (!window.speechSynthesis) {
        resolve();
        return;
      }
      
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'zh-CN';
      utterance.rate = 1.1;
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });
  }, []);

  const handleSpeechEnd = useCallback(async (blob: Blob) => {
    const text = await transcribe(blob);
    console.log('[WakeWord] 转写:', text);
    setLastTranscript(text);
    
    if (!text) return;

    if (!isAwake) {
      const matched = WAKE_WORDS.some(w => text.includes(w));
      if (matched) {
        setIsAwake(true);
        await speak('我在，请说');
        
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => {
          setIsAwake(false);
          console.log('[WakeWord] 超时休眠');
        }, COMMAND_TIMEOUT);
      }
      return;
    }

    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    
    const result = await sendCommand(text);
    const reply = result.reply || result.summary || '处理完成';
    setLastReply(reply);
    
    await speak(reply);
    
    timeoutRef.current = setTimeout(() => {
      setIsAwake(false);
      console.log('[WakeWord] 连续对话超时休眠');
    }, COMMAND_TIMEOUT);
  }, [isAwake, transcribe, sendCommand, speak]);

  const { isListening, isRecording, isProcessing, startListening, stopListening } = useVADVoice({
    onSpeechEnd: handleSpeechEnd,
  });

  const resetWake = useCallback(() => {
    setIsAwake(false);
    setLastReply('');
    setLastTranscript('');
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return {
    isListening,
    isRecording,
    isProcessing,
    isAwake,
    lastReply,
    lastTranscript,
    startListening,
    stopListening,
    resetWake,
  };
};
