const { app, BrowserWindow, ipcMain, Menu, Notification, Tray, nativeImage, shell, globalShortcut } = require('electron')
const path = require('path')
const fs = require('fs/promises')
const AutoLaunch = require('auto-launch')
const { default: Store } = require('electron-store')
const { getSystemMetrics } = require('./monitor.cjs')
const { ActionExecutor } = require('./actionExecutor.cjs')
const { startToolServer } = require('./desktop-executor.cjs')
const { setupVADIPC } = require('./main/vad-ipc.cjs')

// ==================== 安全白名单配置 ====================
const ALLOWED_TOOLS = new Set([
  'file:list', 'file:read', 'file:write', 'file:delete', 'file:search',
  'system:info', 'system:command', 'system:env', 'system:hibernate', 'system:recycle', 'system:cleanmgr',
  'system:browser-cache', 'system:wechat-cache',
  'app:launch', 'clipboard:write',
  'notify', 'disk:list', 'temp:scan', 'temp:cleanup', 'disk:cleanup', 'disk:cleanup_advanced',
  'process:list', 'process:top', 'process:kill', 'network:request',
  'content:generate', 'ide:launch', 'browser:search', 'keyboard:type',
  'store:search', 'store:install', 'store:uninstall', 'store:list'
])

const DANGEROUS_TOOLS = new Set(['file:delete', 'file:write', 'process:kill', 'system:command', 'store:uninstall', 'store:install'])
const ALLOWED_SYSTEM_CMDS = new Set(['echo', 'whoami', 'date', 'uptime', 'uname', 'pwd', 'ls', 'df', 'ps'])
// ================================================

const isDev = process.env.NODE_ENV !== 'production'
const rendererUrl = process.env.ELECTRON_RENDERER_URL || 'http://localhost:5173'
const serverBaseUrl = process.env.AGENT_SERVER_URL || 'http://127.0.0.1:8000'
const alertCooldownMs = 30 * 1000
const alertMaxCooldownMs = 30 * 60 * 1000
const alertBackoffBaseMs = 60 * 1000
const WINDOW_BOUNDS_KEY = 'windowBounds'
const WINDOW_PREFS_KEY = 'windowPrefs'
const TRAY_ICON_PATH = path.join(__dirname, 'assets', 'tray-icon.png')
const MINI_MODE_SIZE = { width: 360, height: 480 }
const NORMAL_MODE_SIZE = { width: 1200, height: 800 }
const MINI_MODE_MARGIN = 20

const store = new Store({
  defaults: {
    [WINDOW_PREFS_KEY]: {
      alwaysOnTop: false,
      miniMode: false,
      launchAtLogin: false,
      minimizeToTray: true,
    },
  },
})

const autoLauncher = new AutoLaunch({
  name: 'AI Desktop Agent',
  path: process.execPath,
  appId: 'com.aitrading.desktop',
})

let mainWindow = null
let tray = null
let actionExecutor = null
let latestAutomationEvents = []
const alertState = new Map()
const alertFailureCount = new Map()
const alertLastNotified = new Map()

