import { useState, useEffect } from 'react'
import type { ConversationRecord } from '../types'
import SessionHistory from './SearchHistory'

interface ConversationPanelProps {
  onAnalyzeProblem: (text: string) => void
  _analyzeLoading: boolean  // kept for interface compatibility
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const STORAGE_API_BASE = `${API_BASE}/storage`

async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

export function ConversationPanel({ onAnalyzeProblem, _analyzeLoading }: ConversationPanelProps) {
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null)
  const [status, setStatus] = useState('初始化中...')
  const [loading, setLoading] = useState(true)

  // 加载会话
  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const convData = await fetchJson<{ items: ConversationRecord[] }>(`${STORAGE_API_BASE}/conversations`)
        if (convData.items[0]?.id) {
          setSelectedConversationId(convData.items[0].id)
          setStatus(`已加载：${convData.items[0].title}`)
        } else {
          setStatus('暂无会话')
        }
      } catch (err) {
        setStatus(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  // Keep analyze callback for future use when re-adding input
  void onAnalyzeProblem

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h2>会话区域</h2>
          <p className="panel-subtitle">历史记录 + 输入</p>
        </div>
        <span className="timestamp">{loading ? 'loading...' : status}</span>
      </div>

      {/* 历史记录 */}
      <div style={{ height: 'calc(100vh - 140px)', overflowY: 'auto', overflowX: 'hidden' }}>
        <SessionHistory 
          sessionId={selectedConversationId} 
          onSelectRecord={() => {
            // Future: could auto-fill input when re-adding input area
          }}
        />
      </div>
    </section>
  )
}