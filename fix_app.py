import pathlib

p = pathlib.Path(r'd:/ecv/apps/desktop/src/App.tsx')
lines = p.read_text(encoding='utf-8').split('
')

# Line 1371 (0-indexed: 1370) is the compressed single line
target = 1370
print(f'Line {target+1} length: {len(lines[target])}')
print(f'First 100 chars: {lines[target][:100]}')

# Replace the compressed line with properly formatted code
new_code = """  // 唤醒词监听：使用 MediaRecorder + 后端 Whisper STT 循环模式
  // 不再依赖浏览器 SpeechRecognition API（Electron 中不稳定）
  const WAKE_LISTEN_INTERVAL_MS = 4000

  const startWakeWordListening = useCallback(async () => {
    if (isWakeListening) {
      setSttStatus(`正在持续监听唤醒词"${DEFAULT_WAKE_WORD}"`)
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError('当前环境不支持麦克风采集，无法开启唤醒监听')
      setSttStatus(MANUAL_INPUT_FALLBACK_STATUS)
      return
    }

    const permission = await ensureMicrophoneAccess()
    if (!permission.ok) {
      setVoiceContextStatus('唤醒监听启动前的麦克风权限探测失败，已明确切换到手动输入模式。')
      return
    }

    if (interruptionEnabled) stopActiveSpeech()

    setVoiceError('')
    setInterimTranscript('')
    setSttStatus(`已开启持续监听，请直接说"${DEFAULT_WAKE_WORD}"唤醒 Agent`)
    wakeLockRef.current = true
    setIsWakeListening(true)

    const runWakeLoop = async () => {
      if (!wakeLockRef.current) return

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        wakeMediaStreamRef.current = stream

        if (!mediaRecorderSupported) {
          stream.getTracks().forEach(t => t.stop())
          setVoiceError('当前环境不支持 MediaRecorder，无法唤醒监听')
          setSttStatus(MANUAL_INPUT_FALLBACK_STATUS)
          setIsWakeListening(false)
          wakeLockRef.current = false
          return
        }

        const chunks: Blob[] = []
        const preferredMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : MediaRecorder.isTypeSupported('audio/webm')
            ? 'audio/webm'
            : ''
        const recorder = preferredMimeType
          ? new MediaRecorder(stream, { mimeType: preferredMimeType, audioBitsPerSecond: 128000 })
          : new MediaRecorder(stream, { audioBitsPerSecond: 128000 })
        wakeRecorderRef.current = recorder

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data)
        }

        recorder.onstop = async () => {
          stream.getTracks().forEach(t => t.stop())
          wakeMediaStreamRef.current = null
          wakeRecorderRef.current = null

          if (!wakeLockRef.current) return

          const blob = new Blob(chunks, { type: preferredMimeType || 'audio/webm' })
          if (blob.size < 1024) {
            wakeLoopTimerRef.current = window.setTimeout(() => { void runWakeLoop() }, 300)
            return
          }

          try {
            const turnId = generateVoiceId('wake')
            const formData = new FormData()
            formData.append('file', blob, 'wake-listen.webm')
            formData.append('locale', 'zh-CN')
            formData.append('session_id', sessionId)
            formData.append('turn_id', turnId)
            formData.append('wake_word_enabled', 'true')
            formData.append('interruption_enabled', String(interruptionEnabled))

            const response = await fetch(`${VOICE_API_BASE}/voice/transcribe-upload`, {
              method: 'POST',
              body: formData,
            })

            if (!response.ok) throw new Error(`STT request failed: ${response.status}`)

            const data = (await response.json()) as VoiceTranscribeResponse
            const transcript = (data.transcript || '').trim()

            if (transcript) {
              setInterimTranscript(transcript)
              setSttStatus(`监听中：${transcript}`)
            }

            // 检测唤醒词
            const compact = transcript.replace(/\s+/g, '').toLowerCase()
            const wakeMatched = data.wake_word_detected
              || compact.includes(DEFAULT_WAKE_WORD.toLowerCase())
              || compact.includes('小知')
              || compact.includes('agent')
              || compact.includes('助手')

            if (wakeMatched && wakeLockRef.current) {
              wakeLockRef.current = false
              const commandOnly = transcript
                .replace(/^(小智|小知|agent|助手)[,，!！\s:]*/i, '')
                .trim()

              setVoiceCommand(commandOnly || voiceCommand)
              setInterimTranscript('')
              setCurrentTurnId(generateVoiceId('turn'))
              setSttStatus(commandOnly
                ? `已命中唤醒词，自动提交指令：${commandOnly}`
                : '已命中唤醒词，开始录音采集后续指令')

              if (commandOnly) {
                stopWakeWordListening()
                void handleVoiceCommandSubmit(commandOnly, { source: 'whisper-stt-wake-word-inline' })
                wakeTimerRef.current = window.setTimeout(() => {
                  restartWakeWordListeningRef.current?.()
                }, 1200)
                return
              }

              stopWakeWordListening()
              wakeTimerRef.current = window.setTimeout(() => {
                void startVoiceCapture()
              }, 300)
              return
            }

            // 未命中唤醒词，继续下一轮监听
            if (wakeLockRef.current) {
              wakeLoopTimerRef.current = window.setTimeout(() => { void runWakeLoop() }, 300)
            }
          } catch (err) {
            console.warn('唤醒词 STT 请求失败:', err)
            if (wakeLockRef.current) {
              setSttStatus('唤醒监听 STT 请求异常，正在重连...')
              wakeLoopTimerRef.current = window.setTimeout(() => { void runWakeLoop() }, 1500)
            }
          }
        }

        recorder.onerror = () => {
          stream.getTracks().forEach(t => t.stop())
          wakeMediaStreamRef.current = null
          wakeRecorderRef.current = null
          if (wakeLockRef.current) {
            wakeLoopTimerRef.current = window.setTimeout(() => { void runWakeLoop() }, 1000)
          }
        }

        recorder.start()
        window.setTimeout(() => {
          if (recorder.state === 'recording') {
            recorder.stop()
          }
        }, WAKE_LISTEN_INTERVAL_MS)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'microphone error'
        setVoiceError(`唤醒监听麦克风异常：${message}`)
        setSttStatus(`${MANUAL_INPUT_FALLBACK_STATUS}（唤醒监听异常：${message}）`)
        setIsWakeListening(false)
        wakeLockRef.current = false
      }
    }

    void runWakeLoop()
  }, [handleVoiceCommandSubmit, interruptionEnabled, isWakeListening, mediaRecorderSupported, sessionId, startVoiceCapture, stopActiveSpeech, stopWakeWordListening, voiceCommand])"""

lines[target] = new_code
p.write_text('
'.join(lines), encoding='utf-8')
print('File updated successfully!')
