// 文件管理面板组件 - 现代化样式

import { useState, useEffect, useCallback } from 'react'
import type { DirectoryListing, FileEntry } from '../types'
import { formatFileSize } from '../utils/formatters'

interface FilesPanelProps {
  getDesktopAPI: () => import('../types').DesktopAPI | undefined
}

export function FilesPanel({ getDesktopAPI }: FilesPanelProps) {
  const [roots, setRoots] = useState<string[]>([])
  const [currentPath, setCurrentPath] = useState('')
  const [listing, setListing] = useState<DirectoryListing | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 加载根目录
  useEffect(() => {
    const api = getDesktopAPI()
    if (api?.listFileRoots) {
      api.listFileRoots().then(setRoots).catch(() => setRoots([]))
    }
  }, [getDesktopAPI])

  // 加载目录内容
  const loadDirectory = useCallback(async (path: string) => {
    const api = getDesktopAPI()
    if (!api?.listDirectory) return
    setLoading(true)
    setError('')
    try {
      const result = await api.listDirectory(path)
      if (result.entries) {
        result.entries = result.entries.filter((entry: FileEntry) => entry.exists !== false)
      }
      setListing(result)
      setCurrentPath(path)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [getDesktopAPI])

  // 删除文件
  const handleDelete = async (entry: FileEntry) => {
    if (!window.confirm(`确定删除 ${entry.name}？`)) return
    const api = getDesktopAPI()
    if (api?.deletePath) {
      try {
        await api.deletePath(entry.path)
        setError('')
        if (currentPath) loadDirectory(currentPath)
      } catch (e) {
        setError(`删除失败: ${e instanceof Error ? e.message : String(e)}`)
      }
    }
  }

  // 打开文件
  const handleOpen = async (entry: FileEntry) => {
    const api = getDesktopAPI()
    if (api?.openPath) {
      try {
        const result = await api.openPath(entry.path)
        if (!result?.opened) {
          setError(`文件不存在: ${entry.name}`)
          if (currentPath) loadDirectory(currentPath)
        }
      } catch {
        setError(`无法打开: ${entry.name}`)
      }
    }
  }

  // 格式化时间
  const formatDate = (date?: string | null) => {
    if (!date) return '-'
    return new Date(date).toLocaleString('zh-CN', { 
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' 
    })
  }

  // 获取文件图标
  const getFileIcon = (name: string): string => {
    const ext = name.split('.').pop()?.toLowerCase() || ''
    const iconMap: Record<string, string> = {
      pdf: '📕', doc: '📘', docx: '📘', xls: '📗', xlsx: '📗', ppt: '📙', pptx: '📙',
      txt: '📄', md: '📝', json: '📋', js: '⚡', ts: '🔷', py: '🐍', html: '🌐', css: '🎨',
      jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', webp: '🖼️', svg: '🎨',
      mp3: '🎵', mp4: '🎬', wav: '🎵', webm: '🎬',
      zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
      exe: '⚙️', msi: '⚙️', dmg: '💿',
    }
    return iconMap[ext] || '📄'
  }

  return (
    <section style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      {/* 标题区 */}
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc', margin: '0 0 8px 0' }}>
          📁 文件管理
        </h2>
        <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0 }}>
          浏览白名单目录中的文件，支持打开和删除
        </p>
      </div>

      {/* 面包屑导航 */}
      <div style={{
        background: '#111827',
        border: '1px solid #1e293b',
        borderRadius: '10px',
        padding: '12px 16px',
        marginBottom: '16px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap',
      }}>
        {currentPath ? (
          <>
            <button 
              onClick={() => { setListing(null); setCurrentPath('') }}
              style={{ background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer', fontSize: '14px' }}
            >
              📁 根目录
            </button>
            <span style={{ color: '#475569' }}>/</span>
            <span style={{ color: '#94a3b8', fontSize: '14px' }}>{currentPath}</span>
          </>
        ) : (
          <span style={{ color: '#94a3b8', fontSize: '14px' }}>选择一个目录开始浏览</span>
        )}
      </div>

      {/* 根目录选择 */}
      {!currentPath && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px' }}>
          {roots.map((root) => (
            <button
              key={root}
              onClick={() => loadDirectory(root)}
              style={{
                background: '#111827',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '20px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '12px',
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = '#3b82f6'; (e.currentTarget as HTMLElement).style.background = '#1e293b' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = '#1e293b'; (e.currentTarget as HTMLElement).style.background = '#111827' }}
            >
              <span style={{ fontSize: '40px' }}>📂</span>
              <span style={{ color: '#f8fafc', fontSize: '14px', fontWeight: 600 }}>
                {root.split(/[\\/]/).pop() || root}
              </span>
              <span style={{ color: '#64748b', fontSize: '12px' }}>{root}</span>
            </button>
          ))}
        </div>
      )}

      {/* 文件列表 */}
      {currentPath && listing && (
        <div style={{
          background: '#111827',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          overflow: 'hidden',
        }}>
          {/* 表头 */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '40px 1fr 120px 150px 120px',
            gap: '12px',
            padding: '12px 16px',
            background: '#0f172a',
            borderBottom: '1px solid #1e293b',
            fontSize: '12px',
            fontWeight: 600,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}>
            <span></span>
            <span>名称</span>
            <span>大小</span>
            <span>修改时间</span>
            <span>操作</span>
          </div>

          {/* 返回上级 */}
          <div
            onClick={() => {
              const parent = currentPath.split(/[\\/]/).slice(0, -1).join('/')
              if (parent && roots.some(r => parent.startsWith(r))) {
                loadDirectory(parent)
              } else {
                setListing(null)
                setCurrentPath('')
              }
            }}
            style={{
              display: 'grid',
              gridTemplateColumns: '40px 1fr 120px 150px 120px',
              gap: '12px',
              padding: '12px 16px',
              borderBottom: '1px solid #1e293b',
              cursor: 'pointer',
              alignItems: 'center',
              color: '#94a3b8',
            }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = '#1e293b'}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
          >
            <span style={{ fontSize: '18px' }}>⬆️</span>
            <span style={{ fontSize: '14px' }}>..</span>
            <span></span><span></span><span></span>
          </div>

          {/* 文件条目 */}
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
              <div style={{ animation: 'pulse 1s infinite' }}>加载中...</div>
            </div>
          ) : listing.entries.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>空文件夹</div>
          ) : (
            listing.entries.map((entry, idx) => (
              <div
                key={idx}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 120px 150px 120px',
                  gap: '12px',
                  padding: '12px 16px',
                  borderBottom: '1px solid #1e293b',
                  alignItems: 'center',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = '#1e293b'}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
              >
                <span style={{ fontSize: '20px' }}>
                  {entry.type === 'directory' ? '📁' : getFileIcon(entry.name)}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    color: '#f8fafc',
                    fontSize: '14px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {entry.name}
                  </div>
                </div>
                <span style={{ color: '#94a3b8', fontSize: '13px' }}>
                  {entry.type === 'directory' ? '--' : formatFileSize(entry.size)}
                </span>
                <span style={{ color: '#64748b', fontSize: '12px' }}>
                  {formatDate(entry.modifiedAt)}
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  {entry.type === 'directory' && (
                    <button
                      onClick={() => loadDirectory(entry.path)}
                      style={{
                        background: 'rgba(59,130,246,0.15)',
                        color: '#3b82f6',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        fontSize: '12px',
                        cursor: 'pointer',
                      }}
                    >
                      进入
                    </button>
                  )}
                  <button
                    onClick={() => handleOpen(entry)}
                    style={{
                      background: 'rgba(34,197,94,0.15)',
                      color: '#22c55e',
                      border: 'none',
                      borderRadius: '6px',
                      padding: '4px 10px',
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    打开
                  </button>
                  <button
                    onClick={() => handleDelete(entry)}
                    style={{
                      background: 'rgba(239,68,68,0.15)',
                      color: '#ef4444',
                      border: 'none',
                      borderRadius: '6px',
                      padding: '4px 10px',
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    删除
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {error && (
        <div style={{
          marginTop: '16px',
          padding: '12px 16px',
          background: 'rgba(239,68,68,0.1)',
          color: '#ef4444',
          borderRadius: '8px',
          fontSize: '13px',
        }}>
          ⚠️ {error}
        </div>
      )}
    </section>
  )
}