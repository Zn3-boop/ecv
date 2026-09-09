import type { SystemMetrics } from '../types'

interface HeaderProps {
  isElectronEnv: boolean
  preloadStatus: string
  agentStatus: string
  metrics: SystemMetrics | null
  error: string
  onRefreshMetrics: () => void
}

export function Header({
  isElectronEnv,
  preloadStatus,
  agentStatus,
  metrics,
  error,
  onRefreshMetrics,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="header-left">
        <h1>🖥️ AI Desktop Agent</h1>
        <span className="status-badge" data-env={isElectronEnv ? 'electron' : 'browser'}>
          {preloadStatus}
        </span>
      </div>
      <div className="header-center">
        <span className="agent-status">Agent: {agentStatus}</span>
      </div>
      <div className="header-right">
        <button onClick={onRefreshMetrics} title="刷新监控数据">
          🔄 刷新
        </button>
        {metrics && (
          <div className="quick-metrics">
            <span>CPU: {metrics.cpu.usagePercent.toFixed(1)}%</span>
            <span>MEM: {metrics.memory.usagePercent.toFixed(1)}%</span>
          </div>
        )}
        {error && <span className="error-indicator" title={error}>⚠️</span>}
      </div>
    </header>
  )
}
