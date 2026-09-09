import type { SystemMetrics } from '../types'

interface MetricsCardProps {
  title: string
  metrics: SystemMetrics
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

export function MetricsCard({ title, metrics }: MetricsCardProps) {
  const cpuPercent = metrics.cpu.usagePercent
  const memPercent = metrics.memory.usagePercent
  const memUsed = metrics.memory.used
  const memTotal = metrics.memory.total
  // disk 使用 I/O 读写速度而非百分比
  const diskReadSpeed = metrics.disk.readLabel
  const diskWriteSpeed = metrics.disk.writeLabel

  const getBarColor = (percent: number) => {
    if (percent >= 90) return '#f44336'
    if (percent >= 70) return '#ff9800'
    return '#4caf50'
  }

  return (
    <div className="metrics-card">
      <h3>{title}</h3>
      
      <div className="metric-row">
        <span className="metric-label">CPU</span>
        <div className="metric-bar-container">
          <div
            className="metric-bar"
            style={{
              width: `${Math.min(cpuPercent, 100)}%`,
              backgroundColor: getBarColor(cpuPercent),
            }}
          />
        </div>
        <span className="metric-value">{cpuPercent.toFixed(1)}%</span>
      </div>

      <div className="metric-row">
        <span className="metric-label">Memory</span>
        <div className="metric-bar-container">
          <div
            className="metric-bar"
            style={{
              width: `${Math.min(memPercent, 100)}%`,
              backgroundColor: getBarColor(memPercent),
            }}
          />
        </div>
        <span className="metric-value">
          {memPercent.toFixed(1)}% ({formatBytes(memUsed)}/{formatBytes(memTotal)})
        </span>
      </div>

      <div className="metric-row">
        <span className="metric-label">Disk I/O</span>
        <div className="metric-bar-container">
          <div
            className="metric-bar"
            style={{
              width: '100%',
              backgroundColor: '#2196f3',
            }}
          />
        </div>
        <span className="metric-value">R: {diskReadSpeed} | W: {diskWriteSpeed}</span>
      </div>
    </div>
  )
}