const FILE_ACTION_ROOTS = [
  app.getPath('desktop'),
  app.getPath('documents'),
  app.getPath('downloads'),
  app.getPath('temp'),
  app.getPath('home'),
  path.join(app.getPath('home'), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
  path.join(app.getPath('home'), 'AppData', 'Local'),
  path.join(app.getPath('home'), 'AppData', 'Roaming'),
  'C:\\Program Files',
  'C:\\Program Files (x86)',
  process.cwd(),
  path.resolve(__dirname, '..', '..', '..'),
  'D:\\',
  'E:\\',
  'F:\\',
]

function getWindowPrefs() {
  return store.get(WINDOW_PREFS_KEY)
}

function setWindowPrefs(nextPrefs) {
  const current = getWindowPrefs()
  const merged = { ...current, ...nextPrefs }
  store.set(WINDOW_PREFS_KEY, merged)
  return merged
}

async function syncAutoLaunch(enabled) {
  try {
    // auto-launch v5 使用 enable() / disable() API
    if (enabled) {
      await autoLauncher.enable()
    } else {
      await autoLauncher.disable()
    }
    return true
  } catch (error) {
    console.warn('[auto-launch] sync failed:', error)
    return false
  }
}

function normalizePath(targetPath) {
  return path.resolve(String(targetPath || ''))
}

function isPathAllowed(targetPath) {
  const normalized = normalizePath(targetPath).toLowerCase()
  return FILE_ACTION_ROOTS.some((root) => {
    const normalizedRoot = normalizePath(root).toLowerCase()
    return normalized === normalizedRoot || normalized.startsWith(`${normalizedRoot}${path.sep}`)
  })
}

function ensureAllowedPath(targetPath) {
  const normalized = normalizePath(targetPath)
  if (!isPathAllowed(normalized)) {
    throw new Error(`path is outside whitelist: ${normalized}`)
  }
  return normalized
}

async function listDirectoryEntries(targetPath) {
  const normalized = ensureAllowedPath(targetPath)
  const entries = await fs.readdir(normalized, { withFileTypes: true })
  const mapped = await Promise.all(
    entries
      .sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name, 'zh-CN'))
      .map(async (entry) => {
        const entryPath = path.join(normalized, entry.name)
        let stats = null
        let exists = true
        try {
          stats = await fs.stat(entryPath)
        } catch {
          stats = null
          exists = false
        }

        return {
          name: entry.name,
          path: entryPath,
          type: entry.isDirectory() ? 'directory' : 'file',
          size: stats?.size ?? 0,
          modifiedAt: stats?.mtime?.toISOString?.() ?? null,
          exists,
        }
      }),
  )

  const filtered = mapped.filter((entry) => entry.exists !== false)

  return {
    path: normalized,
    entries: filtered,
  }
}

async function deletePath(targetPath) {
  const normalized = ensureAllowedPath(targetPath)
  try {
    const stats = await fs.stat(normalized)
    if (stats.isDirectory()) {
      await fs.rm(normalized, { recursive: true, force: true })
    } else {
      try {
        await fs.unlink(normalized)
      } catch (unlinkErr) {
        if (unlinkErr.code === 'EBUSY' || unlinkErr.code === 'EPERM') {
          await fs.rm(normalized, { force: true })
        } else {
          throw unlinkErr
        }
      }
    }
    let verifyExists = false
    try {
      await fs.access(normalized)
      verifyExists = true
    } catch {
      verifyExists = false
    }
    if (verifyExists) {
      throw new Error(`删除失败: 文件 "${path.basename(normalized)}" 可能被其他程序占用，请关闭相关程序后重试`)
    }
    return {
      path: normalized,
      deleted: true,
      type: stats.isDirectory() ? 'directory' : 'file',
    }
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(`文件不存在: ${normalized}`)
    }
    if (err.code === 'EBUSY' || err.code === 'EPERM') {
      throw new Error(`删除失败: "${path.basename(normalized)}" 正在被其他程序使用，请先关闭相关程序`)
    }
    if (err.code === 'EACCES') {
      throw new Error(`删除失败: 没有权限删除 "${path.basename(normalized)}"，请以管理员身份运行`)
    }
    throw err
  }
}

async function openPathInShell(targetPath) {
  if (targetPath && targetPath.includes(':')) {
    const uriPattern = /^[a-zA-Z][a-zA-Z0-9+.-]*:.+$/
    if (uriPattern.test(targetPath)) {
      await shell.openExternal(targetPath)
      return {
        path: targetPath,
        opened: true,
        type: 'uri',
      }
    }
  }
  
  const normalized = ensureAllowedPath(targetPath)
  try {
    await fs.access(normalized)
  } catch {
    return { path: normalized, opened: false }
  }
  const result = await shell.openPath(normalized)
  if (result && result !== 0) {
    return { path: normalized, opened: false }
  }
  return {
    path: normalized,
    opened: true,
  }
}

