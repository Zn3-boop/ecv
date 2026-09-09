import { useState, useEffect, useCallback } from 'react'
import type { DesktopAPI, WindowPreferences } from '../types'

interface WindowSettingsModalProps {
  visible: boolean
  onClose: () => void
}

export function WindowSettingsModal({ visible, onClose }: WindowSettingsModalProps) {
  const [prefs, setPrefs] = useState<WindowPreferences>({
    alwaysOnTop: false,
    miniMode: false,
    launchAtLogin: false,
    minimizeToTray: true,
    visible: true,
  })
  const [loading, setLoading] = useState(false)

  const desktopAPI = (window as Window & { desktopAPI?: DesktopAPI }).desktopAPI

  // 加载窗口偏好设置
  useEffect(() => {
    if (!visible) return
    
    const loadPrefs = async () => {
      if (desktopAPI?.getWindowPreferences) {
        try {
          const p = await desktopAPI.getWindowPreferences()
          setPrefs(p)
        } catch (e) {
          console.error('[WindowSettings] Failed to load preferences:', e)
        }
      }
    }
    
    const timer = setTimeout(loadPrefs, 0)
    return () => clearTimeout(timer)
  }, [visible, desktopAPI])

  // 切换窗口置顶
  const handleToggleAlwaysOnTop = useCallback(async () => {
    if (!desktopAPI?.toggleAlwaysOnTop) return
    setLoading(true)
    try {
      const newPrefs = await desktopAPI.toggleAlwaysOnTop()
      setPrefs(newPrefs)
    } catch (e) {
      console.error('[WindowSettings] toggleAlwaysOnTop failed:', e)
    } finally {
      setLoading(false)
    }
  }, [desktopAPI])

  // 切换迷你模式
  const handleToggleMiniMode = useCallback(async () => {
    if (!desktopAPI?.toggleMiniMode) return
    setLoading(true)
    try {
      const newPrefs = await desktopAPI.toggleMiniMode()
      setPrefs(newPrefs)
    } catch (e) {
      console.error('[WindowSettings] toggleMiniMode failed:', e)
    } finally {
      setLoading(false)
    }
  }, [desktopAPI])

  // 切换窗口可见性
  const handleToggleVisibility = useCallback(async () => {
    if (!desktopAPI?.toggleWindowVisibility) return
    setLoading(true)
    try {
      await desktopAPI.toggleWindowVisibility()
      // 重新加载偏好设置
      if (desktopAPI?.getWindowPreferences) {
        const p = await desktopAPI.getWindowPreferences()
        setPrefs(p)
      }
    } catch (e) {
      console.error('[WindowSettings] toggleVisibility failed:', e)
    } finally {
      setLoading(false)
    }
  }, [desktopAPI])

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
        width: '420px',
        maxWidth: '90vw',
      }} onClick={e => e.stopPropagation()}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '18px' }}>🪟 窗口管理</h3>
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

        {/* 窗口状态 */}
        <div style={{
          background: '#0f172a',
          borderRadius: '10px',
          padding: '14px 16px',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
        }}>
          <span style={{
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            background: prefs.visible ? '#22c55e' : '#64748b',
            boxShadow: prefs.visible ? '0 0 8px #22c55e' : 'none',
          }} />
          <span style={{ color: '#94a3b8', fontSize: '14px' }}>
            窗口状态: <span style={{ color: prefs.visible ? '#22c55e' : '#94a3b8' }}>
              {prefs.visible ? '可见' : '已隐藏'}
            </span>
          </span>
          <span style={{ color: '#64748b', fontSize: '12px', marginLeft: 'auto' }}>
            {prefs.miniMode ? '迷你模式' : '普通模式'}
          </span>
        </div>

        {/* 设置项列表 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* 窗口置顶 */}
          <button
            onClick={handleToggleAlwaysOnTop}
            disabled={loading}
            style={{
              background: prefs.alwaysOnTop ? 'rgba(59,130,246,0.15)' : '#0f172a',
              border: `1px solid ${prefs.alwaysOnTop ? '#3b82f6' : '#334155'}`,
              borderRadius: '10px',
              padding: '14px 16px',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              transition: 'all 0.2s',
            }}
          >
            <span style={{ fontSize: '20px' }}>📌</span>
            <div style={{ flex: 1, textAlign: 'left' }}>
              <div style={{ color: '#f8fafc', fontSize: '14px', fontWeight: 500 }}>窗口置顶</div>
              <div style={{ color: '#64748b', fontSize: '12px', marginTop: '2px' }}>始终显示在其它窗口之上</div>
            </div>
            <div style={{
              width: '44px',
              height: '24px',
              borderRadius: '12px',
              background: prefs.alwaysOnTop ? '#3b82f6' : '#334155',
              position: 'relative',
              transition: 'background 0.2s',
            }}>
              <div style={{
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                background: '#fff',
                position: 'absolute',
                top: '2px',
                left: prefs.alwaysOnTop ? '22px' : '2px',
                transition: 'left 0.2s',
              }} />
            </div>
          </button>

          {/* 迷你模式 */}
          <button
            onClick={handleToggleMiniMode}
            disabled={loading}
            style={{
              background: prefs.miniMode ? 'rgba(168,85,247,0.15)' : '#0f172a',
              border: `1px solid ${prefs.miniMode ? '#a855f7' : '#334155'}`,
              borderRadius: '10px',
              padding: '14px 16px',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              transition: 'all 0.2s',
            }}
          >
            <span style={{ fontSize: '20px' }}>📱</span>
            <div style={{ flex: 1, textAlign: 'left' }}>
              <div style={{ color: '#f8fafc', fontSize: '14px', fontWeight: 500 }}>迷你模式</div>
              <div style={{ color: '#64748b', fontSize: '12px', marginTop: '2px' }}>紧凑悬浮窗口，适合后台运行</div>
            </div>
            <div style={{
              width: '44px',
              height: '24px',
              borderRadius: '12px',
              background: prefs.miniMode ? '#a855f7' : '#334155',
              position: 'relative',
              transition: 'background 0.2s',
            }}>
              <div style={{
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                background: '#fff',
                position: 'absolute',
                top: '2px',
                left: prefs.miniMode ? '22px' : '2px',
                transition: 'left 0.2s',
              }} />
            </div>
          </button>

          {/* 隐藏/显示窗口 */}
          <button
            onClick={handleToggleVisibility}
            disabled={loading}
            style={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: '10px',
              padding: '14px 16px',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              transition: 'all 0.2s',
            }}
          >
            <span style={{ fontSize: '20px' }}>{prefs.visible ? '👁️' : '👁️‍🗨️'}</span>
            <div style={{ flex: 1, textAlign: 'left' }}>
              <div style={{ color: '#f8fafc', fontSize: '14px', fontWeight: 500 }}>{prefs.visible ? '隐藏窗口' : '显示窗口'}</div>
              <div style={{ color: '#64748b', fontSize: '12px', marginTop: '2px' }}>
                {prefs.visible ? '最小化到系统托盘' : '重新显示主窗口'}
              </div>
            </div>
            <span style={{ color: '#64748b', fontSize: '16px' }}>→</span>
          </button>

        </div>

        {/* 提示信息 */}
        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: 'rgba(59,130,246,0.1)',
          borderRadius: '8px',
          fontSize: '12px',
          color: '#64748b',
        }}>
          💡 提示：关闭窗口时会自动最小化到系统托盘，点击托盘图标可重新显示
        </div>
      </div>
    </div>
  )
}
