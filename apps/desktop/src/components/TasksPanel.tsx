import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useVoiceRecorder } from '../hooks/useVoiceRecorder'
import type { ActionCommand, ActionExecutionResult, SystemMetrics } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

interface AgentAnalysis {
  analysis: string
  thinking: string
  advice: string
  riskWarning: string
}

interface TasksPanelProps {
  metrics: SystemMetrics | null
  suggestedCommands: ActionCommand[]
  setSuggestedCommands: React.Dispatch<React.SetStateAction<ActionCommand[]>>
  isExecuting: boolean
  onExecuteSelected: (commands: ActionCommand[]) => Promise<void>
  executionResults: ActionExecutionResult[]
  onAnalyzeProblem?: (text: string) => void
  agentAnalysis?: AgentAnalysis | null
}

export function TasksPanel({
  metrics,
  suggestedCommands,
  setSuggestedCommands,
  isExecuting,
  onExecuteSelected,
  executionResults,
  onAnalyzeProblem,
  agentAnalysis,
}: TasksPanelProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [analyzeText, setAnalyzeText] = useState('帮我看看当前系统状态，给出处置建议')
  const [showThinking, setShowThinking] = useState(false)
  
  const validCommands = useMemo(() => 
    suggestedCommands.filter(cmd => {
      if (cmd.tool === 'process:kill') {
        const hasValidPid = typeof cmd.params?.pid === 'number' && cmd.params.pid > 0
        const hasValidName = typeof cmd.params?.name === 'string' && cmd.params.name.length > 0
        return hasValidPid || hasValidName
      }
      return true
    }), 
  [suggestedCommands])

  const validCommandIds = useMemo(() => new Set(validCommands.map(c => c.id)), [validCommands])

  const activeSelectedIds = useMemo(() => {
    const active = new Set<string>()
    for (const id of selectedIds) {
      if (validCommandIds.has(id)) active.add(id)
    }
    return active
  }, [selectedIds, validCommandIds])

  const prevAnalysisRef = useRef<string | null>(null)
  if (agentAnalysis?.analysis !== prevAnalysisRef.current) {
    prevAnalysisRef.current = agentAnalysis?.analysis ?? null
    if (agentAnalysis) {
      setSelectedIds(new Set())
    }
  }

  // 🆕 清理重复命令
  const handleCleanDuplicates = useCallback(() => {
    const seen = new Set<string>()
    const unique = suggestedCommands.filter(cmd => {
      const sig = `${cmd.tool}::${JSON.stringify(cmd.params || {})}`
      if (seen.has(sig)) return false
      seen.add(sig)
      return true
    })
    if (unique.length !== suggestedCommands.length) {
      setSuggestedCommands(unique)
      setSelectedIds(new Set())
    }
  }, [suggestedCommands, setSuggestedCommands])

  // 🆕 统一添加命令到任务列表（自动去重 + 自动选中）
  const handleAddCommand = useCallback((cmd: ActionCommand) => {
    let existingId: string | null = null
    setSuggestedCommands(prev => {
      const sig = `${cmd.tool}::${JSON.stringify(cmd.params || {})}`
      const existing = prev.find(c => `${c.tool}::${JSON.stringify(c.params || {})}` === sig)
      if (existing) {
        existingId = existing.id
        return prev
      }
      return [...prev, cmd]
    })
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.add(existingId || cmd.id)
      return next
    })
  }, [setSuggestedCommands])

  const {
    isRecording,
    transcript: voiceTranscript,
    loading: voiceLoading,
    error: voiceError,
    stage,
    debugInfo,
    startRecording,
    stopRecording,
    clearTranscript,
  } = useVoiceRecorder(API_BASE)

  // 语音转写结果自动填入并触发分析
  useEffect(() => {
    if (!voiceTranscript) return
    
    // 延迟执行以避免同步 setState 警告
    const timer = setTimeout(() => {
      setAnalyzeText(voiceTranscript)
      clearTranscript()
      onAnalyzeProblem?.(voiceTranscript)
    }, 0)
    
    return () => clearTimeout(timer)
  }, [voiceTranscript, clearTranscript, onAnalyzeProblem])

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    if (activeSelectedIds.size === validCommands.length && validCommands.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(validCommands.map(c => c.id)))
    }
  }, [activeSelectedIds.size, validCommands])

  const handleExecute = useCallback(() => {
    const selected = validCommands.filter(c => activeSelectedIds.has(c.id))
    if (selected.length === 0) return
    void onExecuteSelected(selected)
  }, [activeSelectedIds, validCommands, onExecuteSelected])

  const getResultForCommand = (id: string) => executionResults.find(r => r.id === id)

  const getBarColor = (value: number) => {
    if (value >= 90) return '#ef4444'
    if (value >= 75) return '#f59e0b'
    return '#22c55e'
  }

  const hasDangerousSelected = validCommands.some(
    c => activeSelectedIds.has(c.id) && (c.type === 'destructive' || c.risk === 'high')
  )

  return (
    <section style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      {/* 头部 */}
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc', margin: '0 0 8px 0' }}>
          🖥️ 系统监控 & 任务中心
        </h2>
        <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>
          实时监控系统状态，AI 分析后选择任务批量执行
        </p>
      </div>

      {/* 监控卡片 */}
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
          <MetricCard
            label="CPU 使用率"
            value={`${metrics.cpu.usagePercent.toFixed(1)}%`}
            subtext={`${metrics.cpu.model} · ${metrics.cpu.cores} 核`}
            percent={metrics.cpu.usagePercent}
            color={getBarColor(metrics.cpu.usagePercent)}
          />
          <MetricCard
            label="内存使用"
            value={`${metrics.memory.usagePercent.toFixed(1)}%`}
            subtext={`${metrics.memory.usedLabel} / ${metrics.memory.totalLabel}`}
            percent={metrics.memory.usagePercent}
            color={getBarColor(metrics.memory.usagePercent)}
          />
          <MetricCard
            label="网络 I/O"
            value={`↓${metrics.network.bytesRecvPerSec || '--'}/s ↑${metrics.network.bytesSentPerSec || '--'}/s`}
            subtext={`总计 ↓${metrics.network.recvLabel || '--'} ↑${metrics.network.sentLabel || '--'}`}
            percent={0}
            color="#3b82f6"
          />
        </div>
      )}

      {/* 告警横幅 */}
      {metrics?.alerts && metrics.alerts.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          {metrics.alerts.map((alert, idx) => (
            <AlertBanner key={idx} level={alert.level} title={alert.title} message={alert.message} />
          ))}
        </div>
      )}

      {/* 🆕 Agent 分析卡片 */}
      {agentAnalysis && (
        <div style={{
          background: '#111827',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: '20px',
          marginBottom: '24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <span style={{ fontSize: '20px' }}>🤖</span>
            <span style={{ color: '#3b82f6', fontSize: '15px', fontWeight: 700 }}>AI 诊断分析</span>
          </div>
          
          <div style={{ color: '#f8fafc', fontSize: '16px', fontWeight: 600, marginBottom: '16px', lineHeight: 1.5 }}>
            {agentAnalysis.analysis || '正在分析系统状态...'}
          </div>
          
          {/* 思考过程 */}
          {agentAnalysis.thinking && (
            <div style={{ marginBottom: '16px' }}>
              <button
                onClick={() => setShowThinking(!showThinking)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: 0,
                }}
              >
                <span>{showThinking ? '▼' : '▶'}</span>
                查看 AI 分析过程
              </button>
              {showThinking && (
                <div style={{
                  marginTop: '10px',
                  padding: '14px',
                  background: '#0f172a',
                  borderRadius: '8px',
                  color: '#94a3b8',
                  fontSize: '13px',
                  lineHeight: 1.7,
                  whiteSpace: 'pre-line',
                }}>
                  {agentAnalysis.thinking}
                </div>
              )}
            </div>
          )}
          
          {/* 解决方案 */}
          {agentAnalysis.advice && (
            <div style={{
              background: 'rgba(59,130,246,0.08)',
              border: '1px solid rgba(59,130,246,0.25)',
              borderRadius: '10px',
              padding: '16px',
              marginBottom: '12px',
            }}>
              <div style={{ color: '#3b82f6', fontSize: '13px', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>💡</span> 解决方案
              </div>
              <div style={{ color: '#cbd5e1', fontSize: '14px', lineHeight: 1.7, whiteSpace: 'pre-line' }}>
                {agentAnalysis.advice}
              </div>
            </div>
          )}
          
          {/* 风险提示 */}
          {agentAnalysis.riskWarning && (
            <div style={{
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.25)',
              borderRadius: '10px',
              padding: '16px',
            }}>
              <div style={{ color: '#ef4444', fontSize: '13px', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>⚠️</span> 风险提示
              </div>
              <div style={{ color: '#fca5a5', fontSize: '14px', lineHeight: 1.6 }}>
                {agentAnalysis.riskWarning}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 输入区 */}
      <div style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: '12px',
        padding: '16px',
        marginBottom: '24px',
      }}>
        <label style={{ color: '#94a3b8', fontSize: '13px', display: 'block', marginBottom: '12px' }}>
          💬 输入问题，AI 将分析并生成可执行任务
        </label>
        
        {/* 语音输入 */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', marginBottom: '10px' }}>
          <button
            onMouseDown={startRecording}
            onMouseUp={stopRecording}
            onTouchStart={startRecording}
            onTouchEnd={stopRecording}
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '50%',
              border: 'none',
              background: isRecording ? '#ef4444' : '#3b82f6',
              color: '#fff',
              fontSize: '20px',
              cursor: 'pointer',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: isRecording ? '0 0 20px rgba(239,68,68,0.5)' : '0 2px 8px rgba(59,130,246,0.3)',
              transition: 'all 0.2s',
            }}
            title={isRecording ? '松开结束录音' : '按住说话 (Whisper本地识别)'}
          >
            {isRecording ? '🔴' : '🎤'}
          </button>
          
          <div style={{ flex: 1 }}>
            <input
              type="text"
              value={analyzeText}
              onChange={(e) => setAnalyzeText(e.target.value)}
              placeholder={isRecording ? '正在录音...' : '例如：帮我看看CPU为什么那么高'}
              disabled={voiceLoading}
              style={{
                width: '100%',
                background: '#0f172a',
                border: `1px solid ${isRecording ? '#ef4444' : voiceError ? '#ef4444' : '#334155'}`,
                borderRadius: '8px',
                padding: '12px 14px',
                color: '#f8fafc',
                fontSize: '14px',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            {/* 状态提示 */}
            <div style={{ marginTop: '6px', fontSize: '12px' }}>
              {isRecording ? (
                <span style={{ color: '#ef4444' }}>🔴 正在录音... 松开结束</span>
              ) : voiceLoading ? (
                <span style={{ color: '#3b82f6' }}>
                  ⏳ {stage === 'uploading' ? '上传音频到本地Whisper...' : stage === 'transcribing' ? 'Whisper识别中...' : '处理中...'}
                </span>
              ) : voiceError ? (
                <span style={{ color: '#ef4444' }}>⚠️ {voiceError}</span>
              ) : (
                <span style={{ color: '#64748b' }}>🎤 按住麦克风说话，本地Whisper识别（无需联网）</span>
              )}
            </div>
            {/* 调试信息 */}
            {debugInfo && (
              <div style={{ marginTop: '4px', fontSize: '11px', color: '#475569', fontFamily: 'monospace' }}>
                {debugInfo}
              </div>
            )}
          </div>
          
          <button
            onClick={() => onAnalyzeProblem?.(analyzeText)}
            disabled={isExecuting || !analyzeText.trim() || voiceLoading}
            style={{
              background: isExecuting || voiceLoading ? '#334155' : '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              padding: '12px 24px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: isExecuting || voiceLoading ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              height: '48px',
            }}
          >
            {voiceLoading ? '识别中...' : isExecuting ? '分析中...' : '🤖 AI 分析'}
          </button>
        </div>
      </div>

      {/* 任务列表 */}
      <div style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: '12px',
        padding: '16px',
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}>
          <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            📋 建议执行的任务
            {validCommands.length > 0 && (
              <span style={{
                background: '#1e293b',
                color: '#94a3b8',
                fontSize: '12px',
                padding: '2px 10px',
                borderRadius: '6px',
              }}>
                {validCommands.length}
              </span>
            )}
          </h3>
          {validCommands.length > 0 && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {/* 🆕 清理重复按钮 */}
              <button
                onClick={handleCleanDuplicates}
                style={{
                  background: '#1e293b',
                  color: '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '4px 12px',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
                title="清理重复任务"
              >
                🧹 清理重复
              </button>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#94a3b8', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={activeSelectedIds.size === validCommands.length && validCommands.length > 0}
                  onChange={toggleAll}
                  style={{ cursor: 'pointer' }}
                />
                全选
              </label>
            </div>
          )}
        </div>

        {validCommands.length === 0 ? (
          <EmptyState icon="📭" title="暂无建议任务" desc="输入问题或语音描述后，AI 将分析并生成可执行任务" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {validCommands.map((cmd) => {
              const isSelected = activeSelectedIds.has(cmd.id)
              const isDangerous = cmd.type === 'destructive' || cmd.risk === 'high'
              const result = getResultForCommand(cmd.id)
              const typeConfig = {
                read: { label: '👁️ 查看', color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
                write: { label: '📝 写入', color: '#8b5cf6', bg: 'rgba(139,92,246,0.15)' },
                destructive: { label: '⚠️ 危险', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
                system: { label: '🔧 系统', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
                network: { label: '🌐 网络', color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
              }[cmd.type] || { label: '📋 操作', color: '#64748b', bg: 'rgba(100,116,139,0.15)' }

              const needsConfirmation = (cmd.confidence || 0.8) < 0.7
              const confidencePercent = Math.round((cmd.confidence || 0.8) * 100)
              const confidenceColor = confidencePercent >= 90 ? '#22c55e' : confidencePercent >= 70 ? '#f59e0b' : '#ef4444'

              return (
                <div
                  key={cmd.id}
                  onClick={() => toggleSelection(cmd.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '14px 16px',
                    borderRadius: '10px',
                    border: `1px solid ${isSelected ? (isDangerous ? '#ef4444' : '#3b82f6') : needsConfirmation ? '#f59e0b' : '#1e293b'}`,
                    background: isSelected ? (isDangerous ? 'rgba(239,68,68,0.08)' : 'rgba(59,130,246,0.08)') : needsConfirmation ? 'rgba(245,158,11,0.04)' : 'transparent',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => { e.stopPropagation(); toggleSelection(cmd.id) }}
                    style={{ marginTop: '2px', cursor: 'pointer', accentColor: isDangerous ? '#ef4444' : '#3b82f6' }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
                      <span style={{
                        fontSize: '12px',
                        fontWeight: 600,
                        padding: '3px 10px',
                        borderRadius: '6px',
                        color: typeConfig.color,
                        background: typeConfig.bg,
                      }}>
                        {typeConfig.label}
                      </span>
                      <span style={{ color: '#f8fafc', fontSize: '14px', fontWeight: 600 }}>{cmd.tool}</span>
                      {isDangerous && (
                        <span style={{ fontSize: '11px', color: '#ef4444', border: '1px solid #ef4444', padding: '1px 8px', borderRadius: '4px' }}>
                          需确认
                        </span>
                      )}
                      {needsConfirmation && (
                        <span style={{ fontSize: '11px', color: '#f59e0b', border: '1px solid #f59e0b', padding: '1px 8px', borderRadius: '4px' }}>
                          ⚠️ 需确认
                        </span>
                      )}
                      {cmd.recommended && (
                        <span style={{ fontSize: '11px', color: '#22c55e' }}>⭐ AI推荐</span>
                      )}
                      <span style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        color: confidenceColor,
                        background: `${confidenceColor}15`,
                        marginLeft: 'auto',
                      }}>
                        {confidencePercent}%
                      </span>
                    </div>
                    <div style={{ color: '#cbd5e1', fontSize: '13px', marginBottom: '4px' }}>
                      {cmd.reason}
                    </div>
                    {cmd.reasoning && (
                      <div style={{
                        fontSize: '12px',
                        color: '#94a3b8',
                        fontStyle: 'italic',
                        marginBottom: '4px',
                        padding: '4px 8px',
                        background: 'rgba(148,163,184,0.06)',
                        borderRadius: '4px',
                        borderLeft: '2px solid #475569',
                      }}>
                        🤔 {cmd.reasoning}
                      </div>
                    )}
                    {cmd.params && Object.keys(cmd.params).length > 0 && (
                      <div style={{ fontSize: '12px', color: '#64748b', fontFamily: 'monospace', background: '#0f172a', padding: '6px 10px', borderRadius: '6px', wordBreak: 'break-all' }}>
                        {JSON.stringify(cmd.params)}
                      </div>
                    )}
                    {/* 🆕 执行结果展示 */}
                    {result && <ExecutionResult result={result} tool={cmd.tool} onAddCommand={handleAddCommand} />}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* 执行按钮 */}
        {validCommands.length > 0 && (
          <div style={{
            marginTop: '20px',
            paddingTop: '16px',
            borderTop: '1px solid #1e293b',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <span style={{ color: '#94a3b8', fontSize: '14px' }}>
              已选择 <strong style={{ color: '#f8fafc' }}>{activeSelectedIds.size}</strong> / {validCommands.length} 个任务
              {hasDangerousSelected && (
                <span style={{ color: '#ef4444', marginLeft: '8px', fontSize: '13px' }}>
                  (包含危险操作)
                </span>
              )}
            </span>
            <button
              onClick={handleExecute}
              disabled={isExecuting || activeSelectedIds.size === 0}
              style={{
                background: isExecuting ? '#334155' : hasDangerousSelected ? '#dc2626' : '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                padding: '10px 24px',
                fontSize: '14px',
                fontWeight: 700,
                cursor: isExecuting || activeSelectedIds.size === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              {isExecuting ? '⏳ 执行中...' : `▶️ 执行选中的 ${activeSelectedIds.size} 个任务`}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

// ============ 子组件 ============

function MetricCard({ label, value, subtext, percent, color }: {
  label: string; value: string; subtext: string; percent: number; color: string
}) {
  return (
    <div style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{ color: '#94a3b8', fontSize: '13px' }}>{label}</span>
        <span style={{ color: '#f8fafc', fontSize: '20px', fontWeight: 700 }}>{value}</span>
      </div>
      {percent > 0 && (
        <div style={{ height: '8px', background: '#0f172a', borderRadius: '4px', overflow: 'hidden', marginBottom: '10px' }}>
          <div style={{ height: '100%', width: `${Math.min(percent, 100)}%`, background: color, borderRadius: '4px', transition: 'width 0.5s ease' }} />
        </div>
      )}
      <div style={{ fontSize: '12px', color: '#64748b' }}>{subtext}</div>
    </div>
  )
}

function AlertBanner({ level, title, message }: { level: string; title: string; message: string }) {
  return (
    <div style={{
      background: level === 'critical' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
      border: `1px solid ${level === 'critical' ? '#ef4444' : '#f59e0b'}`,
      borderRadius: '10px',
      padding: '14px 16px',
      marginBottom: '10px',
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px',
    }}>
      <span style={{ fontSize: '20px' }}>{level === 'critical' ? '🔴' : '🟡'}</span>
      <div>
        <div style={{ color: '#f8fafc', fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>{title}</div>
        <div style={{ color: '#94a3b8', fontSize: '13px' }}>{message}</div>
      </div>
    </div>
  )
}

function ExecutionResult({ result, tool, onAddCommand }: { 
  result: ActionExecutionResult; 
  tool: string; 
  onAddCommand?: (cmd: ActionCommand) => void 
}) {
  if (!result) return null

  return (
    <div style={{
      marginTop: '10px',
      padding: '12px',
      borderRadius: '8px',
      fontSize: '13px',
      background: result.success ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
      border: `1px solid ${result.success ? '#22c55e33' : '#ef444433'}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span>{result.success ? '✅' : '❌'}</span>
        <span style={{ color: result.success ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
          {result.success ? '执行成功' : (result.error || '执行失败')}
        </span>
        {result.duration !== undefined && <span style={{ color: '#475569', fontSize: '12px', marginLeft: 'auto' }}>{result.duration}ms</span>}
      </div>

      {result.success && Boolean(result.data) ? <ResultData tool={tool} data={result.data as object} onAddCommand={onAddCommand} /> : null}
      
      {result.error && (
        <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>
          {result.error}{result.code && <span style={{ opacity: 0.7 }}> ({result.code})</span>}
        </div>
      )}
    </div>
  )
}

function ResultData({ tool, data, onAddCommand }: { 
  tool: string; 
  data: object | null; 
  onAddCommand?: (cmd: ActionCommand) => void 
}) {
  if (!data) return null

  // 进程列表 - 带结束按钮
  if ((tool === 'process:top' || tool === 'process:list') && typeof data === 'object' && data !== null && 'processes' in data) {
    const d = data as { processes: Array<{ name: string; pid: number; mem: number }> }
    // 🆕 完整系统进程黑名单 - 与后端 PROTECTED_PROCESS_NAMES 保持一致
    const SYSTEM_PROCS = new Set([
      'dwm', 'csrss', 'winlogon', 'services', 'lsass',
      'svchost', 'smss', 'system', 'registry', 'memory compression',
      'secure system', 'system idle process', 'fontdrvhost', 'wininit',
      'lsaiso', 'wudfhost', 'wudfcompanionhost',
      'explorer', // 🆕 恢复保护，避免前端显示结束按钮后端却拦截
      'wmiexe', 'searchindexer', 'sihost', 'taskhostw',
      'runtimebroker', 'shellexperiencehost', 'startmenuexperiencehost',
      'textinputhost', 'securityhealthservice', 'securityhealthsystray'
    ])
    
    return (
      <div style={{ overflow: 'auto', maxHeight: '320px' }}>
        <div style={{ fontSize: 11, color: '#888', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{tool === 'process:top' ? '🔥 高内存占用进程' : '进程列表'}（点击结束可释放资源）</span>
          {/* 🆕 一键结束 Top 3 */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              const top3 = d.processes.slice(0, 3).filter(p => {
                const pNameNoExt = (p.name || '').toLowerCase().replace(/\.exe$/, '')
                return !SYSTEM_PROCS.has(pNameNoExt)
              })
              if (top3.length === 0) {
                alert('前 3 个进程均为系统进程，不可结束')
                return
              }
              if (window.confirm(`一键结束 Top ${top3.length} 高内存进程？\n${top3.map(p => `• ${p.name} (${(p.mem/1024).toFixed(0)}MB)`).join('\n')}`)) {
                top3.forEach(p => {
                  onAddCommand?.({
                    id: `kill-${p.pid}-${Date.now()}`,
                    tool: 'process:kill',
                    type: 'destructive',
                    params: { pid: p.pid },
                    reason: `结束高内存进程 ${p.name} 释放资源`,
                    confidence: 0.9,
                    risk: 'high',
                    require_confirmation: true,
                  })
                })
              }
            }}
            style={{
              padding: '2px 8px', fontSize: 11, borderRadius: 4,
              border: '1px solid #ff4d4f', background: 'rgba(255,77,79,0.15)',
              color: '#ff4d4f', cursor: 'pointer'
            }}
          >
            ⚡ 一键结束 Top 3
          </button>
        </div>
        {d.processes.map((p, i) => {
          // 🆕 精确匹配：统一去掉 .exe 后缀再匹配
          const pNameNoExt = (p.name || '').toLowerCase().replace(/\.exe$/, '')
          const isSysProc = SYSTEM_PROCS.has(pNameNoExt)
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 8px', borderBottom: '1px solid #1e293b',
              background: i === 0 && tool === 'process:top' ? '#1f1f1f' : 'transparent'
            }}>
              <span style={{ width: 24, textAlign: 'center', fontSize: 11, color: '#666' }}>
                {i === 0 && tool === 'process:top' ? '🔥' : i + 1}
              </span>
              <span style={{ flex: 1, fontSize: 12, color: '#ccc', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {p.name}
              </span>
              <span style={{ fontSize: 11, color: '#faad14', width: 60, textAlign: 'right' }}>
                {(p.mem / 1024).toFixed(0)} MB
              </span>
              <span style={{ fontSize: 11, color: '#666', width: 50, textAlign: 'right' }}>
                {p.pid}
              </span>
              {!isSysProc ? (
              <button
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`确定结束 ${p.name} (PID: ${p.pid})？\n未保存的数据将丢失。`)) {
                      // 🆕 直接通过 API 执行 kill，不加入任务列表
                      fetch(`${API_BASE}/api/tools/execute`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tool: 'process:kill', params: { pid: p.pid }, force: true })
                      }).then(res => res.json()).then(data => {
                        if (data.success || data.data?.success) {
                          alert(`✅ 已结束 ${p.name} (PID: ${p.pid})`)
                          // 刷新页面以更新进程列表
                          window.location.reload()
                        } else {
                          alert(`❌ 结束失败: ${data.error || data.data?.error || '未知错误'}`)
                        }
                      }).catch(err => {
                        alert(`❌ 请求失败: ${err.message}`)
                      })
                    }
                  }}
                  style={{
                    padding: '2px 8px', fontSize: 11, borderRadius: 4,
                    border: '1px solid #ff4d4f', background: 'transparent',
                    color: '#ff4d4f', cursor: 'pointer'
                  }}
                >
                  结束
                </button>
              ) : (
                <span style={{ fontSize: 11, color: '#444', width: 32 }}>系统</span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  // 磁盘列表
  if (tool === 'disk:list' && typeof data === 'object' && data !== null && 'drives' in data) {
    const d = data as { drives: Array<{ name: string; used: number; free: number; usePercent: number }> }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {d.drives.map((drive, i) => (
          <div key={i} style={{ background: '#0f172a', padding: '10px', borderRadius: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{drive.name}:盘</span>
              <span style={{ color: drive.usePercent > 85 ? '#ef4444' : drive.usePercent > 70 ? '#f59e0b' : '#22c55e', fontWeight: 600 }}>{drive.usePercent}% 已用</span>
            </div>
            <div style={{ height: '6px', background: '#1e293b', borderRadius: '3px', overflow: 'hidden', marginBottom: '6px' }}>
              <div style={{ height: '100%', width: `${Math.min(drive.usePercent, 100)}%`, background: drive.usePercent > 85 ? '#ef4444' : drive.usePercent > 70 ? '#f59e0b' : '#22c55e', borderRadius: '3px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
              <span>已用 {(drive.used / 1024 / 1024 / 1024).toFixed(1)} GB</span>
              <span>剩余 {(drive.free / 1024 / 1024 / 1024).toFixed(1)} GB</span>
            </div>
          </div>
        ))}
      </div>
    )
  }

  // 临时文件扫描
  if (tool === 'temp:scan' && typeof data === 'object' && data !== null && 'entries' in data) {
    const d = data as { entries: Array<{ name: string; size: number; isTempLike: boolean }>; total: number }
    const tempFiles = d.entries.filter((e) => e.isTempLike)
    return (
      <div>
        <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '8px' }}>
          共 {d.total} 个文件，其中 <span style={{ color: '#f59e0b' }}>{tempFiles.length}</span> 个可清理
        </div>
        <div style={{ maxHeight: '200px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {tempFiles.slice(0, 15).map((e, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 8px', background: '#0f172a', borderRadius: '4px', fontSize: '11px' }}>
              <span style={{ color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.name}</span>
              <span style={{ color: '#64748b', flexShrink: 0, marginLeft: '8px' }}>{(e.size / 1024).toFixed(0)} KB</span>
            </div>
          ))}
          {tempFiles.length > 15 && <div style={{ color: '#475569', fontSize: '11px', textAlign: 'center' }}>...还有 {tempFiles.length - 15} 个文件</div>}
        </div>
      </div>
    )
  }

  // app:launch 展示 —— 让用户看见"到底打开没"
  if (tool === 'app:launch' && typeof data === 'object' && data !== null) {
    const d = data as { launched?: string; method?: string; message?: string; error?: string; verified?: boolean }
    return (
      <div style={{ padding: '8px', background: '#0f172a', borderRadius: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '16px' }}>🚀</span>
          <span style={{ color: '#22c55e', fontWeight: 600, fontSize: '13px' }}>
            {d.message || `已启动 ${d.launched || '应用'}`}
          </span>
        </div>
        {d.verified !== undefined && (
          <div style={{ fontSize: '11px', color: d.verified ? '#22c55e' : '#f59e0b' }}>
            {d.verified ? '✓ 检测到进程已运行' : '⏳ 启动命令已发送，请检查任务栏'}
          </div>
        )}
        {d.error && (
          <div style={{ fontSize: '11px', color: '#ef4444', marginTop: '4px' }}>
            ⚠️ {d.error}
          </div>
        )}
      </div>
    )
  }

  // process:kill 展示 —— 让用户看见"到底杀掉没"
  if (tool === 'process:kill' && typeof data === 'object' && data !== null) {
    const d = data as { killed?: number; process?: { name?: string; pid?: number }; verified?: boolean; warning?: string }
    const procName = d.process?.name || '未知进程'
    const pid = d.killed || d.process?.pid || '?'
    return (
      <div style={{ padding: '8px', background: '#0f172a', borderRadius: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '16px' }}>💀</span>
          <span style={{ color: d.verified !== false ? '#ef4444' : '#f59e0b', fontWeight: 600, fontSize: '13px' }}>
            已结束 {procName} (PID: {pid})
          </span>
        </div>
        {d.verified === true && (
          <div style={{ fontSize: '11px', color: '#22c55e' }}>✓ 已确认进程已消失</div>
        )}
        {d.verified === false && (
          <div style={{ fontSize: '11px', color: '#f59e0b' }}>
            ⚠️ 命令已执行，但进程可能仍在运行
            {d.warning && <div style={{ marginTop: '4px' }}>{d.warning}</div>}
          </div>
        )}
      </div>
    )
  }

  // 系统信息
  if (tool === 'system:info' && typeof data === 'object' && data !== null) {
    const d = data as { platform?: string; arch?: string; cpus?: number; totalMem?: number; uptime?: number }
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '12px' }}>
        <InfoItem label="平台" value={`${d.platform || 'unknown'} ${d.arch || ''}`} />
        <InfoItem label="CPU" value={`${d.cpus || 0} 核`} />
        <InfoItem label="总内存" value={`${((d.totalMem || 0) / 1024 / 1024 / 1024).toFixed(1)} GB`} />
        <InfoItem label="运行时长" value={`${((d.uptime || 0) / 3600).toFixed(1)} 小时`} />
      </div>
    )
  }

  // 🆕 disk:cleanup_advanced 展示
  if (tool === 'disk:cleanup_advanced' && typeof data === 'object' && data !== null) {
    const d = data as { 
      deletedCount: number; 
      skippedCount: number; 
      deleted?: Array<{ path?: string; source?: string; method?: string }>; 
      skipped?: Array<{ path?: string; reason?: string; source?: string }>;
      message?: string;
    }
    return (
      <div>
        <div style={{ color: d.deletedCount > 0 ? '#22c55e' : '#f59e0b', fontWeight: 600, marginBottom: '8px' }}>
          {d.deletedCount > 0 ? `✅ ${d.message || `已清理 ${d.deletedCount} 个文件`}` : `⚠️ ${d.message || '未找到可清理文件'}`}
        </div>
        {d.deleted && d.deleted.length > 0 && (
          <div style={{ maxHeight: '100px', overflow: 'auto', marginBottom: '8px' }}>
            {d.deleted.slice(0, 10).map((item, i) => (
              <div key={i} style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace', padding: '2px 0' }}>
                🗑️ [{item.source}] {item.path?.split(/[\\/]/).pop()}
                {item.method && <span style={{ color: '#52c41a', marginLeft: 6 }}>({item.method})</span>}
              </div>
            ))}
            {d.deleted.length > 10 && <div style={{ color: '#475569', fontSize: '11px' }}>...还有 {d.deleted.length - 10} 个</div>}
          </div>
        )}
        {d.skipped && d.skipped.length > 0 && (
          <div style={{ marginTop: 10, padding: 10, background: '#1f1f1f', borderRadius: 6 }}>
            <div style={{ color: '#faad14', fontSize: 12, marginBottom: 6 }}>
              ⚠️ 跳过 {d.skippedCount || d.skipped.length} 个
            </div>
            <div style={{ maxHeight: 100, overflowY: 'auto' }}>
              {d.skipped.map((item, idx) => (
                <div key={idx} style={{ fontSize: 11, color: '#888', padding: '3px 0', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.path?.split(/[\\/]/).pop()}
                  </span>
                  <span style={{ color: '#ff4d4f', flexShrink: 0, maxWidth: '45%', textAlign: 'right' }}>
                    {item.reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // 清理结果 - 兼容新旧格式
  if ((tool === 'temp:cleanup' || tool === 'disk:cleanup') && typeof data === 'object' && data !== null && 'deleted' in data) {
    const d = data as { deletedCount: number; deleted?: Array<{ path?: string; method?: string } | string>; skipped?: Array<{ path?: string; reason?: string } | string>; skippedCount?: number }
    const safeFileName = (item: { path?: string; method?: string } | string) => {
      if (typeof item === 'string') return item.split(/[\\/]/).pop() || item
      if (item?.path && typeof item.path === 'string') return item.path.split(/[\\/]/).pop() || item.path
      return '未知文件'
    }
    const safeReason = (item: { reason?: string; method?: string } | string) => {
      if (typeof item === 'string') return '无法删除'
      return item?.reason || item?.method || '未知状态'
    }
    return (
      <div>
        <div style={{ color: '#22c55e', fontWeight: 600, marginBottom: '8px' }}>✅ 已清理 {d.deletedCount} 个文件</div>
        
        {/* 已删除列表 */}
        {d.deleted && d.deleted.length > 0 && (
          <div style={{ maxHeight: '100px', overflow: 'auto', marginBottom: '8px' }}>
            {d.deleted.slice(0, 10).map((item, i) => (
              <div key={i} style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace', padding: '2px 0' }}>
                🗑️ {safeFileName(item)}
                {typeof item === 'object' && item?.method && (
                  <span style={{ color: '#52c41a', marginLeft: 6 }}>({item.method})</span>
                )}
              </div>
            ))}
          </div>
        )}
        
        {/* 未删除列表 */}
        {d.skipped && d.skipped.length > 0 && (
          <div style={{ marginTop: 10, padding: 10, background: '#1f1f1f', borderRadius: 6 }}>
            <div style={{ color: '#faad14', fontSize: 12, marginBottom: 6 }}>
              ⚠️ 未能删除 {d.skippedCount || d.skipped.length} 个
            </div>
            <div style={{ maxHeight: 100, overflowY: 'auto' }}>
              {d.skipped.map((item, idx) => (
                <div key={idx} style={{ 
                  fontSize: 11, color: '#888', 
                  padding: '3px 0', borderBottom: '1px solid #333',
                  display: 'flex', justifyContent: 'space-between', gap: 8
                }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {safeFileName(item)}
                  </span>
                  <span style={{ color: '#ff4d4f', flexShrink: 0, maxWidth: '45%', textAlign: 'right' }}>
                    {safeReason(item)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // 默认 JSON 展示
  const serializeValue = (val: unknown): unknown => {
    if (val === null) return null
    if (typeof val === 'bigint') return String(val)
    if (typeof val === 'function') return '[Function]'
    if (typeof val === 'symbol') return String(val)
    return val
  }
  return (
    <pre style={{ margin: 0, fontSize: '11px', color: '#94a3b8', background: '#0f172a', padding: '8px', borderRadius: '6px', overflow: 'auto', maxHeight: '200px' }}>
      {JSON.stringify(data, serializeValue, 2)}
    </pre>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: '#0f172a', padding: '8px', borderRadius: '6px' }}>
      <div style={{ color: '#64748b', fontSize: '11px' }}>{label}</div>
      <div style={{ color: '#f8fafc', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '50px 20px', color: '#64748b' }}>
      <div style={{ fontSize: '40px', marginBottom: '12px' }}>{icon}</div>
      <p style={{ margin: '0 0 8px 0', color: '#94a3b8', fontSize: '16px', fontWeight: 600 }}>{title}</p>
      <p style={{ margin: 0, fontSize: '13px' }}>{desc}</p>
    </div>
  )
}