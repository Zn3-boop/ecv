// App 共享状态 Context Hook
import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import type {
  DesktopAPI,
  ActionCommand,
  ActionExecutionResult,
  PendingActionCommand,
  SystemMetrics,
  VoiceCommandResponse,
  AgentAnalysis,
} from '../types'
import { useSystemMetrics } from './useSystemMetrics'
import { useVoiceAgent } from './useVoiceAgent'
import {
  createCommandSignature,
  generateAdviceFromResults,
  generateDefaultCommands,
} from '../utils/command-utils'
import type { AppView } from '../types'

// 获取 API Base URL
const getApiBase = () => {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('api_base') || import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
  }
  return 'http://127.0.0.1:8000'
}

interface AppContextValue {
  // 状态
  apiBase: string
  setApiBase: (base: string) => void
  desktopAPI: DesktopAPI | undefined
  preloadStatus: string
  activeView: AppView
  setActiveView: (view: AppView) => void
  showConfig: boolean
  setShowConfig: (show: boolean) => void
  suggestedCommands: ActionCommand[]
  setSuggestedCommands: React.Dispatch<React.SetStateAction<ActionCommand[]>>
  executionResults: ActionExecutionResult[]
  executionLogs: { batchId: string; timestamp: string; commands: ActionCommand[]; results: ActionExecutionResult[] }[]
  pendingActions: PendingActionCommand[]
  isExecuting: boolean
  isPaused: boolean
  error: string
  agentAnalysis: AgentAnalysis | null
  metrics: SystemMetrics | null
  cloudAudioStatus: string
  
  // 方法
  handleAnalyzeProblem: (text: string) => Promise<void>
  handleExecuteSelected: (commands: ActionCommand[]) => Promise<void>
  handleConfirmPending: (ids: string[]) => Promise<void>
  handleRejectPending: (ids: string[]) => void
  handlePause: () => Promise<void>
  handleResume: () => Promise<void>
  speakText: (text: string, label?: string, audioBase64?: string, mimeType?: string) => void
}

