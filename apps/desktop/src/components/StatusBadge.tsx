interface StatusBadgeProps {
  status: 'ok' | 'warning' | 'error' | 'loading' | 'unknown'
  text: string
  size?: 'small' | 'medium'
}

const statusColors: Record<StatusBadgeProps['status'], string> = {
  ok: '#4caf50',
  warning: '#ff9800',
  error: '#f44336',
  loading: '#2196f3',
  unknown: '#9e9e9e',
}

export function StatusBadge({ status, text, size = 'small' }: StatusBadgeProps) {
  return (
    <span
      className={`status-badge ${size}`}
      style={{
        backgroundColor: statusColors[status],
        color: 'white',
        padding: size === 'small' ? '2px 8px' : '4px 12px',
        borderRadius: '4px',
        fontSize: size === 'small' ? '12px' : '14px',
      }}
    >
      {text}
    </span>
  )
}