function getDisplayWorkArea() {
  const targetWindow = mainWindow && !mainWindow.isDestroyed() ? mainWindow : null
  const electron = require('electron')
  const { screen } = electron
  if (targetWindow) {
    return screen.getDisplayMatching(targetWindow.getBounds()).workArea
  }
  return screen.getPrimaryDisplay().workArea
}

function clampBoundsToWorkArea(bounds, workArea) {
  const width = Math.min(bounds.width, workArea.width)
  const height = Math.min(bounds.height, workArea.height)
  const minX = workArea.x
  const minY = workArea.y
  const maxX = workArea.x + workArea.width - width
  const maxY = workArea.y + workArea.height - height

  return {
    width,
    height,
    x: Math.min(Math.max(bounds.x, minX), Math.max(minX, maxX)),
    y: Math.min(Math.max(bounds.y, minY), Math.max(minY, maxY)),
  }
}

function getCenteredBounds(size, workArea = getDisplayWorkArea()) {
  return {
    width: size.width,
    height: size.height,
    x: Math.round(workArea.x + (workArea.width - size.width) / 2),
    y: Math.round(workArea.y + (workArea.height - size.height) / 2),
  }
}

function getMiniModeBounds(workArea = getDisplayWorkArea()) {
  return {
    width: MINI_MODE_SIZE.width,
    height: MINI_MODE_SIZE.height,
    x: Math.round(workArea.x + workArea.width - MINI_MODE_SIZE.width - MINI_MODE_MARGIN),
    y: Math.round(workArea.y + workArea.height - MINI_MODE_SIZE.height - MINI_MODE_MARGIN),
  }
}

function getNormalModeBounds() {
  const storedBounds = store.get(WINDOW_BOUNDS_KEY)
  const workArea = getDisplayWorkArea()
  if (storedBounds?.width && storedBounds?.height) {
    return clampBoundsToWorkArea(storedBounds, workArea)
  }
  return getCenteredBounds(NORMAL_MODE_SIZE, workArea)
}

function ensureWindowVisible(win) {
  const visibleBounds = clampBoundsToWorkArea(win.getBounds(), getDisplayWorkArea())
  win.setBounds(visibleBounds)
}

function applyWindowPrefs(win, prefs, options = {}) {
  const { recenter = false } = options
  win.setAlwaysOnTop(Boolean(prefs.alwaysOnTop))
  if (prefs.miniMode) {
    win.setResizable(false)
    win.setBounds(getMiniModeBounds())
    return
  }

  win.setResizable(true)
  const nextBounds = recenter ? getCenteredBounds(NORMAL_MODE_SIZE) : getNormalModeBounds()
  win.setBounds(nextBounds)
  ensureWindowVisible(win)
}

function saveWindowBounds() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (getWindowPrefs().miniMode) return
  store.set(WINDOW_BOUNDS_KEY, clampBoundsToWorkArea(mainWindow.getBounds(), getDisplayWorkArea()))
}

function getTrayIcon() {
  const icon = nativeImage.createFromPath(TRAY_ICON_PATH)
  if (!icon.isEmpty()) {
    return icon.resize({ width: 16, height: 16 })
  }

  if (process.platform === 'win32') {
    return nativeImage.createFromPath(path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'shell32.dll'))
  }

  return nativeImage.createFromNamedImage('NSApplicationIcon', [16, 16])
}

function updateTrayMenu() {
  if (!tray) return
  const prefs = getWindowPrefs()
  const template = [
    {
      label: mainWindow?.isVisible() ? '隐藏主窗口' : '显示主窗口',
      click: () => toggleMainWindowVisibility(),
    },
    {
      label: prefs.alwaysOnTop ? '取消置顶' : '窗口置顶',
      click: () => toggleAlwaysOnTop(),
    },
    {
      label: prefs.miniMode ? '退出迷你模式' : '进入迷你模式',
      click: () => toggleMiniMode(),
    },
    { type: 'separator' },
    {
      label: '退出 AI Desktop Agent',
      click: () => app.quit(),
    },
  ]
  tray.setContextMenu(Menu.buildFromTemplate(template))
  tray.setToolTip('AI Desktop Agent')
}

