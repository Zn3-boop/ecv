// App.tsx 相关类型定义

// 视图类型
export type AppView = 'tasks' | 'conversation' | 'execution' | 'files' | 'providers'

// 后端命令响应类型（用于解析 commands 数组）
export interface BackendCommand {
  tool: string
  type?: string
  params?: Record<string, unknown>
  reason?: string
  confidence?: number
  risk?: string
  require_confirmation?: boolean
  recommended?: boolean
}

// 执行结果数据类型
export interface ProcessTopData {
  processes: { name: string; pid: number; mem: number }[]
}

export interface DiskListData {
  drives: { name: string; usePercent: number; free: number }[]
}

export interface TempScanData {
  entries: { isTempLike: boolean }[]
  total: number
}

export interface SystemInfoData {
  platform?: string
  cpus?: number
  totalMem?: number
}

// Agent 分析结果类型
export interface AgentAnalysis {
  analysis: string
  thinking: string
  advice: string
  riskWarning: string
}

// Badge 计数类型
export interface BadgeCounts {
  tasks: number
  conversation: number
  execution: number
  files: number
}

// App Context 类型
export interface AppContextState {
  apiBase: string
  setApiBase: (base: string) => void
  desktopAPI: unknown
  preloadStatus: string
  activeView: AppView
  setActiveView: (view: AppView) => void
  showConfig: boolean
  setShowConfig: (show: boolean) => void
  suggestedCommands: unknown[]
  setSuggestedCommands: unknown
  executionResults: unknown[]
  executionLogs: unknown[]
  pendingActions: unknown[]
  isExecuting: boolean
  isPaused: boolean
  error: string
  agentAnalysis: AgentAnalysis | null
  metrics: unknown
  cloudAudioStatus: string
  handleAnalyzeProblem: unknown
  handleExecuteSelected: unknown
  handleConfirmPending: unknown
  handleRejectPending: unknown
  handlePause: unknown
  handleResume: unknown
  speakText: unknown
}
