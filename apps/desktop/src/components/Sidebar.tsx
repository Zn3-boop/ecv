// 侧边导航栏组件
import type { AppView } from '../types'

export type { AppView }

interface SidebarProps {
  activeView: AppView
  onChange: (view: AppView) => void
  badgeCounts?: {
    tasks?: number
    conversation?: number
    execution?: number
    files?: number
  }
}

export function Sidebar({ activeView, onChange, badgeCounts = {} }: SidebarProps) {
  const items = [
    { key: 'tasks' as AppView, label: '任务中心', icon: '📋', badge: badgeCounts.tasks },
    { key: 'conversation' as AppView, label: '会话', icon: '💬', badge: badgeCounts.conversation },
    { key: 'execution' as AppView, label: '执行日志', icon: '⚡', badge: badgeCounts.execution },
    { key: 'files' as AppView, label: '文件', icon: '📁', badge: badgeCounts.files },
    { key: 'providers' as AppView, label: 'AI配置', icon: '🤖', badge: 0 },
  ]

  return (
    <nav style={{
      width: '200px',
      background: '#0f172a',
      borderRight: '1px solid #1e293b',
      padding: '16px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
    }}>
      <div style={{ padding: '0 8px 16px', borderBottom: '1px solid #1e293b', marginBottom: '8px' }}>
        <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '16px', fontWeight: 700 }}>AI Agent</h3>
        <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '12px' }}>桌面运维助手</p>
      </div>

      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onChange(item.key)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '10px 12px',
            borderRadius: '8px',
            border: 'none',
            background: activeView === item.key ? 'rgba(59,130,246,0.2)' : 'transparent',
            color: activeView === item.key ? '#3b82f6' : '#94a3b8',
            fontSize: '14px',
            fontWeight: activeView === item.key ? 600 : 400,
            cursor: 'pointer',
            transition: 'all 0.2s',
            textAlign: 'left',
            position: 'relative',
          }}
        >
          <span style={{ fontSize: '18px' }}>{item.icon}</span>
          <span>{item.label}</span>
          {item.badge ? (
            <span style={{
              marginLeft: 'auto',
              background: item.key === 'tasks' ? '#ef4444' : '#3b82f6',
              color: '#fff',
              fontSize: '11px',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '10px',
              minWidth: '18px',
              textAlign: 'center',
            }}>
              {item.badge}
            </span>
          ) : null}
        </button>
      ))}

      <div style={{ marginTop: 'auto', padding: '12px 8px', borderTop: '1px solid #1e293b' }}>
        <div style={{ fontSize: '11px', color: '#475569' }}>
          <div>🎤 Whisper 本地</div>
          <div style={{ marginTop: '4px' }}>⚡ 实时监听</div>
        </div>
      </div>
    </nav>
  )
}
