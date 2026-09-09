import { useState, useCallback, useRef, useEffect } from 'react'

interface VoiceRecorderState {
  isRecording: boolean
  transcript: string
  loading: boolean
  error: string
  stage: 'idle' | 'recording' | 'uploading' | 'transcribing' | 'done' | 'error'
  debugInfo: string
}

export const useVoiceRecorder = (apiBase: string = 'http://127.0.0.1:8000') => {
  const [state, setState] = useState<VoiceRecorderState>({
    isRecording: false,
    transcript: '',
    loading: false,
    error: '',
    stage: 'idle',
    debugInfo: '',
  })

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recordingStartTimeRef = useRef<number>(0)
  const streamRef = useRef<MediaStream | null>(null)
  const isProcessingRef = useRef<boolean>(false)

  // 清理函数：停止录音并释放资源
  const cleanup = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    mediaRecorderRef.current = null
  }, [])

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      cleanup()
    }
  }, [cleanup])

  const startRecording = useCallback(async () => {
    // 🆕 防重复点击：如果正在录音或处理中，直接返回
    if (state.isRecording || isProcessingRef.current) {
      console.log('[Voice] Already recording or processing, ignoring')
      return
    }

    try {
      isProcessingRef.current = true
      console.log('[Voice] Requesting microphone...')
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        } 
      })
      streamRef.current = stream
      console.log('[Voice] Microphone granted:', stream.getAudioTracks()[0]?.label)
      
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') 
        ? 'audio/webm' 
        : MediaRecorder.isTypeSupported('audio/mp4') 
          ? 'audio/mp4' 
          : 'audio/ogg'
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []
      recordingStartTimeRef.current = Date.now()

      mediaRecorder.ondataavailable = (event) => {
        // 🆕 过滤太小的 chunks（< 100 bytes 可能是噪音）
        if (event.data.size > 100) {
          audioChunksRef.current.push(event.data)
          console.log('[Voice] Audio chunk:', event.data.size, 'bytes')
        }
      }

      mediaRecorder.onstop = async () => {
        console.log('[Voice] Recording stopped, chunks:', audioChunksRef.current.length)
        
        // 🆕 检查录音时长（至少 1 秒）
        const duration = Date.now() - recordingStartTimeRef.current
        if (duration < 1000) {
          console.log('[Voice] Recording too short:', duration, 'ms')
          cleanup()
          setState(prev => ({ 
            ...prev, 
            isRecording: false, 
            error: '录音太短，请长按说话',
            stage: 'error',
            debugInfo: `录音仅 ${duration}ms，请长按说话`,
          }))
          isProcessingRef.current = false
          return
        }
        
        setState(prev => ({ ...prev, stage: 'uploading', loading: true, isRecording: false }))
        
        try {
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType })
          console.log('[Voice] Audio blob:', audioBlob.size, 'bytes, type:', mimeType, 'duration:', duration, 'ms')
          
          if (audioBlob.size < 1024) {
            throw new Error('录音太短，请重新录制')
          }

          const base64 = await blobToBase64(audioBlob)
          console.log('[Voice] Base64 length:', base64.length)

          setState(prev => ({ ...prev, stage: 'transcribing' }))

          const response = await fetch(`${apiBase}/voice/transcribe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              audio_base64: base64,
              filename: `voice.${mimeType.split('/')[1]}`,
              mime_type: mimeType,
            }),
          })

          console.log('[Voice] Response status:', response.status)
          const data = await response.json()
          console.log('[Voice] Response data:', data)

          // 🆕 兼容多种字段名：优先 transcript，其次 text
          const transcript = (data.transcript || data.text || '').trim()
          
          if (transcript) {
            setState(prev => ({
              ...prev,
              transcript: transcript,
              loading: false,
              stage: 'done',
              error: '',
              debugInfo: `识别成功 (${data.provider || 'unknown'})`,
            }))
          } else if (data.manual_input_required) {
            setState(prev => ({
              ...prev,
              transcript: '',
              error: `未识别到语音，请重试或直接输入文字`,
              loading: false,
              stage: 'error',
              debugInfo: `Provider: ${data.provider}, Model: ${data.model}`,
            }))
          } else {
            setState(prev => ({
              ...prev,
              transcript: '',
              error: data.message || '转写失败',
              loading: false,
              stage: 'error',
              debugInfo: JSON.stringify(data).slice(0, 200),
            }))
          }
        } catch (err) {
          console.error('[Voice] Error:', err)
          setState(prev => ({
            ...prev,
            error: err instanceof Error ? err.message : '上传失败',
            loading: false,
            stage: 'error',
            debugInfo: err instanceof Error ? err.stack?.slice(0, 200) || '' : '',
          }))
        } finally {
          cleanup()
          isProcessingRef.current = false
        }
      }

      mediaRecorder.onerror = (e) => {
        console.error('[Voice] Recorder error:', e)
        setState(prev => ({ 
          ...prev, 
          error: '录音设备错误', 
          stage: 'error',
          isRecording: false,
        }))
        cleanup()
        isProcessingRef.current = false
      }

      mediaRecorder.start(100) // 每100ms收集一次数据
      setState(prev => ({ 
        ...prev, 
        isRecording: true, 
        transcript: '', 
        error: '',
        stage: 'recording',
        debugInfo: `录音中... (${mimeType})`,
      }))
    } catch (err) {
      console.error('[Voice] Start error:', err)
      setState(prev => ({
        ...prev,
        error: err instanceof Error ? `无法访问麦克风: ${err.message}` : '麦克风权限被拒绝',
        stage: 'error',
        isRecording: false,
      }))
      isProcessingRef.current = false
    }
  }, [apiBase, state.isRecording, cleanup])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      console.log('[Voice] Stopping recording manually')
      mediaRecorderRef.current.stop()
    }
  }, [])

  const clearTranscript = useCallback(() => {
    cleanup()
    isProcessingRef.current = false
    setState(prev => ({ 
      ...prev, 
      transcript: '', 
      error: '', 
      stage: 'idle', 
      debugInfo: '',
      isRecording: false,
    }))
  }, [cleanup])

  // 🆕 设置转录文本（用于手动输入 fallback）
  const setTranscript = useCallback((text: string) => {
    setState(prev => ({ 
      ...prev, 
      transcript: text,
      error: '',
      stage: 'done',
    }))
  }, [])

  return {
    ...state,
    startRecording,
    stopRecording,
    clearTranscript,
    setTranscript, // 🆕 导出手动设置文本的函数
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const base64 = (reader.result as string).split(',')[1]
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}