function ensureTray() {
  if (tray) return tray
  tray = new Tray(getTrayIcon())
  tray.on('click', () => toggleMainWindowVisibility())
  updateTrayMenu()
  return tray
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow()
    return
  }
  mainWindow.show()
  mainWindow.focus()
}

function hideMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.hide()
}

function toggleMainWindowVisibility() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow()
    return { visible: true }
  }
  if (mainWindow.isVisible()) {
    hideMainWindow()
    updateTrayMenu()
    return { visible: false }
  }
  showMainWindow()
  updateTrayMenu()
  return { visible: true }
}

function toggleAlwaysOnTop() {
  const prefs = setWindowPrefs({ alwaysOnTop: !getWindowPrefs().alwaysOnTop })
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setAlwaysOnTop(Boolean(prefs.alwaysOnTop))
  }
  updateTrayMenu()
  return prefs
}

function toggleMiniMode() {
  const prefs = setWindowPrefs({ miniMode: !getWindowPrefs().miniMode })
  if (mainWindow && !mainWindow.isDestroyed()) {
    applyWindowPrefs(mainWindow, prefs, { recenter: !prefs.miniMode })
    showMainWindow()
  }
  updateTrayMenu()
  return prefs
}

async function setLaunchAtLogin(enabled) {
  const prefs = setWindowPrefs({ launchAtLogin: enabled })
  await syncAutoLaunch(Boolean(enabled))
  updateTrayMenu()
  return prefs
}

async function getDesktopPreferences() {
  const prefs = getWindowPrefs()
  // auto-launch v5 使用 isEnabled() 检查状态
  let autoLaunchEnabled = prefs.launchAtLogin
  try {
    autoLaunchEnabled = await autoLauncher.isEnabled()
  } catch (e) {
    console.warn('[auto-launch] isEnabled failed:', e)
  }
  return {
    ...prefs,
    launchAtLogin: autoLaunchEnabled,
    visible: Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible()),
  }
}

