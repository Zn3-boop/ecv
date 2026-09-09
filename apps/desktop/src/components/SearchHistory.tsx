import { useState, useEffect, useCallback } from 'react'
import {
  Search,
  Clock,
  Terminal,
  Activity,
  Trash2,
  Cpu,
  HardDrive,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
  HelpCircle,
} from 'lucide-react'

interface HistoryRecord {
  id: string
  timestamp: string
  query: string
  type: 'cpu' | 'disk' | 'memory' | 'cleanup' | 'general'
  actions: string[]
  status: 'completed' | 'pending' | 'confirm_required' | 'failed'
  systemData?: string
  actionCount?: number
}

interface SessionHistoryProps {
  sessionId: number | null
  onSelectRecord?: (record: HistoryRecord) => void
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export default function SearchHistory({ sessionId, onSelectRecord }: SessionHistoryProps) {
  const [query, setQuery] = useState('')
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<string>('all')

  const search = useCallback(
    async (keyword: string) => {
      if (!sessionId) return
      setLoading(true)
      try {
        const params = new URLSearchParams({
          conversation_id: String(sessionId),
          q: keyword,
          limit: '50',
        })
        const res = await fetch(`${API_BASE}/chat/history/search?${params}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setRecords(data.records || [])
      } catch (e) {
        console.error('搜索历史失败', e)
        setRecords([])
      } finally {
        setLoading(false)
      }
    },
    [sessionId],
  )

  useEffect(() => {
    search('')
  }, [search])

  useEffect(() => {
    const t = setTimeout(() => search(query), 300)
    return () => clearTimeout(t)
  }, [query, search])

  const filtered = filter === 'all' ? records : records.filter((r) => r.type === filter)
  const grouped: Record<string, HistoryRecord[]> = groupByDate(filtered)

  return (
    <div className="session-history">
      <div className="history-header">
        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="搜索处理记录：CPU、C盘、内存、清理..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="clear" onClick={() => setQuery('')}>
              ×
            </button>
          )}
        </div>

        <div className="filter-bar">
          {[
            { key: 'all', label: '全部' },
            { key: 'cpu', label: 'CPU' },
            { key: 'disk', label: '磁盘' },
            { key: 'memory', label: '内存' },
            { key: 'cleanup', label: '清理' },
          ].map((f) => (
            <button
              key={f.key}
              className={filter === f.key ? 'active' : ''}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="records-list">
        {loading && <div className="empty">搜索中...</div>}
        {!loading && records.length === 0 && (
          <div className="empty">
            <Terminal size={40} opacity={0.3} />
            <p>暂无处理记录</p>
            <span className="empty-tip">尝试搜索 "CPU"、"C盘"、"内存" 等关键词</span>
          </div>
        )}

        {Object.entries(grouped).map(([date, items]) => (
          <div key={date} className="date-group">
            <div className="date-label">{date}</div>
            {items.map((r) => (
              <HistoryCard key={r.id} record={r} onSelect={onSelectRecord} />
            ))}
          </div>
        ))}
      </div>

      <style>{`
        .session-history { display:flex; flex-direction:column; height:100%; background:#0b1120; color:#e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .history-header { padding:16px; border-bottom:1px solid #1e293b; }
        .search-box { position:relative; display:flex; align-items:center; background:#1e293b; border:1px solid #334155; border-radius:8px; padding:0 12px; }
        .search-box input { flex:1; background:transparent; border:none; padding:10px; color:#f1f5f9; font-size:14px; outline:none; }
        .search-box .clear { background:none; border:none; color:#64748b; cursor:pointer; font-size:16px; padding:0 4px; }
        .filter-bar { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
        .filter-bar button { padding:4px 12px; border-radius:4px; border:none; background:#1e293b; color:#94a3b8; font-size:12px; cursor:pointer; transition:all 0.2s; }
        .filter-bar button.active { background:#3b82f6; color:white; }
        .records-list { flex:1; overflow-y:auto; padding:12px; }
        .date-group { margin-bottom:16px; }
        .date-label { font-size:12px; color:#64748b; margin-bottom:8px; padding-left:4px; font-weight:500; }
        .empty { text-align:center; padding:60px 20px; color:#64748b; display:flex; flex-direction:column; align-items:center; gap:8px; }
        .empty-tip { font-size:12px; color:#475569; }
      `}</style>
    </div>
  )
}

function HistoryCard({ record, onSelect }: { record: HistoryRecord; onSelect?: (r: HistoryRecord) => void }) {
  const [expanded, setExpanded] = useState(false)

  const icons: Record<string, React.ReactNode> = {
    cpu: <Cpu size={16} />,
    disk: <HardDrive size={16} />,
    memory: <Activity size={16} />,
    cleanup: <Trash2 size={16} />,
    general: <Terminal size={16} />,
  }

  const statusConfig = {
    completed: { color: '#22c55e', bg: '#14532d', icon: <CheckCircle size={14} />, text: '已完成' },
    pending: { color: '#f59e0b', bg: '#78350f', icon: <HelpCircle size={14} />, text: '执行中' },
    confirm_required: { color: '#ef4444', bg: '#7f1d1d', icon: <AlertTriangle size={14} />, text: '需确认' },
    failed: { color: '#ef4444', bg: '#7f1d1d', icon: <XCircle size={14} />, text: '失败' },
  }

  const s = statusConfig[record.status]

  return (
    <div className={`h-card ${record.status}`} onClick={() => onSelect?.(record)}>
      <div className="h-main" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}>
        <div className="h-icon" style={{ color: s.color }}>
          {icons[record.type] || icons.general}
        </div>
        <div className="h-body">
          <div className="h-top">
            <span className="h-query">{record.query}</span>
            <span className="h-status" style={{ color: s.color, background: s.bg }}>
              {s.icon}
              {s.text}
            </span>
          </div>
          <div className="h-meta">
            <Clock size={12} />
            {formatTime(record.timestamp)}
            {record.actions.length > 0 && (
              <span className="h-actions">{record.actions.join(' · ')}</span>
            )}
            {record.actionCount !== undefined && (
              <span className="h-count">({record.actionCount} 条指令)</span>
            )}
          </div>
        </div>
        <div className="h-toggle" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {expanded && (
        <div className="h-detail">
          {record.systemData && (
            <div className="detail-block">
              <h4>系统监控数据</h4>
              <pre>{record.systemData}</pre>
            </div>
          )}
          {record.actions.length > 0 && (
            <div className="detail-block">
              <h4>执行步骤</h4>
              <ul>
                {record.actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <style>{`
        .h-card { background:#1e293b; border-radius:8px; margin-bottom:8px; overflow:hidden; border-left:3px solid transparent; cursor:pointer; transition:background 0.15s; }
        .h-card:hover { background:#27354f; }
        .h-card.completed { border-left-color:#22c55e; }
        .h-card.confirm_required { border-left-color:#ef4444; }
        .h-card.failed { border-left-color:#ef4444; }
        .h-main { display:flex; align-items:center; gap:12px; padding:12px; }
        .h-icon { display:flex; align-items:center; justify-content:center; width:32px; height:32px; background:#0f172a; border-radius:8px; flex-shrink:0; }
        .h-body { flex:1; min-width:0; }
        .h-top { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:4px; }
        .h-query { font-size:14px; font-weight:500; color:#f1f5f9; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .h-status { font-size:11px; padding:2px 8px; border-radius:4px; white-space:nowrap; display:flex; align-items:center; gap:4px; }
        .h-meta { display:flex; align-items:center; gap:6px; font-size:12px; color:#64748b; flex-wrap:wrap; }
        .h-actions { color:#94a3b8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:200px; }
        .h-count { color:#64748b; margin-left:auto; }
        .h-toggle { color:#64748b; flex-shrink:0; cursor:pointer; padding:4px; }
        .h-detail { padding:0 12px 12px 56px; border-top:1px solid #334155; }
        .detail-block { margin-top:12px; }
        .detail-block h4 { font-size:12px; color:#64748b; margin-bottom:6px; font-weight:500; }
        .detail-block pre { background:#0f172a; padding:8px; border-radius:4px; font-size:11px; color:#94a3b8; white-space:pre-wrap; word-break:break-all; max-height:200px; overflow-y:auto; line-height:1.5; }
        .detail-block ul { margin:0; padding-left:16px; font-size:12px; color:#94a3b8; }
        .detail-block li { margin-bottom:4px; }
      `}</style>
    </div>
  )
}

function groupByDate(records: HistoryRecord[]): Record<string, HistoryRecord[]> {
  const g: Record<string, HistoryRecord[]> = {}
  const today = new Date().toDateString()
  const yesterday = new Date(Date.now() - 86400000).toDateString()

  for (const r of records) {
    const d = new Date(r.timestamp).toDateString()
    const label =
      d === today ? '今天' : d === yesterday ? '昨天' : new Date(r.timestamp).toLocaleDateString('zh-CN')
    if (!g[label]) g[label] = []
    g[label].push(r)
  }
  return g
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}