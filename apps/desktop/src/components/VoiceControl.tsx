import React, { useCallback, useState } from 'react';
import { useSileroVAD } from '../hooks/useSileroVAD';

export const VoiceControl: React.FC = () => {
  const [lastTranscript, setLastTranscript] = useState('');
  const [status, setStatus] = useState<'idle' | 'listening' | 'recording' | 'wake-word'>('idle');

  const handleSpeechEnd = useCallback(async (blob: Blob) => {
    console.log('[Voice] 收到录音，准备转写...');
    
    try {
      const formData = new FormData();
      formData.append('audio', blob, 'voice.webm');
      
      const res = await fetch('/api/voice/transcribe', {
        method: 'POST',
        body: formData,
      });
      
      if (!res.ok) {
        throw new Error(`转写失败: ${res.status}`);
      }
      
      const data = await res.json();
      // 🆕 兼容多种字段名：优先 transcript，其次 text
      const transcript = data.transcript || data.text || '';
      console.log('[Voice] 转写结果:', transcript);
      setLastTranscript(transcript);
      
      // 🆕 发送给 AI 处理
      if (transcript) {
        try {
          const aiRes = await fetch('/api/voice/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript }),
          });
          const result = await aiRes.json();
          console.log('[Voice] AI 回复:', result.reply);
          
          // 🆕 播放 TTS（如果有）
          if (result.speech_text && result.tts_audio_base64) {
            const audio = new Audio(`data:${result.tts_mime_type || 'audio/mp3'};base64,${result.tts_audio_base64}`);
            audio.play().catch(e => console.log('[Voice] TTS 播放失败:', e));
          }
        } catch (aiErr) {
          console.error('[Voice] AI 处理错误:', aiErr);
        }
      }
      
    } catch (err) {
      console.error('[Voice] 转写错误:', err);
    }
  }, []);

  const handleWakeWordDetected = useCallback(() => {
    console.log('[Voice] 🎤 唤醒词检测到！');
    setStatus('listening');
  }, []);

  const {
    isListening,
    isRecording,
    isWakeWordMode,
    startListening,
    stopListening,
    enableWakeWordMode,
    disableWakeWordMode,
  } = useSileroVAD({
    onSpeechEnd: handleSpeechEnd,
    onWakeWordDetected: handleWakeWordDetected,
    wakeWord: '开始语音',
    continuousMode: true,
    silenceTimeout: 3000,
  });

  const handleToggle = useCallback(() => {
    if (isListening) {
      stopListening();
      setStatus('idle');
    } else {
      startListening();
      setStatus(isWakeWordMode ? 'wake-word' : 'listening');
    }
  }, [isListening, isWakeWordMode, startListening, stopListening]);

  const handleWakeWordToggle = useCallback(() => {
    if (isWakeWordMode) {
      disableWakeWordMode();
      if (isListening) setStatus('listening');
    } else {
      enableWakeWordMode();
      if (isListening) setStatus('wake-word');
    }
  }, [isWakeWordMode, isListening, enableWakeWordMode, disableWakeWordMode]);

  const getStatusText = () => {
    if (isRecording) return '🔴 录音中...';
    if (status === 'wake-word') return '🎤 等待唤醒词...';
    if (isListening) return '👂 监听中...';
    return '⏸️ 已停止';
  };

  const getButtonText = () => {
    if (isRecording) return '停止录音';
    if (isListening) return '停止监听';
    return '开始监听';
  };

  return (
    <div className="voice-control" style={{
      padding: '16px',
      background: '#1a1a2e',
      borderRadius: '12px',
      color: '#fff',
    }}>
      <h3 style={{ margin: '0 0 12px 0', fontSize: '16px' }}>🎙️ 语音控制</h3>
      
      {/* 唤醒词模式开关 */}
      <label style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '12px',
        cursor: 'pointer',
        fontSize: '14px',
      }}>
        <input
          type="checkbox"
          checked={isWakeWordMode}
          onChange={handleWakeWordToggle}
          disabled={isListening}
        />
        <span>唤醒词模式（说"开始语音"唤醒）</span>
      </label>

      {/* 主按钮 */}
      <button
        onClick={handleToggle}
        style={{
          width: '100%',
          padding: '12px',
          borderRadius: '8px',
          border: 'none',
          background: isListening ? '#ef4444' : '#3b82f6',
          color: '#fff',
          fontSize: '14px',
          fontWeight: 'bold',
          cursor: 'pointer',
          marginBottom: '12px',
        }}
      >
        {getButtonText()}
      </button>

      {/* 状态显示 */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '14px',
        color: '#94a3b8',
      }}>
        <span>{getStatusText()}</span>
      </div>

      {/* 最后一次转写结果 */}
      {lastTranscript && (
        <div style={{
          marginTop: '12px',
          padding: '8px 12px',
          background: '#0f172a',
          borderRadius: '6px',
          fontSize: '13px',
        }}>
          <div style={{ color: '#64748b', marginBottom: '4px' }}>你说：</div>
          <div>{lastTranscript}</div>
        </div>
      )}

      {/* 快捷键提示 */}
      <div style={{
        marginTop: '12px',
        fontSize: '12px',
        color: '#64748b',
      }}>
        💡 快捷键: Ctrl+Alt+A 切换语音监听
      </div>
    </div>
  );
};
