import { useState } from 'react'
import { useApp } from './hooks'
import {
  TopBar, Sidebar, TasksPanel, ExecutionPanel, FilesPanel, BackendConfigModal, ConversationPanel, ProviderManager,
  WindowSettingsModal,
} from './components'
import type { BadgeCounts } from './types'

export default function App() {
  const {
    desktopAPI,
    preloadStatus,
    activeView,
    setActiveView,
    showConfig,
    setShowConfig,
    error,
    agentAnalysis,
    metrics,
    cloudAudioStatus,
    suggestedCommands,
    setSuggestedCommands,
    isExecuting,
    handleAnalyzeProblem,
    handleExecuteSelected,
    executionResults,
    executionLogs,
    pendingActions,
    isPaused,
    handleConfirmPending,
    handleRejectPending,
    handlePause,
    handleResume,
    setApiBase,
  } = useApp()
  
  const [showWindowSettings, setShowWindowSettings] = useState(false)

  const agentStatus = metrics ? `在线 (${metrics.hostname})` : '离线'
  
  const badgeCounts: BadgeCounts = {
    tasks: suggestedCommands.filter(c => c.type === 'destructive').length,
    conversation: 0,
    execution: executionResults.length,
    files: 0,
  }

  const handleInternalConfigChange = (newApiBase: string) => {
    setApiBase(newApiBase)
  }

  return (
    <div className="app" style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0b1020' }}>
      <TopBar
        agentStatus={agentStatus}
        preloadStatus={preloadStatus}
        voiceStatusText={cloudAudioStatus}
        metrics={metrics}
        error={error}
        onOpenConfig={() => setShowConfig(true)}
        onOpenWindowSettings={() => setShowWindowSettings(true)}
      />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar
          activeView={activeView}
          onChange={setActiveView}
          badgeCounts={badgeCounts}
        />

        <main style={{ flex: 1, overflow: 'auto', padding: '0' }}>
          {activeView === 'tasks' && (
            <TasksPanel
              metrics={metrics}
              suggestedCommands={suggestedCommands}
              setSuggestedCommands={setSuggestedCommands}
              isExecuting={isExecuting}
              onExecuteSelected={handleExecuteSelected}
              executionResults={executionResults}
              onAnalyzeProblem={handleAnalyzeProblem}
              agentAnalysis={agentAnalysis}
            />
          )}
          {activeView === 'conversation' && (
            <ConversationPanel
              onAnalyzeProblem={handleAnalyzeProblem}
              _analyzeLoading={isExecuting}
            />
          )}
          {activeView === 'execution' && (
            <ExecutionPanel
              executionLogs={executionLogs}
              pendingActions={pendingActions}
              isExecuting={isExecuting}
              isPaused={isPaused}
              executionResults={executionResults}
              onConfirmPending={handleConfirmPending}
              onRejectPending={handleRejectPending}
              onPause={handlePause}
              onResume={handleResume}
              onClearLog={() => {}}
            />
          )}
          {activeView === 'files' && (
            <FilesPanel getDesktopAPI={() => desktopAPI} />
          )}
          {activeView === 'providers' && (
            <ProviderManager />
          )}
        </main>
      </div>

      <BackendConfigModal
        visible={showConfig}
        onClose={() => setShowConfig(false)}
        onConfigChange={handleInternalConfigChange}
      />
      
      <WindowSettingsModal
        visible={showWindowSettings}
        onClose={() => setShowWindowSettings(false)}
      />
    </div>
  )
}
