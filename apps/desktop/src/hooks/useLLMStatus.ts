import { useEffect, useState } from 'react'

export type LLMStatus = 'idle' | 'thinking' | 'calling' | 'success' | 'error' | 'fallback'

export interface LLMStatusInfo {
  status: LLMStatus
  message: string
  duration?: number
  error?: string
  fallbackReason?: string
}

export function useLLMStatus() {
  const [status, setStatus] = useState<LLMStatusInfo>({
    status: 'idle',
    message: '就绪',
  })
  const [callStartTime, setCallStartTime] = useState<number | null>(null)

  const startThinking = (message = '正在分析...') => {
    setCallStartTime(Date.now())
    setStatus({ status: 'thinking', message })
  }

  const startCalling = (message = '正在调用 LLM...') => {
    setCallStartTime(Date.now())
    setStatus({ status: 'calling', message })
  }

  const setSuccess = (message = '处理完成') => {
    const duration = callStartTime ? Date.now() - callStartTime : undefined
    setStatus({ status: 'success', message, duration })
    setCallStartTime(null)
  }

  const setError = (error: string) => {
    const duration = callStartTime ? Date.now() - callStartTime : undefined
    setStatus({ status: 'error', message: '调用失败', error, duration })
    setCallStartTime(null)
  }

  const setFallback = (reason: string) => {
    const duration = callStartTime ? Date.now() - callStartTime : undefined
    setStatus({ status: 'fallback', message: '降级模式', fallbackReason: reason, duration })
    setCallStartTime(null)
  }

  const reset = () => {
    setStatus({ status: 'idle', message: '就绪' })
    setCallStartTime(null)
  }

  return {
    status,
    startThinking,
    startCalling,
    setSuccess,
    setError,
    setFallback,
    reset,
  }
}

// 自动隐藏成功/错误状态的 Hook
export function useAutoHideStatus(statusInfo: LLMStatusInfo, hideDelay = 3000) {
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    if (statusInfo.status === 'success' || statusInfo.status === 'error') {
      const timer = setTimeout(() => setVisible(false), hideDelay)
      return () => clearTimeout(timer)
    }
    // 其他状态立即显示
    const timer = setTimeout(() => setVisible(true), 0)
    return () => clearTimeout(timer)
  }, [statusInfo.status, hideDelay])

  return visible
}
