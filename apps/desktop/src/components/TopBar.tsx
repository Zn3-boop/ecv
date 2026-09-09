import type { SystemMetrics } from '../types'

interface TopBarProps {
  agentStatus: string
  preloadStatus: string
  voiceStatusText?: string
  metrics?: SystemMetrics | null
  error?: string
  onOpenConfig?: () => void
  onOpenWindowSettings?: () => void
}

export function TopBar({
  agentStatus,
  preloadStatus,
  voiceStatusText,
  metrics,
  error,
  onOpenConfig,
  onOpenWindowSettings,
}: TopBarProps) {
  return (
    <header style={{
      height: '56px',
      background: '#0f172a',
      borderBottom: '1px solid #1e293b',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 20px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '22px' }}>🤖</span>
          <span style={{ color: '#f8fafc', fontWeight: 700, fontSize: '16px' }}>AI Desktop Agent</span>
        </div>
        <span style={{
          fontSize: '12px',
          padding: '4px 10px',
          borderRadius: '6px',
          background: agentStatus.includes('在线') ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
          color: agentStatus.includes('在线') ? '#22c55e' : '#ef4444',
        }}>
          {agentStatus}
        </span>
        <span style={{ fontSize: '12px', color: '#64748b' }}>
          preload: {preloadStatus}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {voiceStatusText && (
          <span style={{
            fontSize: '12px',
            color: voiceStatusText.includes('可用') ? '#22c55e' : '#f59e0b',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}>
            🎤 {voiceStatusText}
          </span>
        )}
        {metrics && (
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            CPU {metrics.cpu.usagePercent.toFixed(0)}% · MEM {metrics.memory.usagePercent.toFixed(0)}%
          </span>
        )}
        {error && (
          <span style={{ fontSize: '12px', color: '#ef4444', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            ⚠️ {error}
          </span>
        )}
        <button
          onClick={onOpenConfig}
          style={{
            background: 'transparent',
            border: '1px solid #334155',
            color: '#94a3b8',
            padding: '6px 12px',
            borderRadius: '6px',
            fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          ⚙️ 设置
        </button>
        <button
          onClick={onOpenWindowSettings}
          style={{
            background: 'transparent',
            border: '1px solid #334155',
            color: '#94a3b8',
            padding: '6px 12px',
            borderRadius: '6px',
            fontSize: '13px',
            cursor: 'pointer',
          }}
          title="窗口管理"
        >
          🪟
        </button>
      </div>
    </header>
  )
}
