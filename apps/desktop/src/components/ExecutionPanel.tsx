import { useState } from 'react'
import type { ActionLogEntry, PendingActionCommand, ActionExecutionResult } from '../types'

interface ExecutionPanelProps {
  executionLogs: ActionLogEntry[]
  pendingActions: PendingActionCommand[]
  isExecuting: boolean
  isPaused: boolean
  executionResults?: ActionExecutionResult[]
  onConfirmPending?: (ids: string[]) => void
  onRejectPending?: (ids: string[]) => void
  onPause?: () => void
  onResume?: () => void
  onClearLog?: () => void
}

export function ExecutionPanel({
  executionLogs,
  pendingActions,
  isExecuting,
  isPaused,
  executionResults = [],
  onConfirmPending,
  onRejectPending,
  onPause,
  onResume,
  onClearLog,
}: ExecutionPanelProps) {
  const [selectedPendingIds, setSelectedPendingIds] = useState<Set<string>>(new Set())
  const [activeTab, setActiveTab] = useState<'results' | 'logs' | 'pending'>('results')

  const togglePendingSelection = (id: string) => {
    setSelectedPendingIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const getStatusIcon = (result: ActionExecutionResult) => {
    if (result.skipped) return '⏭️'
    if (result.success) return '✅'
    return '❌'
  }

  const getStatusColor = (result: ActionExecutionResult) => {
    if (result.skipped) return '#f59e0b'
    if (result.success) return '#22c55e'
    return '#ef4444'
  }

  return (
    <section style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc', margin: '0 0 8px 0' }}>
          ⚡ 执行中心
        </h2>
        <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>
          查看执行结果、历史日志和待确认操作
        </p>
      </div>

      {/* 标签切换 */}
      <div style={{
        display: 'flex',
        gap: '4px',
        background: '#0f172a',
        padding: '4px',
        borderRadius: '10px',
        marginBottom: '20px',
        width: 'fit-content',
      }}>
        {([
          { key: 'results' as const, label: `执行结果 (${executionResults.length})` },
          { key: 'pending' as const, label: `待确认 (${pendingActions.length})` },
          { key: 'logs' as const, label: `历史日志 (${executionLogs.length})` },
        ]).map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: activeTab === tab.key ? 'rgba(59,130,246,0.2)' : 'transparent',
              color: activeTab === tab.key ? '#3b82f6' : '#94a3b8',
              fontSize: '13px',
              fontWeight: activeTab === tab.key ? 600 : 400,
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 控制按钮 */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        {isPaused ? (
          <button onClick={onResume} style={btnStyle('#22c55e')}>▶️ 恢复执行</button>
        ) : (
          <button onClick={onPause} style={btnStyle('#f59e0b')}>⏸️ 暂停执行</button>
        )}
        <button onClick={onClearLog} style={btnStyle('#64748b')}>🗑️ 清空记录</button>
        {isExecuting && (
          <span style={{ color: '#3b82f6', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="spinner">⏳</span> 执行中...
          </span>
        )}
      </div>

      {/* 执行结果标签 */}
      {activeTab === 'results' && (
        <div>
          {executionResults.length === 0 ? (
            <EmptyState icon="📭" title="暂无执行结果" desc="在任务中心选择任务并执行后将显示结果" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {executionResults.map((result, idx) => (
                <div key={result.id || idx} style={{
                  background: '#111827',
                  border: `1px solid ${getStatusColor(result)}33`,
                  borderRadius: '10px',
                  padding: '14px 16px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                    <span style={{ fontSize: '20px' }}>{getStatusIcon(result)}</span>
                    <span style={{ color: '#f8fafc', fontWeight: 600, fontSize: '14px' }}>
                      {result.tool}
                    </span>
                    <span style={{
                      marginLeft: 'auto',
                      fontSize: '12px',
                      color: getStatusColor(result),
                      fontWeight: 600,
                    }}>
                      {result.skipped ? '已跳过' : result.success ? '成功' : '失败'}
                    </span>
                  </div>
                  
                  {result.error && (
                    <div style={{
                      background: 'rgba(239,68,68,0.1)',
                      color: '#ef4444',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      fontSize: '13px',
                      marginBottom: '8px',
                    }}>
                      {result.error}
                      {result.code && <span style={{ opacity: 0.7 }}> ({result.code})</span>}
                      {result.blocked_reason && <div style={{ marginTop: '4px', fontSize: '12px' }}>原因: {result.blocked_reason}</div>}
                    </div>
                  )}
                  
                  {result.data !== undefined && result.data !== null && (
                    <div style={{
                      background: '#0f172a',
                      padding: '10px 12px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      color: '#94a3b8',
                      fontFamily: 'monospace',
                      overflow: 'auto',
                      maxHeight: '200px',
                    }}>
                      <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                        {typeof result.data === 'string' ? result.data : JSON.stringify(result.data, null, 2)}
                      </pre>
                    </div>
                  )}
                  
                  <div style={{ marginTop: '8px', fontSize: '12px', color: '#475569', display: 'flex', gap: '16px' }}>
                    {result.duration !== undefined && <span>⏱️ {result.duration}ms</span>}
                    <span>🆔 {result.id}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 待确认标签 */}
      {activeTab === 'pending' && (
        <div>
          {pendingActions.length === 0 ? (
            <EmptyState icon="✅" title="没有待确认操作" desc="所有操作已处理或暂无危险操作需要确认" />
          ) : (
            <div>
              <div style={{ marginBottom: '16px', display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => onConfirmPending?.(Array.from(selectedPendingIds))}
                  disabled={selectedPendingIds.size === 0}
                  style={btnStyle('#22c55e', selectedPendingIds.size === 0)}
                >
                  ✅ 确认执行 ({selectedPendingIds.size})
                </button>
                <button
                  onClick={() => onRejectPending?.(Array.from(selectedPendingIds))}
                  disabled={selectedPendingIds.size === 0}
                  style={btnStyle('#ef4444', selectedPendingIds.size === 0)}
                >
                  ❌ 拒绝 ({selectedPendingIds.size})
                </button>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {pendingActions.map((action) => (
                  <div key={action.id} style={{
                    background: '#111827',
                    border: `1px solid ${selectedPendingIds.has(action.id) ? '#ef4444' : '#1e293b'}`,
                    borderRadius: '10px',
                    padding: '14px 16px',
                    cursor: 'pointer',
                  }} onClick={() => togglePendingSelection(action.id)}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <input
                        type="checkbox"
                        checked={selectedPendingIds.has(action.id)}
                        onChange={() => {}}
                        style={{ cursor: 'pointer', accentColor: '#ef4444' }}
                      />
                      <span style={{ color: '#ef4444', fontSize: '12px', fontWeight: 600, border: '1px solid #ef4444', padding: '2px 8px', borderRadius: '4px' }}>
                        待确认
                      </span>
                      <span style={{ color: '#f8fafc', fontWeight: 600 }}>{action.tool}</span>
                    </div>
                    <div style={{ color: '#cbd5e1', fontSize: '13px', marginTop: '6px', paddingLeft: '28px' }}>
                      {action.reason}
                    </div>
                    {action.params && (
                      <div style={{ paddingLeft: '28px', marginTop: '6px', fontSize: '12px', color: '#64748b', fontFamily: 'monospace' }}>
                        {JSON.stringify(action.params)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 历史日志标签 */}
      {activeTab === 'logs' && (
        <div>
          {executionLogs.length === 0 ? (
            <EmptyState icon="📜" title="暂无历史日志" desc="执行操作后将记录历史" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {executionLogs.map((log, idx) => (
                <div key={log.batchId || idx} style={{
                  background: '#111827',
                  border: '1px solid #1e293b',
                  borderRadius: '10px',
                  padding: '14px 16px',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <span style={{ color: '#f8fafc', fontWeight: 600, fontSize: '14px' }}>
                      批次 {log.batchId}
                    </span>
                    <span style={{ color: '#475569', fontSize: '12px' }}>
                      {new Date(log.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
                    {log.commands.map(cmd => (
                      <span key={cmd.id} style={{
                        fontSize: '12px',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        background: cmd.type === 'destructive' ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.15)',
                        color: cmd.type === 'destructive' ? '#ef4444' : '#3b82f6',
                      }}>
                        {cmd.tool}
                      </span>
                    ))}
                  </div>
                  <div style={{ fontSize: '12px', color: '#64748b' }}>
                    结果: {log.results.filter((r: ActionExecutionResult) => r.success).length} 成功 / {log.results.filter((r: ActionExecutionResult) => !r.success && !r.skipped).length} 失败 / {log.results.filter((r: ActionExecutionResult) => r.skipped).length} 跳过
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: '#64748b' }}>
      <div style={{ fontSize: '40px', marginBottom: '12px' }}>{icon}</div>
      <p style={{ margin: '0 0 8px 0', color: '#94a3b8', fontSize: '16px', fontWeight: 600 }}>{title}</p>
      <p style={{ margin: 0, fontSize: '13px' }}>{desc}</p>
    </div>
  )
}

function btnStyle(color: string, disabled = false): React.CSSProperties {
  return {
    background: disabled ? '#334155' : color,
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  }
}