const AppContext = createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [apiBase, setApiBase] = useState(getApiBase())
  const [desktopAPI, setDesktopAPI] = useState<DesktopAPI | undefined>()
  const [preloadStatus, setPreloadStatus] = useState('checking...')
  const [activeView, setActiveView] = useState<AppView>('tasks')
  const [showConfig, setShowConfig] = useState(false)
  const [suggestedCommands, setSuggestedCommands] = useState<ActionCommand[]>([])
  const [executionResults, setExecutionResults] = useState<ActionExecutionResult[]>([])
  const [executionLogs, setExecutionLogs] = useState<{ batchId: string; timestamp: string; commands: ActionCommand[]; results: ActionExecutionResult[] }[]>([])
  const [pendingActions, setPendingActions] = useState<PendingActionCommand[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [error, setError] = useState('')
  const [agentAnalysis, setAgentAnalysis] = useState<AgentAnalysis | null>(null)
  const [analyzedTools, setAnalyzedTools] = useState<Set<string>>(new Set())

  // 初始化 desktopAPI
  useEffect(() => {
    queueMicrotask(() => {
      const api = (window as Window & { desktopAPI?: DesktopAPI }).desktopAPI
      if (api) {
        setDesktopAPI(api)
        if (api.ping) setPreloadStatus(api.ping())
      }
    })
  }, [])

  const { metrics } = useSystemMetrics(desktopAPI)
  const { speakText, cloudAudioStatus } = useVoiceAgent(desktopAPI)

  // 监听待确认操作
  useEffect(() => {
    if (!desktopAPI?.onPendingActions) return
    const unsub = desktopAPI.onPendingActions((cmds) => {
      setPendingActions(cmds || [])
    })
    return unsub
  }, [desktopAPI])

  // 监听执行日志更新
  useEffect(() => {
    if (!desktopAPI?.onActionLogUpdated) return
    const unsub = desktopAPI.onActionLogUpdated(() => {
      desktopAPI.getActionLog?.(50).then(logs => {
        if (logs) setExecutionLogs(logs)
      }).catch(() => {})
    })
    return unsub
  }, [desktopAPI])

  // 分析问题
  const handleAnalyzeProblem = useCallback(async (text: string) => {
    setIsExecuting(true)
    setError('')
    setExecutionResults([])

    try {
      const latestMetrics = await desktopAPI?.getSystemMetrics?.() ?? null

      const response = await fetch(`${apiBase}/voice/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript: text,
          mode: 'default',
          system_context: latestMetrics,
          conversation_id: null,
        }),
      })

      if (!response.ok) throw new Error(`后端返回错误: ${response.status}`)

      const data = await response.json() as VoiceCommandResponse

      if (data.analysis || data.thinking || data.advice) {
        setAgentAnalysis({
          analysis: data.analysis || '',
          thinking: data.thinking || '',
          advice: data.advice || '',
          riskWarning: data.risk_warning || '',
        })
      } else {
        setAgentAnalysis(null)
      }

      if (data.commands && data.commands.length > 0) {
        const seen = new Set<string>()
        const uniqueCommands: ActionCommand[] = []
        
        data.commands.forEach((cmd) => {
          const sig = createCommandSignature(cmd.tool, cmd.params)
          if (!seen.has(sig)) {
            seen.add(sig)
            uniqueCommands.push({
              id: `task-${Date.now()}-${uniqueCommands.length}`,
              tool: cmd.tool,
              type: (cmd.type || 'read') as ActionCommand['type'],
              params: cmd.params || {},
              reason: cmd.reason || '未说明原因',
              confidence: cmd.confidence || 0.5,
              risk: (cmd.risk || 'low') as ActionCommand['risk'],
              require_confirmation: cmd.require_confirmation || cmd.type === 'destructive',
              recommended: cmd.recommended || false,
            })
          }
        })
        
        setSuggestedCommands(uniqueCommands)
      } else {
        setSuggestedCommands(generateDefaultCommands(text))
      }

      if (data.speech_text) {
        speakText(data.speech_text, '分析完成', data.tts_audio_base64, data.tts_mime_type)
      }
    } catch (e) {
      setError(String(e))
      setSuggestedCommands(generateDefaultCommands(text))
    } finally {
      setIsExecuting(false)
    }
  }, [desktopAPI, speakText, apiBase])

  // 执行选中命令
  const handleExecuteSelected = useCallback(async (commands: ActionCommand[]) => {
    if (!desktopAPI?.executeActions) {
      setError('执行 API 不可用')
      return
    }
    setIsExecuting(true)
    setError('')
    try {
      const results = await desktopAPI.executeActions(commands)
      setExecutionResults(results)

      const logs = await desktopAPI.getActionLog?.(50)
      if (logs) setExecutionLogs(logs)

      const newlyAnalyzed = new Set(analyzedTools)
      commands.forEach(c => newlyAnalyzed.add(c.tool))
      setAnalyzedTools(newlyAnalyzed)

      const readResults = results.filter(r => r.success && r.data && !analyzedTools.has(r.tool))
      if (readResults.length > 0) {
        const resultSummary = readResults.map(r => {
          const data = r.data as Record<string, unknown>
          if (r.tool === 'process:top' && data?.processes) {
            const procs = (data.processes as { name: string; pid: number; mem: number }[]).slice(0, 5).map(p => 
              `${p.name}(PID:${p.pid}, MEM:${p.mem}K)`
            ).join('; ')
            return `高占用进程: ${procs}`
          }
          if (r.tool === 'disk:list' && data?.drives) {
            const drives = (data.drives as { name: string; usePercent: number; free: number }[]).map(d => 
              `${d.name}: ${d.usePercent}% 已用, ${(d.free / 1024 / 1024 / 1024).toFixed(1)}GB 剩余`
            ).join('; ')
            return `磁盘状态: ${drives}`
          }
          return `${r.tool}: 执行完成`
        }).join('\n')

        try {
          const analysisResponse = await fetch(`${apiBase}/voice/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              transcript: `基于以下监控数据给出处置建议:\n${resultSummary}`,
              mode: 'automation',
              system_context: metrics,
            }),
          })
          const analysisData = await analysisResponse.json() as VoiceCommandResponse
          
          if (analysisData.commands && analysisData.commands.length > 0) {
            const existingSigs = new Set(suggestedCommands.map(c => createCommandSignature(c.tool, c.params)))
            const newCommands: ActionCommand[] = []
            analysisData.commands.forEach((cmd, idx) => {
              const sig = createCommandSignature(cmd.tool, cmd.params)
              if (existingSigs.has(sig)) return
              if (analyzedTools.has(cmd.tool)) return
              
              existingSigs.add(sig)
              newCommands.push({
                id: `suggested-${Date.now()}-${idx}`,
                tool: cmd.tool,
                type: (cmd.type || 'read') as ActionCommand['type'],
                params: cmd.params || {},
                reason: `🤖 AI 建议: ${cmd.reason || '基于分析结果推荐'}`,
                confidence: cmd.confidence || 0.8,
                risk: (cmd.risk || 'low') as ActionCommand['risk'],
                require_confirmation: cmd.require_confirmation || cmd.type === 'destructive',
                recommended: true,
              })
            })
            
            if (newCommands.length > 0) {
              setSuggestedCommands(prev => [...prev, ...newCommands])
            }
          }

          if (analysisData.speech_text) {
            speakText(analysisData.speech_text, '分析完成', analysisData.tts_audio_base64, analysisData.tts_mime_type)
          }
        } catch {
          const localAdvice = generateAdviceFromResults(readResults, suggestedCommands, analyzedTools)
          if (localAdvice.length > 0) {
            setSuggestedCommands(prev => [...prev, ...localAdvice])
          }
        }
      }

      const successCount = results.filter(r => r.success).length
      const failCount = results.length - successCount
      const skippedCount = results.filter(r => r.skipped).length
      const summary = `执行完成，${successCount}个成功${failCount > 0 ? `，${failCount}个失败` : ''}${skippedCount > 0 ? `，${skippedCount}个跳过` : ''}`
      speakText(summary, '执行完成')
    } catch (e) {
      setError(String(e))
    } finally {
      setIsExecuting(false)
    }
  }, [desktopAPI, speakText, apiBase, metrics, analyzedTools, suggestedCommands])

  const handleConfirmPending = useCallback(async (ids: string[]) => {
    const cmds = pendingActions.filter(a => ids.includes(a.id))
    setPendingActions(prev => prev.filter(a => !ids.includes(a.id)))
    if (cmds.length > 0) {
      await handleExecuteSelected(cmds)
    }
  }, [pendingActions, handleExecuteSelected])

  const handleRejectPending = useCallback((ids: string[]) => {
    setPendingActions(prev => prev.filter(a => !ids.includes(a.id)))
    if (desktopAPI?.clearPendingActions) {
      desktopAPI.clearPendingActions(ids).catch(() => {})
    }
  }, [desktopAPI])

  const handlePause = useCallback(async () => {
    await desktopAPI?.pauseActions?.()
    setIsPaused(true)
  }, [desktopAPI])

  const handleResume = useCallback(async () => {
    await desktopAPI?.resumeActions?.()
    setIsPaused(false)
  }, [desktopAPI])

  const value: AppContextValue = {
    apiBase,
    setApiBase,
    desktopAPI,
    preloadStatus,
    activeView,
    setActiveView,
    showConfig,
    setShowConfig,
    suggestedCommands,
    setSuggestedCommands,
    executionResults,
    executionLogs,
    pendingActions,
    isExecuting,
    isPaused,
    error,
    agentAnalysis,
    metrics,
    cloudAudioStatus,
    handleAnalyzeProblem,
    handleExecuteSelected,
    handleConfirmPending,
    handleRejectPending,
    handlePause,
    handleResume,
    speakText,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error('useApp must be used within AppProvider')
  }
  return context
}
