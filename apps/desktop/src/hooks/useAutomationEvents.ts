import { useState, useEffect, useCallback, useRef } from 'react'
import type { AutomationEvent, DesktopAPI } from '../types'

export const useAutomationEvents = (desktopAPI?: DesktopAPI) => {
  const [events, setEvents] = useState<AutomationEvent[]>([])
  const [loading, setLoading] = useState(true)
  const spokenEventIdsRef = useRef<Set<string>>(new Set())

  const loadEvents = useCallback(async () => {
    try {
      const items = await desktopAPI?.getAutomationEvents?.()
      if (items) setEvents(items)
    } catch {
      // ignore automation events bootstrap failure
    } finally {
      setLoading(false)
    }
  }, [desktopAPI])

  const addEvent = useCallback((event: AutomationEvent) => {
    setEvents((prev) => [event, ...prev.filter((item) => item.id !== event.id)].slice(0, 10))
  }, [])

  useEffect(() => {
    if (!desktopAPI) return

    // 初始加载
    queueMicrotask(() => {
      void loadEvents()
    })

    // 订阅自动化事件
    const dispose = desktopAPI?.onAutomationEvent?.((event: AutomationEvent) => {
      addEvent(event)
    })

    return () => {
      dispose?.()
    }
  }, [desktopAPI, loadEvents, addEvent])

  return { 
    events, 
    loading, 
    addEvent, 
    spokenEventIdsRef,
    refetch: loadEvents 
  }
}
