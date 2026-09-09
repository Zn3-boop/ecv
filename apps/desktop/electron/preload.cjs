const { contextBridge, ipcRenderer } = require('electron')

// 安全 IPC 调用包装器
function safeInvoke(channel, ...args) {
  try {
    return ipcRenderer.invoke(channel, ...args)
  } catch (err) {
    console.error(`[preload] IPC error (${channel}):`, err)
    return Promise.reject(err)
  }
}

// ==================== 安全白名单配置 ====================

// 允许的工具列表（完整版）
const ALLOWED_TOOLS = new Set([
  'file:list', 'file:read', 'file:write', 'file:delete', 'file:search',
  'system:info', 'system:command', 'app:launch', 'clipboard:write',
  'notify', 'disk:list', 'temp:scan', 'temp:cleanup', 'disk:cleanup',
  'process:list', 'process:top', 'process:kill', 'network:request', 'system:env',
  'system:hibernate', 'system:recycle', 'system:cleanmgr',
  'system:browser-cache', 'system:wechat-cache', 'disk:cleanup_advanced',
  'content:generate', 'ide:launch', 'browser:search', 'keyboard:type',
  'store:search', 'store:install', 'store:uninstall', 'store:list'
])

// 高危工具：参数需要额外审查
const DANGEROUS_TOOLS = new Set([
  'file:delete', 'file:write', 'process:kill', 'system:command',
  'system:hibernate', 'system:recycle', 'system:cleanmgr',
  'system:browser-cache', 'system:wechat-cache', 'disk:cleanup', 'disk:cleanup_advanced', 'temp:cleanup',
  'store:uninstall', 'store:install'
])

// 需要路径校验的工具（所有涉及 path 参数的工具）
const PATH_VALIDATED_TOOLS = new Set([
  'file:read', 'file:write', 'file:delete', 'file:list', 'file:search',
  'temp:scan', 'temp:cleanup', 'disk:cleanup', 'disk:cleanup_advanced',
  'app:launch',
])

// 允许执行的系统命令白名单
const ALLOWED_SYSTEM_CMDS = new Set(['echo', 'whoami', 'date', 'uptime', 'uname', 'pwd', 'ls', 'df', 'ps'])

// 缓存文件白名单根目录
let cachedFileRoots = []
let rootsReady = false

async function initFileRoots() {
  try {
    cachedFileRoots = await ipcRenderer.invoke('system:file-roots:list') || []
    rootsReady = true
    console.log('[preload] file roots loaded:', cachedFileRoots)
  } catch (e) {
    console.error('[preload] failed to load file roots:', e)
    // 如果获取失败，使用默认白名单
    const home = process.env.USERPROFILE || process.env.HOME || 'C:/Users/' + (process.env.USERNAME || '')
    cachedFileRoots = [
      home,
      home + '/Desktop',
      home + '/Downloads',
      home + '/Documents',
      home + '/AppData/Local/Temp',
      home + '/AppData/Roaming/Microsoft/Windows/Start Menu/Programs',
      home + '/AppData/Local',
      home + '/AppData/Roaming',
      'C:/Program Files',
      'C:/Program Files (x86)',
      'D:/',
      'E:/',
      'F:/',
    ]
    rootsReady = true
    console.log('[preload] using default file roots:', cachedFileRoots)
  }
}
initFileRoots()

function normalizePath(targetPath) {
  return targetPath.replace(/\\/g, '/').replace(/\/+/g, '/')
}