function createWindow() {
  const prefs = getWindowPrefs()
  const initialBounds = prefs.miniMode ? getMiniModeBounds() : getNormalModeBounds()

  const win = new BrowserWindow({
    ...initialBounds,
    minWidth: MINI_MODE_SIZE.width,
    minHeight: 420,
    center: !prefs.miniMode,
    backgroundColor: '#0b1020',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: !isDev,
    },
  })

  mainWindow = win
  applyWindowPrefs(win, prefs)
  ensureWindowVisible(win)
  if (isDev) {
    win.webContents.openDevTools()
  }

  win.once('ready-to-show', () => {
    win.show()
    updateTrayMenu()
  })

  if (isDev) {
    win.loadURL(rendererUrl).catch((error) => {
      const html = `
      <!doctype html>
      <html lang="zh-CN">
      <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>Renderer Load Failed</title>
      <style>
      body { margin:0; font-family: Arial, sans-serif; background: #0b1020; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height:100vh; }
      .panel { width: min(860px,92vw); background: #111827; border:1px solid #334155; border-radius:16px; padding:24px; }
      code, pre { display: block; white-space: pre-wrap; word-break: break-word; background: #020617; color: #93c5fd; padding:12px; border-radius:10px; }
      </style>
      </head>
      <body>
      <div class="panel">
      <h1>Electron 已启动，但前端地址无法加载</h1>
      <p>当前地址：</p>
      <code>${rendererUrl}</code>
      <p>错误：</p>
      <pre>${String(error?.message || error)}</pre>
      </div>
      </body>
      </html>
      `
      win.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(html)}`)
    })
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  win.on('resize', saveWindowBounds)
  win.on('move', saveWindowBounds)
  win.on('close', (event) => {
    if (process.platform !== 'darwin' && getWindowPrefs().minimizeToTray) {
      event.preventDefault()
      hideMainWindow()
      updateTrayMenu()
    }
  })
  win.on('closed', () => {
    mainWindow = null
    updateTrayMenu()
  })

  return win
}

function shouldDispatchAlert(alert) {
  const key = alert.type
  const now = Date.now()
  const previous = alertState.get(key) ?? 0
  const failures = alertFailureCount.get(key) ?? 0

  let currentCooldown = alertCooldownMs
  if (failures > 0) {
    currentCooldown = Math.min(
      alertMaxCooldownMs,
      alertBackoffBaseMs * Math.pow(2, Math.min(failures, 5))
    )
  }

  if (now - previous < currentCooldown) {
    return false
  }

  alertState.set(key, now)
  return true
}

function pushAutomationEvent(event) {
  latestAutomationEvents = [event, ...latestAutomationEvents].slice(0, 10)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('automation:event', event)
  }
}

function notifyAlert(alert) {
  if (!Notification.isSupported()) return

  const now = Date.now()
  const lastNotified = alertLastNotified.get(alert.type) ?? 0
  if (now - lastNotified < alertMaxCooldownMs) {
    return
  }
  alertLastNotified.set(alert.type, now)

  const notification = new Notification({
    title: `[${alert.level.toUpperCase()}] ${alert.title}`,
    body: alert.message,
  })

  notification.show()
}

async function requestAutomation(alert) {
  try {
    const response = await fetch(`${serverBaseUrl}/automation/handle-alert`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...alert,
        system_context: await getSystemMetrics(),
      }),
    })

    if (!response.ok) {
      throw new Error(`automation request failed: ${response.status}`)
    }

    const result = await response.json()
    
    const autoCommands = result.commands.filter(cmd => 
      cmd.auto_execute || ['read', 'network'].includes(cmd.type)
    )

    const pendingCommands = result.commands.filter(cmd => 
      cmd.type === 'destructive' && !cmd.auto_execute
    )

    let executionResults = []
    if (autoCommands.length > 0) {
      const commands = autoCommands.map((cmd, idx) => ({
        id: `${Date.now()}-${alert.type}-auto-${idx}`,
        tool: cmd.tool,
        type: cmd.type || 'system',
        params: cmd.params || {},
        reason: cmd.reason || '自动处置',
        confidence: cmd.confidence || 0.8,
      }))
      executionResults = await actionExecutor.executeCommands(commands)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('action:log-updated', { count: executionResults.length })
      }
    }

    const autoFailCount = executionResults.filter(r => !r.success).length
    const autoTotalCount = executionResults.length
    const autoAllFailed = autoTotalCount > 0 && autoFailCount === autoTotalCount

    if (pendingCommands.length > 0) {
      const pending = pendingCommands.map((cmd, idx) => ({
        id: `${Date.now()}-${alert.type}-pending-${idx}`,
        tool: cmd.tool,
        type: cmd.type || 'system',
        params: cmd.params || {},
        reason: cmd.reason || '需要确认的操作',
        confidence: cmd.confidence || 0.8,
      }))

      const existingPids = new Set(
        pendingActionsQueue
          .filter(p => p.tool === 'process:kill')
          .map(p => p.params?.pid)
          .filter(Boolean)
      )
      const existingNames = new Set(
        pendingActionsQueue
          .filter(p => p.tool === 'process:kill' && p.params?.name)
          .map(p => String(p.params.name).toLowerCase())
      )
      const existingSignatures = new Set(
        pendingActionsQueue.map(p => `${p.tool}::${JSON.stringify(p.params || {})}`)
      )

      const filtered = pending.filter(p => {
        if (p.tool === 'process:kill' && existingPids.has(p.params?.pid)) return false
        if (p.tool === 'process:kill' && p.params?.name && existingNames.has(String(p.params.name).toLowerCase())) return false
        const sig = `${p.tool}::${JSON.stringify(p.params || {})}`
        if (existingSignatures.has(sig)) return false
        return true
      })

      const uniqueNew = dedupePendingQueue(pendingActionsQueue, filtered)
      pendingActionsQueue.push(...uniqueNew)
      pendingActionsQueue = trimPendingQueue(pendingActionsQueue)

      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pending-actions', pendingActionsQueue)
      }
    }

    if (autoAllFailed) {
      const failures = (alertFailureCount.get(alert.type) ?? 0) + 1
      alertFailureCount.set(alert.type, failures)
    } else {
      alertFailureCount.set(alert.type, 0)
    }

    const event = {
      id: `${Date.now()}-${alert.type}`,
      timestamp: new Date().toISOString(),
      source: 'agent',
      alert,
      result,
      executionResults,
      speechText: `${alert.title}。${result.action}${executionResults.length > 0 ? ` 已执行 ${executionResults.length} 个操作` : ''}`,
    }

    pushAutomationEvent(event)
    return event
  } catch (error) {
    const failures = (alertFailureCount.get(alert.type) ?? 0) + 1
    alertFailureCount.set(alert.type, failures)

    const event = {
      id: `${Date.now()}-${alert.type}`,
      timestamp: new Date().toISOString(),
      source: 'fallback',
      alert,
      result: {
        summary: `自动处置接口调用失败：${error.message}`,
        action: '已降级为本地通知，等待人工处理。',
        priority: alert.level === 'critical' ? 'high' : 'medium',
      },
      executionResults: [],
      speechText: `${alert.title}。自动处置接口暂不可用，请手动处理。`,
    }

    pushAutomationEvent(event)
    return event
  }
}

async function processAlerts(alerts) {
  const freshAlerts = alerts.filter(shouldDispatchAlert)
  for (const alert of freshAlerts) {
    const event = await requestAutomation(alert)
    const source = event?.source
    const failures = alertFailureCount.get(alert.type) ?? 0
    const needNotify = source === 'fallback' || (source === 'agent' && failures > 0)
    if (needNotify && failures <= 3) {
      notifyAlert(alert)
    }
  }
}

/** pendingActionsQueue 管理待确认的危险操作 */
let pendingActionsQueue = []
const MAX_PENDING_QUEUE = 20;  // 最多堆积 20 个
const MAX_PENDING_PROCESS_KILL = 5;  // process:kill 最多 5 个

function dedupePendingQueue(queue, newItems) {
  const seen = new Set(queue.map(i => `${i.tool}::${JSON.stringify(i.params)}`));
  const filtered = [];
  for (const item of newItems) {
    const sig = `${item.tool}::${JSON.stringify(item.params)}`;
    if (seen.has(sig)) continue;
    seen.add(sig);
    filtered.push(item);
  }
  return filtered;
}

function trimPendingQueue(queue) {
  if (queue.length <= MAX_PENDING_QUEUE) return queue;
  const withoutKill = queue.filter(p => p.tool !== 'process:kill');
  const killItems = queue.filter(p => p.tool === 'process:kill').slice(-MAX_PENDING_PROCESS_KILL);
  const total = [...withoutKill, ...killItems];
  return total.slice(-MAX_PENDING_QUEUE);
}

function registerActionIpc() {
  // 主进程安全校验：与 preload 相同的白名单校验（最终防线）
  ipcMain.handle('action:execute', async (_, commands) => {
    const arr = Array.isArray(commands) ? commands : []
    
    // 主进程独立校验
    for (const cmd of arr) {
      if (!cmd?.tool || !ALLOWED_TOOLS.has(cmd.tool)) {
        throw new Error(`[main] tool rejected: ${cmd?.tool}`)
      }
      if ((cmd.tool === 'file:delete' || cmd.tool === 'file:write') && cmd.params?.path) {
        ensureAllowedPath(cmd.params.path) // 会 throw
      }
      if (cmd.tool === 'system:command' && cmd.params?.command) {
        const cmdName = cmd.params.command.split(/\s+/)[0]
        if (!ALLOWED_SYSTEM_CMDS.has(cmdName)) throw new Error(`[main] system command rejected: ${cmdName}`)
      }
      if (cmd.tool === 'process:kill' && typeof cmd.params?.pid !== 'number' && typeof cmd.params?.name !== 'string') {
        throw new Error('[main] process:kill requires numeric pid or string name')
      }
    }
    
    if (!actionExecutor) {
      return [{ id: 'executor', success: false, error: 'action executor is not ready' }]
    }
    const results = await actionExecutor.executeCommands(arr)
    // 执行完成后通知前端刷新日志
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('action:log-updated', { count: results.length })
    }
    return results
  })

  ipcMain.handle('action:pause', () => {
    if (!actionExecutor) return { status: 'unavailable' }
    return actionExecutor.pause()
  })

  ipcMain.handle('action:resume', () => {
    if (!actionExecutor) return { status: 'unavailable' }
    return actionExecutor.resume()
  })

  ipcMain.handle('action:log', (_, limit) => {
    if (!actionExecutor) return []
    return actionExecutor.getExecutionLog(limit)
  })

  /** 获取 pendingActionsQueue 中的待确认操作 */
  ipcMain.handle('action:pending:get', () => pendingActionsQueue)

  /** 从 pendingActionsQueue 中移除已确认的操作 */
  ipcMain.handle('action:pending:clear', (_, ids) => {
    const idSet = new Set(Array.isArray(ids) ? ids : [ids])
    const removed = pendingActionsQueue.filter(item => idSet.has(item.id))
    pendingActionsQueue = pendingActionsQueue.filter(item => !idSet.has(item.id))
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('pending-actions', pendingActionsQueue)
    }
    return removed
  })

  /** 将危险操作添加到 pendingActionsQueue */
  ipcMain.handle('action:pending:add', (_, actions) => {
    const toAdd = Array.isArray(actions) ? actions : [actions]
    
    // 主进程安全校验：工具白名单 + 参数审查
    for (const cmd of toAdd) {
      if (!cmd?.tool || !ALLOWED_TOOLS.has(cmd.tool)) {
        throw new Error(`[main] pending add rejected: tool "${cmd?.tool}" not in whitelist`)
      }
      if ((cmd.tool === 'file:delete' || cmd.tool === 'file:write') && cmd.params?.path) {
        ensureAllowedPath(cmd.params.path) // 会 throw
      }
      if (cmd.tool === 'system:command' && cmd.params?.command) {
        const cmdName = cmd.params.command.split(/\s+/)[0]
        if (!ALLOWED_SYSTEM_CMDS.has(cmdName)) {
          throw new Error(`[main] pending add rejected: system command "${cmdName}" not allowed`)
        }
      }
      if (cmd.tool === 'process:kill' && typeof cmd.params?.pid !== 'number' && typeof cmd.params?.name !== 'string') {
        throw new Error('[main] pending add rejected: process:kill requires numeric pid or string name')
      }
    }
    
    // 去重 + 限流 + 入队
    const uniqueNew = dedupePendingQueue(pendingActionsQueue, toAdd)
    pendingActionsQueue.push(...uniqueNew)
    pendingActionsQueue = trimPendingQueue(pendingActionsQueue)
    // 通知前端有新待确认操作
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('pending-actions', pendingActionsQueue)
    }
    return pendingActionsQueue
  })
}

app.whenReady().then(async () => {
  // 初始化 VAD IPC 处理器
  setupVADIPC()
  
  ensureTray()
  await syncAutoLaunch(Boolean(getWindowPrefs().launchAtLogin))

  actionExecutor = new ActionExecutor({
    getMainWindow: () => mainWindow,
    ensureAllowedPath,
    listDirectoryEntries,
    deletePath,
    openPathInShell,
  })

  registerActionIpc()

  ipcMain.handle('system:metrics:get', async () => {
    const metrics = await getSystemMetrics()
    await processAlerts(metrics.alerts)
    return {
      ...metrics,
      automationEvents: latestAutomationEvents,
    }
  })

  ipcMain.handle('automation:events:list', () => latestAutomationEvents)
  ipcMain.handle('system:file-roots:list', () => FILE_ACTION_ROOTS)
  ipcMain.handle('system:file:list', async (_, targetPath) => listDirectoryEntries(targetPath))
  ipcMain.handle('system:file:delete', async (_, targetPath) => deletePath(targetPath))
  ipcMain.handle('system:file:open', async (_, targetPath) => openPathInShell(targetPath))
  ipcMain.handle('window:preferences:get', async () => getDesktopPreferences())
  ipcMain.handle('window:visibility:toggle', () => toggleMainWindowVisibility())
  ipcMain.handle('window:always-on-top:toggle', () => toggleAlwaysOnTop())
  ipcMain.handle('window:mini-mode:toggle', () => toggleMiniMode())
  ipcMain.handle('window:launch-at-login:set', async (_, enabled) => setLaunchAtLogin(Boolean(enabled)))

  // 后端配置 IPC（运行时可修改后端地址）
  const BACKEND_CONFIG_KEY = 'backendConfig'
  store.set(BACKEND_CONFIG_KEY, { apiBase: serverBaseUrl })
  
  ipcMain.handle('config:backend:get', () => store.get(BACKEND_CONFIG_KEY) || { apiBase: serverBaseUrl })
  ipcMain.handle('config:backend:set', (_, config) => {
    const current = store.get(BACKEND_CONFIG_KEY) || {}
    const updated = { ...current, ...config }
    store.set(BACKEND_CONFIG_KEY, updated)
    return updated
  })

  // ==================== VAD IPC Handlers ====================
  // 注意：VAD IPC handlers 已在 setupVADIPC() 中注册
  // 以下保留供其他模块使用

  // 注册全局快捷键 Ctrl+Alt+A 切换语音监听
  const shortcut = process.platform === 'darwin' ? 'Cmd+Alt+A' : 'Ctrl+Alt+A'
  const registered = globalShortcut.register(shortcut, () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('voice:toggle-listening')
      console.log('[main] Voice toggle triggered by shortcut')
    }
  })
  if (registered) {
    console.log(`[main] Global shortcut registered: ${shortcut}`)
  } else {
    console.warn('[main] Failed to register global shortcut')
  }

  createWindow()

  // 启动桌面工具服务（供后端 Python ReAct 调用）
  startToolServer(9000, {
    actionExecutor,
    validateCommand: (tool, params) => {
      try {
        if (!ALLOWED_TOOLS.has(tool)) {
          return { ok: false, error: `tool rejected: ${tool}` }
        }
        if ((tool === 'file:delete' || tool === 'file:write') && params?.path) {
          ensureAllowedPath(params.path)
        }
        if (tool === 'system:command' && params?.command) {
          const cmdName = params.command.split(/\s+/)[0]
          if (!ALLOWED_SYSTEM_CMDS.has(cmdName)) {
            return { ok: false, error: `system command rejected: ${cmdName}` }
          }
        }
        if (tool === 'process:kill' && typeof params?.pid !== 'number' && typeof params?.name !== 'string') {
          return { ok: false, error: 'process:kill requires numeric pid or string name' }
        }
        return { ok: true }
      } catch (e) {
        return { ok: false, error: e.message }
      }
    },
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    else showMainWindow()
  })
})

app.on('before-quit', () => {
  store.set(`${WINDOW_PREFS_KEY}.minimizeToTray`, false)
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})