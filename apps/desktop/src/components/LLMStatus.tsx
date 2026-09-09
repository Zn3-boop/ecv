import type { LLMStatus, LLMStatusInfo } from '../hooks/useLLMStatus'
import { useAutoHideStatus } from '../hooks/useLLMStatus'

interface LLMStatusBadgeProps {
  statusInfo: LLMStatusInfo
  compact?: boolean
  autoHide?: boolean
}

const statusConfig: Record<LLMStatus, { icon: string; color: string; bg: string }> = {
  idle: { icon: '💤', color: '#9e9e9e', bg: '#f5f5f5' },
  thinking: { icon: '🤔', color: '#2196f3', bg: '#e3f2fd' },
  calling: { icon: '🔄', color: '#ff9800', bg: '#fff3e0' },
  success: { icon: '✅', color: '#4caf50', bg: '#e8f5e9' },
  error: { icon: '❌', color: '#f44336', bg: '#ffebee' },
  fallback: { icon: '⚠️', color: '#ff9800', bg: '#fff3e0' },
}

function formatDuration(ms?: number): string {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

export function LLMStatusBadge({ statusInfo, compact = false, autoHide = false }: LLMStatusBadgeProps) {
  const config = statusConfig[statusInfo.status]
  // 始终调用 hook，但根据 autoHide 决定是否使用其返回值
  const autoHideVisible = useAutoHideStatus(statusInfo)
  const visible = autoHide ? autoHideVisible : true

  if (!visible) return null

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: compact ? '4px' : '8px',
        padding: compact ? '2px 8px' : '4px 12px',
        borderRadius: '16px',
        backgroundColor: config.bg,
        color: config.color,
        fontSize: compact ? '12px' : '14px',
        fontWeight: 500,
        transition: 'all 0.2s ease',
      }}
      title={statusInfo.error || statusInfo.fallbackReason || statusInfo.message}
    >
      <span>{config.icon}</span>
      <span>{statusInfo.message}</span>
      {statusInfo.duration !== undefined && (
        <span style={{ opacity: 0.7, fontSize: compact ? '10px' : '12px' }}>
          ({formatDuration(statusInfo.duration)})
        </span>
      )}
      {statusInfo.status === 'fallback' && statusInfo.fallbackReason && !compact && (
        <span
          style={{
            fontSize: '11px',
            opacity: 0.8,
            maxWidth: '200px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          → {statusInfo.fallbackReason}
        </span>
      )}
      {statusInfo.status === 'error' && statusInfo.error && !compact && (
        <span
          style={{
            fontSize: '11px',
            opacity: 0.8,
            maxWidth: '200px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          → {statusInfo.error}
        </span>
      )}
    </div>
  )
}