function validatePath(targetPath) {
  if (!targetPath || typeof targetPath !== 'string') {
    return { valid: false, reason: 'path must be non-empty string' }
  }
  const normalized = normalizePath(targetPath).toLowerCase()
  if (normalized.includes('..')) {
    return { valid: false, reason: 'path traversal detected' }
  }
  // 如果白名单未加载，允许所有路径（由主进程进一步验证）
  if (cachedFileRoots.length === 0) {
    console.warn('[preload] file roots not loaded yet, allowing path for testing')
    return { valid: true, normalized }
  }
  const isAllowed = cachedFileRoots.some(root => {
    let normalizedRoot = normalizePath(root).toLowerCase()
    normalizedRoot = normalizedRoot.replace(/\/+$/, '')
    return normalized === normalizedRoot || normalized.startsWith(normalizedRoot + '/')
  })
  if (!isAllowed) {
    return { valid: false, reason: `path not in whitelist roots: ${normalized}` }
  }
  return { valid: true, normalized }
}

function validateCommands(commands) {
  if (!Array.isArray(commands)) {
    return { valid: false, reason: 'commands must be an array' }
  }

  for (const cmd of commands) {
    if (!cmd || typeof cmd !== 'object') {
      return { valid: false, reason: 'each command must be an object' }
    }
    if (!cmd.tool || typeof cmd.tool !== 'string') {
      return { valid: false, reason: 'command.tool is required and must be string' }
    }
    if (!ALLOWED_TOOLS.has(cmd.tool)) {
      return { valid: false, reason: `tool "${cmd.tool}" is not in whitelist` }
    }

    // 路径校验：所有涉及 path 参数的工具都必须通过白名单校验
    if (PATH_VALIDATED_TOOLS.has(cmd.tool) && cmd.params?.path) {
      // app:launch 的 path 可能是纯程序名（如 WeChat.exe），跳过路径校验
      const isPlainName = cmd.tool === 'app:launch'
        && !cmd.params.path.includes('\\')
        && !cmd.params.path.includes('/')
        && !cmd.params.path.includes('..')
      if (!isPlainName) {
        const pathCheck = validatePath(cmd.params.path)
        if (!pathCheck.valid) return pathCheck
      }
    }

    // 高危命令参数深度校验
    if (DANGEROUS_TOOLS.has(cmd.tool)) {
      if (cmd.tool === 'system:command' && cmd.params?.command) {
        const cmdName = cmd.params.command.split(/\s+/)[0]
        if (!ALLOWED_SYSTEM_CMDS.has(cmdName)) {
          return { valid: false, reason: `system command "${cmdName}" is not in allowed list` }
        }
      }

      // process:kill 必须带 pid（数字>0）或 name（非空字符串）
      if (cmd.tool === 'process:kill') {
        const hasPid = typeof cmd.params?.pid === 'number' && cmd.params.pid > 0
        const hasName = typeof cmd.params?.name === 'string' && cmd.params.name.length > 0
        if (!hasPid && !hasName) {
          return { valid: false, reason: 'process:kill requires pid (number>0) or name (non-empty string)' }
        }
      }
    }
  }

  return { valid: true }
}

// ==================== VAD (Voice Activity Detection) API ====================
contextBridge.exposeInMainWorld('electron', {
  // VAD 生命周期
  startVAD: () => safeInvoke('vad:start'),
  stopVAD: () => safeInvoke('vad:stop'),
  
  // VAD 音频帧处理
  processVAD: (frameArray) => safeInvoke('vad:process', frameArray),
  
  // 重置 VAD 状态
  resetVAD: () => {
    ipcRenderer.send('vad:reset')
  },
  
  // 监听 VAD 事件
  onVADSpeechStart: (callback) => {
    const listener = () => callback()
    ipcRenderer.on('vad:speech-start', listener)
    return () => ipcRenderer.removeListener('vad:speech-start', listener)
  },
  onVADSpeechEnd: (callback) => {
    const listener = () => callback()
    ipcRenderer.on('vad:speech-end', listener)
    return () => ipcRenderer.removeListener('vad:speech-end', listener)
  },
  
  // 监听全局快捷键触发的语音切换
  onToggleListening: (callback) => {
    const listener = () => callback()
    ipcRenderer.on('voice:toggle-listening', listener)
    return () => ipcRenderer.removeListener('voice:toggle-listening', listener)
  },
})

