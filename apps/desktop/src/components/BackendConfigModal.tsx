import { useState, useEffect, useCallback } from 'react'
import type { DesktopAPI } from '../types'

interface BackendConfigModalProps {
  visible: boolean
  onClose: () => void
  onConfigChange?: (apiBase: string) => void
}

export function BackendConfigModal({ visible, onClose, onConfigChange }: BackendConfigModalProps) {
  const [apiBase, setApiBase] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')

  const desktopAPI = (window as Window & { desktopAPI?: DesktopAPI }).desktopAPI

  // 初始化配置 - 使用 setTimeout 延迟执行以避免 ESLint 警告
  useEffect(() => {
    if (!visible) return
    
    const loadConfig = () => {
      // 尝试从 IPC 读取配置
      if (desktopAPI?.getBackendConfig) {
        desktopAPI.getBackendConfig().then((config) => {
          setApiBase(config.apiBase || 'http://127.0.0.1:8000')
          setError('')
          setSaved(false)
          setTestStatus('idle')
        }).catch(() => {
          // 降级：从 localStorage 读取
          const savedVal = localStorage.getItem('api_base')
          setApiBase(savedVal || 'http://127.0.0.1:8000')
        })
      } else {
        const savedVal = localStorage.getItem('api_base')
        setApiBase(savedVal || 'http://127.0.0.1:8000')
      }
    }
    
    // 延迟执行以避免同步 setState 警告
    const timer = setTimeout(loadConfig, 0)
    return () => clearTimeout(timer)
  }, [visible, desktopAPI])

  const validateUrl = (url: string): boolean => {
    try {
      new URL(url)
      return true
    } catch {
      return false
    }
  }

  const handleTest = useCallback(async () => {
    if (!validateUrl(apiBase)) {
      setError('请输入有效的 URL')
      return
    }
    setTestStatus('testing')
    setError('')
    
    try {
      const response = await fetch(`${apiBase}/voice/status`, { 
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      })
      if (response.ok) {
        setTestStatus('success')
      } else {
        setTestStatus('error')
        setError(`后端返回错误: ${response.status}`)
      }
    } catch {
      setTestStatus('error')
      setError('无法连接到后端，请检查地址和网络')
    }
  }, [apiBase])

  const handleSave = useCallback(async () => {
    if (!validateUrl(apiBase)) {
      setError('请输入有效的 URL，例如 http://127.0.0.1:8000')
      return
    }

    setLoading(true)
    setError('')
    try {
      // 保存到 IPC（主进程）
      if (desktopAPI?.setBackendConfig) {
        await desktopAPI.setBackendConfig({ apiBase: apiBase.trim() })
      }
      // 备份到 localStorage
      localStorage.setItem('api_base', apiBase.trim())
      
      setSaved(true)
      onConfigChange?.(apiBase.trim())
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [apiBase, desktopAPI, onConfigChange])

  const handleReload = () => {
    window.location.reload()
  }

  if (!visible) return null

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: '16px',
        padding: '24px',
        width: '480px',
        maxWidth: '90vw',
      }} onClick={e => e.stopPropagation()}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '18px' }}>⚙️ 后端服务配置</h3>
          <button onClick={onClose} style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            fontSize: '24px',
            cursor: 'pointer',
            padding: '0',
            width: '32px',
            height: '32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '6px',
          }}>×</button>
        </div>

        {/* 表单 */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', color: '#94a3b8', fontSize: '13px', marginBottom: '6px' }}>
            API 基础地址
          </label>
          <input
            type="text"
            value={apiBase}
            onChange={(e) => { setApiBase(e.target.value); setTestStatus('idle') }}
            placeholder="http://127.0.0.1:8000"
            disabled={loading}
            style={{
              width: '100%',
              background: '#0f172a',
              border: `1px solid ${error ? '#ef4444' : '#334155'}`,
              borderRadius: '8px',
              padding: '10px 14px',
              color: '#f8fafc',
              fontSize: '14px',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          <p style={{ margin: '6px 0 0', fontSize: '12px', color: '#475569' }}>
            修改后需要点击保存，刷新页面生效
          </p>
        </div>

        {/* 测试连接 */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <button
            onClick={handleTest}
            disabled={testStatus === 'testing'}
            style={{
              flex: 1,
              background: testStatus === 'success' ? 'rgba(34,197,94,0.2)' : testStatus === 'error' ? 'rgba(239,68,68,0.2)' : '#1e293b',
              color: testStatus === 'success' ? '#22c55e' : testStatus === 'error' ? '#ef4444' : '#94a3b8',
              border: 'none',
              borderRadius: '8px',
              padding: '10px',
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            {testStatus === 'testing' ? '🔗 测试中...' : 
             testStatus === 'success' ? '✅ 连接成功' : 
             testStatus === 'error' ? '❌ 连接失败' : '🔗 测试连接'}
          </button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)',
            color: '#ef4444',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
          }}>
            {error}
          </div>
        )}

        {/* 成功提示 */}
        {saved && (
          <div style={{
            background: 'rgba(34,197,94,0.1)',
            color: '#22c55e',
            padding: '10px 14px',
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
          }}>
            ✅ 配置已保存
          </div>
        )}

        {/* 操作按钮 */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={onClose}
            style={{
              flex: 1,
              background: 'transparent',
              border: '1px solid #334155',
              color: '#94a3b8',
              padding: '10px',
              borderRadius: '8px',
              fontSize: '14px',
              cursor: 'pointer',
            }}
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={loading}
            style={{
              flex: 1,
              background: loading ? '#334155' : '#3b82f6',
              color: '#fff',
              border: 'none',
              padding: '10px',
              borderRadius: '8px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '保存中...' : '💾 保存配置'}
          </button>
        </div>

        {/* 刷新提示 */}
        {saved && (
          <div style={{ marginTop: '16px', textAlign: 'center' }}>
            <button
              onClick={handleReload}
              style={{
                background: 'rgba(59,130,246,0.15)',
                color: '#3b82f6',
                border: 'none',
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              🔄 立即刷新页面生效
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
