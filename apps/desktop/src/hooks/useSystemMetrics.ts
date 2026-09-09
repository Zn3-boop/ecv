import { useState, useEffect, useCallback, useRef } from 'react'
import type { DesktopAPI, SystemMetrics } from '../types'

export const useSystemMetrics = (desktopAPI?: DesktopAPI, pollingInterval: number = 2500) => {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const timerRef = useRef<number | null>(null)
  const isVisibleRef = useRef(true)

  const fetchMetrics = useCallback(async () => {
    try {
      const next = await desktopAPI?.getSystemMetrics?.()
      if (next) {
        setMetrics(next)
        setError('')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load metrics')
    } finally {
      setLoading(false)
    }
  }, [desktopAPI])

  const startPolling = useCallback(() => {
    if (timerRef.current) return
    timerRef.current = window.setInterval(() => {
      if (isVisibleRef.current) {
        void fetchMetrics()
      }
    }, pollingInterval)
  }, [fetchMetrics, pollingInterval])

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!desktopAPI) return

    // 初始加载
    queueMicrotask(() => { void fetchMetrics() })

    // 设置定时轮询
    startPolling()

    // 页面可见性监听 - 后台时停止轮询
    const handleVisibilityChange = () => {
      isVisibleRef.current = !document.hidden
      if (!document.hidden) {
        void fetchMetrics()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      stopPolling()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [desktopAPI, fetchMetrics, startPolling, stopPolling])

  return { metrics, error, loading, refetch: fetchMetrics }
}