contextBridge.exposeInMainWorld('desktopAPI', {
  ping: () => 'pong from electron preload',

  getSystemMetrics: () => safeInvoke('system:metrics:get'),
  getAutomationEvents: () => safeInvoke('automation:events:list'),

  listFileRoots: () => safeInvoke('system:file-roots:list'),
  refreshFileRoots: async () => {
    cachedFileRoots = await safeInvoke('system:file-roots:list') || []
    rootsReady = true
    return cachedFileRoots
  },

  listDirectory: (targetPath) => {
    const check = validatePath(targetPath)
    if (!check.valid) return Promise.reject(new Error(`[preload] listDirectory blocked: ${check.reason}`))
    return safeInvoke('system:file:list', targetPath)
  },

  deletePath: (targetPath) => {
    const check = validatePath(targetPath)
    if (!check.valid) return Promise.reject(new Error(`[preload] deletePath blocked: ${check.reason}`))
    return safeInvoke('system:file:delete', targetPath)
  },

  openPath: (targetPath) => {
    // 如果是纯程序名（如 WeChat.exe, calc.exe, notepad.exe），跳过路径校验
    if (targetPath && !targetPath.includes('\\') && !targetPath.includes('/') && !targetPath.includes('..') && !targetPath.startsWith('.') && /^[a-zA-Z0-9 _\-.]+$/.test(targetPath)) {
      return safeInvoke('system:file:open', targetPath)
    }
    // 如果是特殊URI（如 ms-settings:, ms-photos:），跳过路径校验
    if (targetPath && targetPath.includes(':') && /^[a-zA-Z-]+:.+$/.test(targetPath)) {
      return safeInvoke('system:file:open', targetPath)
    }
    const check = validatePath(targetPath)
    if (!check.valid) return Promise.reject(new Error(`[preload] openPath blocked: ${check.reason}`))
    return safeInvoke('system:file:open', targetPath)
  },

  getWindowPreferences: () => safeInvoke('window:preferences:get'),
  toggleWindowVisibility: () => safeInvoke('window:visibility:toggle'),
  toggleAlwaysOnTop: () => safeInvoke('window:always-on-top:toggle'),
  toggleMiniMode: () => safeInvoke('window:mini-mode:toggle'),
  setLaunchAtLogin: (enabled) => safeInvoke('window:launch-at-login:set', enabled),

  executeActions: (commands) => {
    const check = validateCommands(commands)
    if (!check.valid) return Promise.reject(new Error(`[preload] executeActions blocked: ${check.reason}`))
    return safeInvoke('action:execute', commands)
  },

  pauseActions: () => safeInvoke('action:pause'),
  resumeActions: () => safeInvoke('action:resume'),
  getActionLog: (limit) => safeInvoke('action:log', limit),
  getPendingActions: () => safeInvoke('action:pending:get'),
  clearPendingActions: (ids) => safeInvoke('action:pending:clear', ids),
  addPendingActions: (actions) => {
    const check = validateCommands(actions)
    if (!check.valid) return Promise.reject(new Error(`[preload] addPendingActions blocked: ${check.reason}`))
    return safeInvoke('action:pending:add', actions)
  },

  getBackendConfig: () => safeInvoke('config:backend:get'),
  setBackendConfig: (config) => safeInvoke('config:backend:set', config),

  onAutomationEvent: (callback) => {
    const listener = (_, payload) => callback(payload)
    ipcRenderer.on('automation:event', listener)
    return () => ipcRenderer.removeListener('automation:event', listener)
  },
  onPendingActions: (callback) => {
    const listener = (_, payload) => callback(payload)
    ipcRenderer.on('pending-actions', listener)
    return () => ipcRenderer.removeListener('pending-actions', listener)
  },
  onActionLogUpdated: (callback) => {
    const listener = (_, payload) => callback(payload)
    ipcRenderer.on('action:log-updated', listener)
    return () => ipcRenderer.removeListener('action:log-updated', listener)
  },
})