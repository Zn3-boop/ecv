import { useState } from 'react'
import { useApp } from './hooks'
import {
  TopBar, Sidebar, TasksPanel, ExecutionPanel, FilesPanel, BackendConfigModal, ConversationPanel, ProviderManager,
  WindowSettingsModal,
} from './components'
import type { BadgeCounts } from './types'
import type { ToastItem } from './hooks/useAppContext'

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
    isMuted,
    setIsMuted,
    toasts,
    removeToast,
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
        isMuted={isMuted}
        onToggleMute={() => setIsMuted(!isMuted)}
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
              addToast={addToast}
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

      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </div>
  )
}

function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null
  const colorMap = { success: '#22c55e', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' }
  const iconMap = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' }
  return (
    <div style={{
      position: 'fixed', bottom: '20px', right: '20px', zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '400px',
    }}>
      {toasts.map(t => (
        <div key={t.id} onClick={() => onDismiss(t.id)} style={{
          background: '#1e293b', border: `1px solid ${colorMap[t.type]}55`,
          borderRadius: '10px', padding: '12px 16px', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: '10px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          animation: 'slideIn 0.2s ease-out',
        }}>
          <span style={{ fontSize: '16px' }}>{iconMap[t.type]}</span>
          <span style={{ color: '#f8fafc', fontSize: '13px', flex: 1 }}>{t.message}</span>
          <span style={{ color: '#64748b', fontSize: '11px', cursor: 'pointer' }}>✕</span>
        </div>
      ))}
    </div>
  )
}