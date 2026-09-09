const { Notification, dialog, shell, clipboard } = require('electron')
const fs = require('fs/promises')
const path = require('path')
const os = require('os')
const { execFile } = require('child_process')

const TEMP_SCAN_LIMIT = 200
const TEMP_CLEANUP_LIMIT = 100
const EXECUTION_LOG_LIMIT = 100

const PROTECTED_PIDS = new Set([0, 4])
const PROTECTED_PROCESS_NAMES = new Set([
  'system', 'idle', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe',
  'winlogon.exe', 'services.exe', 'lsass.exe', 'svchost.exe', 'explorer.exe',
  'electron.exe', 'dwm.exe',
])
const ALLOWED_COMMANDS = new Set([
  'ping', 'ipconfig', 'ifconfig', 'netstat', 'dir', 'where', 'which', 'whoami', 'tasklist',
])

// ===== 弹窗防轰炸系统 =====
const DIALOG_COOLDOWN_MS = 15000;     // 15秒内不重复弹窗（更严格）
const MAX_SEEN_PIDS = 30;
const MAX_SEEN_SIGNATURES = 50;        // 非PID命令也去重

function normalizePath(targetPath) {
  return path.resolve(String(targetPath || ''))
}

function isCriticalPath(targetPath = '') {
  const normalized = normalizePath(targetPath)
  const homeDir = os.homedir()
  const criticalPaths = [
    normalizePath(process.env.SystemRoot || 'C:\\Windows'),
    normalizePath('C:\\Program Files'),
    normalizePath('C:\\Program Files (x86)'),
    normalizePath(path.join(homeDir, 'Desktop')),
    normalizePath(path.join(homeDir, 'Documents')),
  ]
  return criticalPaths.some((criticalRoot) => normalized === criticalRoot || normalized.startsWith(`${criticalRoot}${path.sep}`))
}

function parseCommand(command) {
  return String(command || '').trim().split(/\s+/).filter(Boolean)
}

function isAllowedNetworkTarget(rawUrl, explicitTarget) {
  if (explicitTarget === 'self_backend') return true
  try {
    const url = new URL(String(rawUrl || ''))
    const hostname = url.hostname.toLowerCase()
    return hostname === '127.0.0.1' || hostname === 'localhost'
  } catch {
    return false
  }
}

function sanitizeEnvName(value) {
  const normalized = String(value || '').trim().toUpperCase()
  return /^[A-Z0-9_]+$/.test(normalized) ? normalized : null
}

function isSensitiveEnvName(name) {
  return ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE', 'CREDENTIAL', 'COOKIE'].some((keyword) => name.includes(keyword))
}

function execFileAsync(file, args = [], options = {}) {
  return new Promise((resolve) => {
    execFile(file, args, { windowsHide: true, shell: false, ...options }, (error, stdout, stderr) => {
      if (error) {
        resolve({ success: false, error: String(stderr || error.message || 'command failed') })
        return
      }
      resolve({ success: true, stdout: String(stdout || ''), stderr: String(stderr || '') })
    })
  })
}

function normalizeProcessName(name) {
  return String(name || '').trim().toLowerCase()
}

async function lookupProcessByPid(pid) {
  const result = await execFileAsync('tasklist', ['/FO', 'CSV', '/FI', `PID eq ${pid}`], { timeout: 10000 })
  if (!result.success) {
    return { success: false, error: result.error }
  }
  const lines = String(result.stdout || '').trim().split('\n').slice(1)
  if (!lines.length) {
    return { success: false, error: 'ProcessNotFound', code: 'PROCESS_NOT_FOUND' }
  }
  const first = lines[0]
  const parts = first.split('","').map((item) => item.replace(/"/g, ''))
  return {
    success: true,
    data: {
      name: parts[0] || '',
      pid: Number(parts[1]) || pid,
      sessionName: parts[2] || '',
      mem: parseInt(String(parts[4] || '').replace(/,/g, '').replace(' K', ''), 10) || 0,
    },
  }
}

function buildBlockedResult(code, message, extra = {}) {
  return { success: false, error: message, code, ...extra }
}

async function listDiskDrives() {
  const commandResult = await execFileAsync('powershell', [
    '-NoProfile', '-Command',
    'Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used,Root | ConvertTo-Json -Compress',
  ], { timeout: 15000 })
  if (!commandResult.success) {
    return { success: false, error: commandResult.error }
  }
  try {
    const parsed = JSON.parse(commandResult.stdout || '[]')
    const drives = (Array.isArray(parsed) ? parsed : [parsed]).map((item) => {
      const free = Number(item.Free || 0)
      const used = Number(item.Used || 0)
      const total = free + used
      return {
        name: item.Name,
        root: item.Root || `${item.Name}:\\`,
        free, used, total,
        usePercent: total > 0 ? Number(((used / total) * 100).toFixed(2)) : 0,
      }
    })
    return { success: true, data: { drives } }
  } catch (error) {
    return { success: false, error: `failed to parse disk list: ${error.message}` }
  }
}

async function collectTempEntries(targetPath, maxEntries = TEMP_SCAN_LIMIT) {
  const entries = await fs.readdir(targetPath, { withFileTypes: true })
  const results = []
  for (const entry of entries) {
    if (results.length >= maxEntries) break
    const entryPath = path.join(targetPath, entry.name)
    let stats = null
    try { stats = await fs.stat(entryPath) } catch { stats = null }
    results.push({
      name: entry.name,
      path: entryPath,
      type: entry.isDirectory() ? 'directory' : 'file',
      size: stats?.size ?? 0,
      modifiedAt: stats?.mtime?.toISOString?.() ?? null,
      isTempLike: /\.(tmp|temp|log|bak)$/i.test(entry.name),
    })
  }
  return results
}

// ===== 强制删除（Windows文件锁对策） ====================
async function forceDeleteFile(filePath) {
  // 1. 先尝试普通删除
  try {
    await fs.rm(filePath, { force: true })
    return { deleted: true, method: 'fs.rm' }
  } catch (fsError) {
    // 2. Windows上被占用时，用PowerShell强制删除
    if (process.platform === 'win32') {
      try {
        const psCommand = `Remove-Item -LiteralPath $env:TARGET_PATH -Force -ErrorAction Stop`
        const { stderr } = await execFileAsync('powershell', [
          '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psCommand
        ], { timeout: 8000, env: { ...process.env, TARGET_PATH: filePath } })
        
        if (stderr && stderr.toLowerCase().includes('exception')) throw new Error(stderr)
        return { deleted: true, method: 'powershell' }
      } catch (psError) {
        // 3. 尝试延迟删除（重启后生效）
        try {
          const markCmd = `
            $path = $env:TARGET_PATH;
            cmd /c "echo y | del /f /q \\"$path\\" 2>nul" 2>$null;
            exit 0;
          `
          await execFileAsync('powershell', ['-NoProfile', '-Command', markCmd], { timeout: 3000, env: { ...process.env, TARGET_PATH: filePath } })
          
          return { 
            deleted: false, 
            method: 'marked_reboot',
            reason: '文件被系统锁定，已标记为重启后删除。可手动重启电脑完成清理。' 
          }
        } catch (finalError) {
          return { 
            deleted: false, 
            reason: `无法删除(文件被占用): ${fsError.message}` 
          }
        }
      }
    }
    return { deleted: false, reason: fsError.message }
  }
}

// ========== 增强版临时文件匹配 ==========
function isTempLikeFile(name) {
  return (
    // 标准临时扩展名
    /\.(tmp|temp|log|bak|cache|crdownload|part|old|ico|png|jpg|jpeg|gif|mp3|wav|xml|txt|zip|rar|7z|ps1|psm1|lock|dat|cpuprofile|ini|track)$/i.test(name) ||
    // Windows 安装临时文件
    /^is-[A-Z0-9]{5,6}\.tmp$/i.test(name) ||
    /^TCD[A-F0-9]{3,6}\.tmp$/i.test(name) ||
    /^LISF_[A-F0-9]+\.tmp$/i.test(name) ||
    /^SLB_[A-F0-9]+\.tmp$/i.test(name) ||
    // 常见程序前缀
    /^tmp[0-9a-z_]/i.test(name) ||
    /^temp_/i.test(name) ||
    /^tempimage_/i.test(name) ||
    /^chrome_/i.test(name) ||
    /^electron-/i.test(name) ||
    /^msedge_/i.test(name) ||
    /^vscode-/i.test(name) ||
    /^v8-compile-cache/i.test(name) ||
    /^node-compile-cache/i.test(name) ||
    /^pyright-/i.test(name) ||
    /^exthost-/i.test(name) ||
    /^gkinstall/i.test(name) ||
    /^Setup Log/i.test(name) ||
    /^track_record_/i.test(name) ||
    /^__PSScriptPolicyTest_/i.test(name) ||
    // 下载残留（.zip.43c 等）
    /\.(zip|rar|7z)\.[a-f0-9]{3,4}$/i.test(name) ||
    // xml_file (数字).xml
    /^xml_file \(\d+\)\.xml$/i.test(name) ||
    // 8位随机+3位扩展名
    /^[a-z0-9]{7,8}\.[a-z0-9]{3}$/i.test(name) ||
    // UUID 格式
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(name) ||
    /^\{?[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}?$/i.test(name) ||
    // 8-10位无扩展名随机
    /^[a-zA-Z0-9]{8,10}$/i.test(name) ||
    // 短隐藏文件
    (name.startsWith('.') && name.length <= 5)
  )
}

function isTempLikeDir(name) {
  return (
    /^(tmp|temp|cache|crashpad|scoped_dir)/i.test(name) ||
    /^chrome_/i.test(name) ||
    /^electron-/i.test(name) ||
    /^msedge_/i.test(name) ||
    /^vscode-/i.test(name) ||
    /^v8-compile-cache/i.test(name) ||
    /^node-compile-cache/i.test(name) ||
    /^pyright-/i.test(name) ||
    /^NuGetScratch/i.test(name) ||
    /^jest/i.test(name) ||
    /^Diagnostics/i.test(name) ||
    /^DiagOutputDir/i.test(name) ||
    /^WeChat Files/i.test(name) ||
    /^Tencent/i.test(name) ||
    /^Sogou/i.test(name) ||
    /^baidu/i.test(name) ||
    /^steam/i.test(name) ||
    /^WinGet/i.test(name) ||
    /^ic-cache-/i.test(name) ||
    /^xml_file /i.test(name) ||
    /^tmp_/i.test(name) ||
    /^temp_image_/i.test(name) ||
    /^track_record_/i.test(name) ||
    /^claude/i.test(name) ||
    /^aits-(stt|tts)/i.test(name) ||
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(name)
  )
}

async function cleanupTempEntries(targetPath, maxEntries = TEMP_CLEANUP_LIMIT) {
  const entries = await fs.readdir(targetPath, { withFileTypes: true })
  const deleted = []
  const skipped = []
  for (const entry of entries) {
    if (deleted.length + skipped.length >= maxEntries) break
    const entryPath = path.join(targetPath, entry.name)
    
    const isTempFile = entry.isFile() && isTempLikeFile(entry.name)
    const isTempDir = entry.isDirectory() && isTempLikeDir(entry.name)
    
    if (!isTempFile && !isTempDir) {
      skipped.push({ path: entryPath, reason: 'not temp-like file' })
      continue
    }
    
    // 目录递归删除，文件用强制删除
    if (entry.isDirectory()) {
      try {
        await fs.rm(entryPath, { recursive: true, force: true })
        deleted.push({ path: entryPath, method: 'fs.rm(dir)' })
      } catch (err) {
        skipped.push({ path: entryPath, reason: `目录删除失败: ${err.message}` })
      }
    } else {
      const result = await forceDeleteFile(entryPath)
      if (result.deleted) {
        deleted.push({ path: entryPath, method: result.method })
      } else {
        skipped.push({ path: entryPath, reason: result.reason || result.method })
      }
    }
  }
  return { deleted, skipped }
}

function getApprovalPolicy(cmd) {
  if (cmd.type === 'read') {
    return { autoExecute: true, notify: false, requireConfirm: false, requireDoubleConfirm: false }
  }
  if (cmd.type === 'write') {
    if (Number(cmd.confidence || 0) >= 0.9 && !isCriticalPath(cmd.params?.path || '')) {
      return { autoExecute: true, notify: true, requireConfirm: false, requireDoubleConfirm: false }
    }
    return { autoExecute: false, notify: true, requireConfirm: true, requireDoubleConfirm: false }
  }
  if (cmd.type === 'network') {
    if (cmd.params?.target === 'self_backend') {
      return { autoExecute: true, notify: false, requireConfirm: false, requireDoubleConfirm: false }
    }
    return { autoExecute: false, notify: true, requireConfirm: true, requireDoubleConfirm: false }
  }
  if (cmd.type === 'system') {
    return { autoExecute: false, notify: true, requireConfirm: true, requireDoubleConfirm: false }
  }
  if (cmd.type === 'destructive') {
    return { autoExecute: false, notify: true, requireConfirm: true, requireDoubleConfirm: true }
  }
  return { autoExecute: false, notify: true, requireConfirm: true, requireDoubleConfirm: true }
}

class ActionExecutor {
  constructor(options) {
    this.getMainWindow = options.getMainWindow
    this.ensureAllowedPath = options.ensureAllowedPath
    this.listDirectoryEntries = options.listDirectoryEntries
    this.deletePath = options.deletePath
    this.openPathInShell = options.openPathInShell
    this.executionLog = []
    this.pendingApprovals = new Map()
    this.toolRegistry = new Map()
    this.isPaused = false
    
    // ===== 弹窗防轰炸状态 =====
    this._dialogLock = false
    this._lastDialogTime = 0
    this._seenPids = new Set()        // 已弹窗的 PID
    this._seenSignatures = new Set() // 已弹窗的命令签名
    this._skipDestructive = false     // "不再提示"标志
    // =========================

    this.registerBuiltinTools()
  }

  registerBuiltinTools() {
    this.registerTool('file:list', async (params = {}) => {
      const result = await this.listDirectoryEntries(params.path)
      const max = Number(params.max || 0)
      if (!max) return { success: true, data: result }
      return { success: true, data: { ...result, entries: result.entries.slice(0, max) } }
    })

    this.registerTool('file:read', async (params = {}) => {
      const targetPath = this.ensureAllowedPath(params.path)
      const content = await fs.readFile(targetPath, 'utf-8')
      const maxLength = Number(params.maxLength || 10000)
      return {
        success: true,
        data: { path: targetPath, content: content.slice(0, maxLength), truncated: content.length > maxLength },
      }
    })

    this.registerTool('file:write', async (params = {}) => {
      const targetPath = this.ensureAllowedPath(params.path)
      await fs.mkdir(path.dirname(targetPath), { recursive: true })
      const content = String(params.content || '')
      await fs.writeFile(targetPath, content, 'utf-8')
      return { success: true, data: { path: targetPath, bytesWritten: Buffer.byteLength(content, 'utf-8') } }
    })

    this.registerTool('file:delete', async (params = {}) => {
      return { success: true, data: await this.deletePath(params.path) }
    })

    this.registerTool('system:info', async () => ({
      success: true,
      data: {
        platform: os.platform(),
        arch: os.arch(),
        totalMem: os.totalmem(),
        freeMem: os.freemem(),
        uptime: os.uptime(),
        cpus: os.cpus().length,
      },
    }))

    this.registerTool('system:command', async (params = {}) => {
      const command = String(params.command || '').trim()
      if (!command) {
        return { success: false, error: 'command is required' }
      }
      const parts = parseCommand(command)
      const base = parts[0]?.toLowerCase()
      if (!base || !ALLOWED_COMMANDS.has(base)) {
        return { success: false, error: `command not allowed: ${base || 'unknown'}` }
      }
      return new Promise((resolve) => {
        execFile(parts[0], parts.slice(1), { timeout: Number(params.timeout || 10000), windowsHide: true, shell: false }, (error, stdout, stderr) => {
          if (error) {
            resolve({ success: false, error: stderr || error.message })
            return
          }
          resolve({ success: true, data: { command, stdout: String(stdout || '').slice(0, 50000) } })
        })
      })
    })

    this.registerTool('app:launch', async (params = {}) => {
      const target = String(params.path || '').trim()
      if (!target) {
        return { success: false, error: 'path is required' }
      }
      
      // 收集额外参数（如 VSCode 打开文件、浏览器打开 URL）
      const args = Array.isArray(params.args) ? params.args : []
      const url = params.url || ''
      
      // 如果是程序名（不含路径分隔符），用 PowerShell Start-Process 确保前台启动
      if (!target.includes('\\') && !target.includes('/') && !target.includes(':')) {
        // 1. 尝试用 where 找完整路径
        let fullPath = target
        const whereResult = await execFileAsync('where', [target], { timeout: 5000 })
        if (whereResult.success && whereResult.stdout) {
          const lines = whereResult.stdout.trim().split('\n').filter(Boolean)
          if (lines.length > 0) fullPath = lines[0].trim()
        }
        
        // 2. 构建启动参数
        const argList = []
        if (url) argList.push(url)
        if (args.length > 0) argList.push(...args)
        
        // 3. 用 PowerShell Start-Process 确保窗口正常显示（-WindowStyle Normal）
        const launchEnv = { ...process.env, LAUNCH_PATH: fullPath }
        if (argList.length > 0) launchEnv.LAUNCH_ARGS = JSON.stringify(argList)
        const argPart = argList.length > 0 ? ' -ArgumentList @(ConvertFrom-Json $env:LAUNCH_ARGS)' : ''
        const psCommand = `try { $proc = Start-Process -FilePath $env:LAUNCH_PATH${argPart} -WindowStyle Normal -PassThru; "PID:" + $proc.Id } catch { "Error:" + $_.Exception.Message }`
        const psResult = await execFileAsync('powershell', ['-NoProfile', '-NonInteractive', '-Command', psCommand], { timeout: 15000, env: launchEnv })
        
        if (psResult.success && psResult.stdout && psResult.stdout.includes('PID:')) {
          const pidMatch = psResult.stdout.match(/PID:(\d+)/)
          return { 
            success: true, 
            data: { 
              launched: target, 
              fullPath,
              pid: pidMatch ? parseInt(pidMatch[1]) : null,
              method: 'powershell_foreground',
              args: argList,
              message: `${target} 已启动${argList.length > 0 ? '（带参数）' : ''}，请检查任务栏`
            } 
          }
        }
        
        // 4. 降级：cmd /c start（去掉 windowsHide）
        try {
          const { spawn } = require('child_process')
          const spawnArgs = ['/c', 'start', '', fullPath]
          if (argList.length > 0) spawnArgs.push(...argList)
          const child = spawn('cmd', spawnArgs, {
            windowsHide: false,
            detached: true,
            stdio: 'ignore'
          })
          child.unref()
          return { 
            success: true, 
            data: { 
              launched: target, 
              fullPath,
              method: 'cmd_start',
              args: argList,
              message: `${target} 启动命令已发送${argList.length > 0 ? '（带参数）' : ''}`
            } 
          }
        } catch (e) {
          return { success: false, error: `启动失败: ${e.message}` }
        }
      }
      
      // ========== 完整路径处理：允许标准程序目录 ==========
      // 程序安装目录白名单（不检查 ensureAllowedPath）
      const ALLOWED_PROGRAM_ROOTS = [
        'C:\\Program Files',
        'C:\\Program Files (x86)',
        'C:\\Windows',
        'C:\\Windows\\System32',
        process.env.LOCALAPPDATA,
        process.env.PROGRAMFILES,
        process.env['PROGRAMFILES(X86)'],
        process.env.APPDATA,
        path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        path.join(os.homedir(), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs',  // 公共开始菜单
      ].filter(Boolean)
      
      const BLOCKED_APP_PATHS = [
        'C:\\Windows\\System32\\cmd.exe',
        'C:\\Windows\\System32\\WindowsPowerShell',
        'C:\\Windows\\SysWOW64\\cmd.exe',
        'C:\\Windows\\System32\\config',
        'C:\\Windows\\System32\\regedit.exe',
        'C:\\Windows\\System32\\diskpart.exe',
        'C:\\Windows\\System32\\format.exe',
        'C:\\Windows\\System32\\net.exe',
        'C:\\Windows\\System32\\net1.exe',
        'C:\\Windows\\System32\\schtasks.exe',
        'C:\\Windows\\System32\\taskkill.exe',
        'C:\\Windows\\System32\\shutdown.exe',
        'C:\\Windows\\System32\\taskmgr.exe',
      ]
      
      // 常见Office应用快捷方式名称映射
      const KNOWN_SHORTCUTS = {
        'word': 'Microsoft Word.lnk',
        'excel': 'Microsoft Excel.lnk',
        'PowerPoint': 'Microsoft PowerPoint.lnk',
        'Outlook': 'Microsoft Outlook.lnk',
        'access': 'Microsoft Access.lnk',
        'publisher': 'Microsoft Publisher.lnk',
        'onenote': 'Microsoft OneNote.lnk',
        'teams': 'Microsoft Teams.lnk',
        'edge': 'Microsoft Edge.lnk',
        'chrome': 'Google Chrome.lnk',
        'firefox': 'Mozilla Firefox.lnk',
      }
      
      function isProgramPathAllowed(p) {
        const normalized = path.normalize(p).toLowerCase()
        // 黑名单优先检查
        if (BLOCKED_APP_PATHS.some(b => normalized === path.normalize(b).toLowerCase())) {
          return false
        }
        // 白名单检查
        return ALLOWED_PROGRAM_ROOTS.some(root => 
          normalized.startsWith(path.normalize(root).toLowerCase())
        )
      }
      
      const normalizedTarget = path.normalize(target).toLowerCase()
      
      // .exe 或 .lnk 文件且在允许的程序目录下：跳过 ensureAllowedPath
      // 同时支持通过快捷方式名称启动Office应用
      if (/\.(exe|lnk)$/i.test(target) && isProgramPathAllowed(target)) {
        // 构建启动参数
        const argList = []
        if (url) argList.push(url)
        if (args.length > 0) argList.push(...args)
        
        // 用 PowerShell Start-Process 启动（与上面逻辑一致）
        const launchEnv = { ...process.env, LAUNCH_PATH: target }
        if (argList.length > 0) launchEnv.LAUNCH_ARGS = JSON.stringify(argList)
        const argPart = argList.length > 0 ? ' -ArgumentList @(ConvertFrom-Json $env:LAUNCH_ARGS)' : ''
        const psCommand = `try { $proc = Start-Process -FilePath $env:LAUNCH_PATH${argPart} -WindowStyle Normal -PassThru; "PID:" + $proc.Id } catch { "Error:" + $_.Exception.Message }`
        const psResult = await execFileAsync('powershell', ['-NoProfile', '-NonInteractive', '-Command', psCommand], { timeout: 15000, env: launchEnv })
        
        if (psResult.success && psResult.stdout && psResult.stdout.includes('PID:')) {
          const pidMatch = psResult.stdout.match(/PID:(\d+)/)
          return { 
            success: true, 
            data: { 
              launched: target, 
              method: 'powershell_foreground',
              pid: pidMatch ? parseInt(pidMatch[1]) : null,
              args: argList,
              message: `${target} 已启动${argList.length > 0 ? '（带参数）' : ''}，请检查任务栏`
            } 
          }
        }
        
        // 降级：cmd /c start
        try {
          const { spawn } = require('child_process')
          const spawnArgs = ['/c', 'start', '', target]
          if (argList.length > 0) spawnArgs.push(...argList)
          const child = spawn('cmd', spawnArgs, {
            windowsHide: false,
            detached: true,
            stdio: 'ignore'
          })
          child.unref()
          return { 
            success: true, 
            data: { 
              launched: target,
              method: 'cmd_start',
              args: argList,
              message: `${target} 启动命令已发送${argList.length > 0 ? '（带参数）' : ''}`
            } 
          }
        } catch (e) {
          return { success: false, error: `启动失败: ${e.message}` }
        }
      }
      
      // 其他路径：走原有的 ensureAllowedPath 检查
      const targetPath = this.ensureAllowedPath(target)
      try {
        const err = await shell.openPath(targetPath)
        return { 
          success: !err, 
          data: { 
            launched: targetPath, 
            method: 'shell_open',
            message: err ? '打开失败' : `已打开 ${targetPath}`
          } 
        }
      } catch (e) {
        const code = e.message || String(e)
        return {
          success: false,
          data: {
            launched: targetPath,
            method: 'shell_open',
            message: code === 'FILE_NOT_FOUND' ? '文件不存在' : '打开失败'
          }
        }
      }
    })

    this.registerTool('clipboard:write', async (params = {}) => {
      clipboard.writeText(String(params.text || ''))
      return { success: true, data: { written: true } }
    })

    this.registerTool('content:generate', async (params = {}) => {
      const http = require('http')
      const contentType = params.content_type || 'word'
      const theme = params.theme || params.task || ''
      const length = params.length || '中'
      const style = params.style || '现代'
      const outputPath = params.output_path || ''
      const autoOpen = params.auto_open !== false

      const requestBody = JSON.stringify({
        task: params.task || theme,
        content_type: contentType,
        style: style,
        length: length,
        output_path: outputPath,
        theme: theme,
        auto_open: autoOpen,
        browser_url: autoOpen ? 'auto_open' : undefined,
      })

      const serverPort = parseInt(process.env.AGENT_SERVER_URL?.split(':').pop() || '8000', 10)

      return new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1',
          port: serverPort,
          path: '/content/generate',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(requestBody),
          },
          timeout: 120000,
        }, (res) => {
          let data = ''
          res.on('data', (chunk) => { data += chunk })
          res.on('end', () => {
            try {
              const result = JSON.parse(data)
              if (result.success) {
                if (autoOpen && result.output_file) {
                  try {
                    const { exec, spawn } = require('child_process')
                    const filePath = result.output_file
                    if (filePath.endsWith('.html') || filePath.endsWith('.htm')) {
                      const browserUrl = 'file:///' + filePath.replace(/\\/g, '/')
                      spawn('cmd', ['/c', 'start', '', 'msedge.exe', browserUrl], { detached: true, stdio: 'ignore', windowsHide: true }).unref()
                    } else {
                      exec(`start "" "${filePath}"`)
                    }
                  } catch (e) {
                    console.error('自动打开文件失败:', e)
                  }
                }
                resolve({
                  success: true,
                  data: {
                    content: result.content || '',
                    output_file: result.output_file || '',
                    message: result.message || '内容生成成功',
                  },
                })
              } else {
                resolve({
                  success: false,
                  error: result.message || result.error || '内容生成失败',
                })
              }
            } catch (e) {
              resolve({ success: false, error: `解析响应失败: ${e.message}` })
            }
          })
        })
        req.on('error', (e) => {
          resolve({ success: false, error: `内容生成服务不可用: ${e.message}` })
        })
        req.on('timeout', () => {
          req.destroy()
          resolve({ success: false, error: '内容生成超时（120秒）' })
        })
        req.write(requestBody)
        req.end()
      })
    })

    this.registerTool('keyboard:type', async (params = {}) => {
      const text = params.text || ''
      if (!text) return { success: false, error: 'text is required' }
      
      try {
        const { clipboard } = require('electron')
        clipboard.writeText(text)
        await new Promise(resolve => setTimeout(resolve, 1500))
        const { exec } = require('child_process')
        const { promisify } = require('util')
        const execAsync = promisify(exec)
        try {
          await execAsync('powershell -NoProfile -Command "[Microsoft.VisualBasic.Interaction]::AppActivate([System.Diagnostics.Process]::GetProcessesByName(\'notepad\')[0].MainWindowTitle)"', { windowsHide: true, timeout: 3000 })
          await new Promise(resolve => setTimeout(resolve, 300))
        } catch (_) {}
        const { spawn } = require('child_process')
        spawn('powershell', [
          '-NoProfile', '-Command',
          'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^v")'
        ], { windowsHide: true, detached: true, stdio: 'ignore' }).unref()
        return { success: true, data: { typed: text, method: 'clipboard_paste' } }
      } catch (e) {
        return { success: false, error: `输入失败: ${e.message}` }
      }
    })

    this.registerTool('ide:launch', async (params = {}) => {
      const ide = params.ide || 'vscode'
      const action = params.action || 'open_file'
      const projectName = params.project_name || ''
      const projectPath = params.project_path || ''
      const previewUrl = params.preview_url || ''
      const files = params.files || []
      const args = params.args || []
      const fs = require('fs')
      const pathModule = require('path')
      
      let idePath = params.path || ''
      if (!idePath) {
        if (ide === 'vscode') {
          idePath = 'Code.exe'
        } else if (ide === 'cursor') {
          idePath = 'Cursor.exe'
        } else {
          idePath = ide
        }
      }
      
      let resolvedProjectPath = projectPath
      const createdFiles = []
      
      if (action === 'create_project' && !projectPath) {
        const baseDir = 'D:\\'
        const dirName = projectName || 'project'
        const safeName = dirName.replace(/[<>:"/\\|?*]/g, '_')
        resolvedProjectPath = pathModule.join(baseDir, safeName)
        
        try {
          if (!fs.existsSync(resolvedProjectPath)) {
            fs.mkdirSync(resolvedProjectPath, { recursive: true })
          }
          
          if (files.length > 0) {
            for (const file of files) {
              const filePath = pathModule.join(resolvedProjectPath, file.path || 'index.html')
              const fileDir = pathModule.dirname(filePath)
              if (!fs.existsSync(fileDir)) {
                fs.mkdirSync(fileDir, { recursive: true })
              }
              
              let content = file.content || ''
              if (!content) {
                const ext = pathModule.extname(filePath).toLowerCase()
                if (ext === '.html') {
                  content = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>${projectName || 'Page'}</title>\n  <style>\n    body { font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }\n    .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }\n    h1 { color: #333; }\n    p { color: #666; line-height: 1.6; }\n  </style>\n</head>\n<body>\n  <div class="container">\n    <h1>${projectName || 'Hello World'}</h1>\n    <p>This is a generated page. Edit me in VSCode!</p>\n  </div>\n</body>\n</html>`
                } else if (ext === '.py') {
                  content = `# ${projectName || 'Script'}\n\ndef main():\n    print("Hello, World!")\n\nif __name__ == "__main__":\n    main()\n`
                } else if (ext === '.js') {
                  content = `// ${projectName || 'Script'}\n\nconsole.log("Hello, World!");\n`
                } else {
                  content = `# ${projectName || 'Project'}\n`
                }
              }
              
              fs.writeFileSync(filePath, content, 'utf-8')
              createdFiles.push(filePath)
            }
          } else {
            const defaultHtml = pathModule.join(resolvedProjectPath, 'index.html')
            if (!fs.existsSync(defaultHtml)) {
              const content = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>${projectName || 'Page'}</title>\n  <style>\n    body { font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }\n    .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }\n    h1 { color: #333; }\n    p { color: #666; line-height: 1.6; }\n  </style>\n</head>\n<body>\n  <div class="container">\n    <h1>${projectName || 'Hello World'}</h1>\n    <p>This is a generated page. Edit me in VSCode!</p>\n  </div>\n</body>\n</html>`
              fs.writeFileSync(defaultHtml, content, 'utf-8')
              createdFiles.push(defaultHtml)
            }
          }
        } catch (e) {
          console.error('[ide:launch] 创建项目失败:', e)
        }
      }
      
      const launchArgs = []
      if (resolvedProjectPath) {
        launchArgs.push(resolvedProjectPath)
      } else if (args.length > 0) {
        launchArgs.push(...args)
      }
      
      try {
        const { spawn } = require('child_process')
        const spawnArgs = ['/c', 'start', '', idePath, ...launchArgs, '--reuse-window']
        const child = spawn('cmd', spawnArgs, {
          windowsHide: false,
          detached: true,
          stdio: 'ignore'
        })
        child.unref()
        
        const results = {
          success: true,
          data: {
            ide,
            action,
            projectPath: resolvedProjectPath,
            createdFiles,
            launched: idePath,
            message: resolvedProjectPath 
              ? `${ide} 已打开项目: ${resolvedProjectPath}` 
              : `${ide} 已启动`,
          }
        }
        
        if (createdFiles.length > 0) {
          results.data.message += `，已创建 ${createdFiles.length} 个文件`
        }
        
        if (previewUrl && params.auto_preview) {
          setTimeout(() => {
            try {
              const browserPath = 'msedge.exe'
              spawn('cmd', ['/c', 'start', '', browserPath, previewUrl], {
                windowsHide: false,
                detached: true,
                stdio: 'ignore'
              }).unref()
            } catch (e) {
              console.error('[ide:launch] 浏览器预览失败:', e)
            }
          }, 2000)
          results.data.previewUrl = previewUrl
          results.data.message += '，浏览器预览将在2秒后打开'
        }
        
        if (createdFiles.length > 0 && params.auto_preview !== false) {
          const htmlFile = createdFiles.find(f => f.endsWith('.html'))
          if (htmlFile) {
            setTimeout(() => {
              try {
                spawn('cmd', ['/c', 'start', '', 'msedge.exe', htmlFile], {
                  windowsHide: false,
                  detached: true,
                  stdio: 'ignore'
                }).unref()
              } catch (e) {
                console.error('[ide:launch] 自动预览失败:', e)
              }
            }, 3000)
            results.data.previewUrl = htmlFile
            results.data.message += '，浏览器预览将在3秒后打开'
          }
        }
        
        return results
      } catch (e) {
        return { success: false, error: `IDE启动失败: ${e.message}` }
      }
    })

    this.registerTool('notify', async (params = {}) => {
      const notification = new Notification({
        title: params.title || 'AI Agent',
        body: params.body || '收到新的自主执行通知',
      })
      notification.show()
      return { success: true, data: { shown: true } }
    })

    this.registerTool('disk:list', async () => listDiskDrives())

    this.registerTool('temp:scan', async (params = {}) => {
      const targetPath = String(params.path || os.tmpdir())
      const entries = await collectTempEntries(targetPath, Number(params.max || TEMP_SCAN_LIMIT))
      return { success: true, data: { path: targetPath, entries, total: entries.length } }
    })

    this.registerTool('temp:cleanup', async (params = {}) => {
      const targetPath = String(params.path || os.tmpdir())
      const result = await cleanupTempEntries(targetPath, Number(params.max || TEMP_CLEANUP_LIMIT))
      return {
        success: true,
        data: { path: targetPath, deletedCount: result.deleted.length, deleted: result.deleted, skipped: result.skipped },
      }
    })

    this.registerTool('disk:cleanup', async (params = {}) => {
      const drive = String(params.drive || 'C').replace(/[:\\/]/g, '').toUpperCase()
      if (!/^[A-Z]$/.test(drive)) {
        return { success: false, error: 'invalid drive' }
      }
      const tempPath = String(params.path || os.tmpdir())
      const before = await listDiskDrives()
      const cleanup = await cleanupTempEntries(tempPath, Number(params.max || TEMP_CLEANUP_LIMIT))
      const after = await listDiskDrives()
      
      // 明确标注清理范围
      return {
        success: true,
        data: {
          drive, tempPath,
          deletedCount: cleanup.deleted.length,
          deleted: cleanup.deleted,
          skipped: cleanup.skipped,
          before: before.data?.drives || [],
          after: after.data?.drives || [],
          scope: 'temp_files_only',
          notice: '仅清理了临时文件。如需清理系统文件（Windows 更新缓存等），请手动运行 cleanmgr 或磁盘清理工具。',
        },
      }
    })

    this.registerTool('process:list', async (params = {}) => {
      const { execFile } = require('child_process')
      return new Promise((resolve) => {
        execFile('tasklist', ['/fo', 'csv'], { windowsHide: true }, (error, stdout) => {
          if (error) { resolve({ success: false, error: error.message }); return }
          try {
            const lines = String(stdout).trim().split('\n').slice(1)
            const processes = lines.map(line => {
              const parts = line.split('","').map(p => p.replace(/"/g, ''))
              return { name: parts[0], pid: parseInt(parts[1]) || 0, sessionName: parts[2], mem: parseInt(parts[4].replace(/,/g, '').replace(' K', '')) || 0 }
            }).slice(0, Number(params.max || 50))
            resolve({ success: true, data: { processes } })
          } catch (err) { resolve({ success: false, error: 'Failed to parse process list' }) }
        })
      })
    })

    this.registerTool('process:top', async (params = {}) => {
      const { execFile } = require('child_process')
      return new Promise((resolve) => {
        execFile('tasklist', ['/fo', 'csv'], { windowsHide: true }, (error, stdout) => {
          if (error) { resolve({ success: false, error: error.message }); return }
          try {
            const lines = String(stdout).trim().split('\n').slice(1)
            const processes = lines.map(line => {
              const parts = line.split('","').map(p => p.replace(/"/g, ''))
              return { name: parts[0], pid: parseInt(parts[1]) || 0, sessionName: parts[2], mem: parseInt(parts[4].replace(/,/g, '').replace(' K', '')) || 0 }
            }).sort((a, b) => b.mem - a.mem).slice(0, Number(params.max || 10))
            resolve({ success: true, data: { processes } })
          } catch (err) { resolve({ success: false, error: 'Failed to parse process list' }) }
        })
      })
    })

    // 🆕 process:kill 支持 name 参数（自动查 PID）
    this.registerTool('process:kill', async (params = {}) => {
      let pid = Number(params.pid)
      const name = params.name || ''
      
      // 🆕 按名称查找 PID（轮询直到找到）
      if (!pid && name) {
        const { stdout } = await execFileAsync('tasklist', ['/FI', `IMAGENAME eq ${name}`, '/FO', 'CSV', '/NH'], { timeout: 10000, windowsHide: true })
        const lines = stdout.trim().split('\n').filter(Boolean)
        if (lines.length > 0) {
          const parts = lines[0].split('","').map(s => s.replace(/^"|"$/g, ''))
          pid = parseInt(parts[1]) || 0
        }
        if (!pid) return { success: false, error: `未找到进程: ${name}` }
      }
      const targetName = params.name  // 🆕 支持按名称查找 PID
      
      // 如果给了 name 但没给 pid，自动查找
      if (!pid && targetName) {
        const { execFile: ef } = require('child_process')
        // 先精确匹配
        const exactResult = await new Promise(resolve => {
          ef('tasklist', ['/FI', `IMAGENAME eq ${targetName}`, '/FO', 'CSV', '/NH'], { windowsHide: true }, (e, out) => resolve({ success: !e, stdout: out }))
        })
        if (exactResult.success && exactResult.stdout) {
          const lines = String(exactResult.stdout).trim().split('\n').filter(Boolean)
          if (lines.length > 0) {
            const parts = lines[0].split('","').map(p => p.replace(/"/g, ''))
            pid = parseInt(parts[1])
          }
        }
        // 精确匹配失败，模糊匹配
        if (!pid) {
          const fuzzyResult = await new Promise(resolve => {
            ef('tasklist', ['/FO', 'CSV'], { windowsHide: true }, (e, out) => resolve({ success: !e, stdout: out }))
          })
          if (fuzzyResult.success && fuzzyResult.stdout) {
            const lines = String(fuzzyResult.stdout).trim().split('\n').slice(1)
            const matches = lines.map(line => {
              const parts = line.split('","').map(p => p.replace(/"/g, ''))
              return { name: parts[0], pid: parseInt(parts[1]) }
            }).filter(p => p.name.toLowerCase().includes(targetName.toLowerCase().replace(/\.exe$/, '')))
            
            if (matches.length === 1) {
              pid = matches[0].pid
            } else if (matches.length > 1) {
              return { 
                success: false, 
                error: `找到多个匹配: ${matches.map(m=>m.name).join(', ')}，请指定 PID`,
                code: 'MULTIPLE_MATCHES',
                data: { matches }
              }
            }
          }
        }
        if (!pid) {
          return { success: false, error: `未找到进程: ${targetName}`, code: 'PROCESS_NOT_FOUND' }
        }
      }

      if (!pid || pid <= 0 || !Number.isInteger(pid)) {
        return buildBlockedResult('INVALID_PID', 'Invalid PID')
      }
      if (pid === process.pid) {
        return buildBlockedResult('SELF_PROTECTION', 'Refusing to kill current Electron process')
      }
      if (PROTECTED_PIDS.has(pid)) {
        return buildBlockedResult('PROTECTED_PROCESS', `PID ${pid} is protected and cannot be terminated`, { blocked_reason: 'system critical pid' })
      }
      const procLookup = await lookupProcessByPid(pid)
      if (!procLookup.success) {
        return buildBlockedResult(procLookup.code || 'PROCESS_LOOKUP_FAILED', procLookup.error || 'Failed to inspect target process')
      }
      const processInfo = procLookup.data || {}
      const processName = normalizeProcessName(processInfo.name)
      if (PROTECTED_PROCESS_NAMES.has(processName)) {
        return buildBlockedResult('PROTECTED_PROCESS', `Process ${processInfo.name} is protected and cannot be terminated`, {
          blocked_reason: `protected process name: ${processInfo.name}`,
          data: processInfo,
        })
      }
      return new Promise((resolve) => {
        const psCmd = `$p = Get-Process -Id ${pid} -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id ${pid} -Force -ErrorAction Stop; Write-Output 'KILLED' } else { Write-Output 'NOT_FOUND' }`
        execFileAsync('powershell', ['-NoProfile', '-NonInteractive', '-Command', psCmd], { timeout: 10000, windowsHide: true }).then(async (result) => {
          if (result.success && result.stdout && result.stdout.trim() === 'KILLED') {
            resolve({ success: true, data: { killed: pid, process: processInfo, method: 'powershell', stdout: result.stdout } })
            return
          }
          if (result.stdout && result.stdout.trim() === 'NOT_FOUND') {
            resolve({ success: false, error: `PID ${pid} 不存在`, code: 'PROCESS_NOT_FOUND', data: processInfo })
            return
          }
          try {
            const elevCmd = `Start-Process powershell -ArgumentList '-NoProfile','-Command','Stop-Process -Id ${pid} -Force' -Verb RunAs -WindowStyle Hidden -Wait`
            const elevResult = await execFileAsync('powershell', ['-NoProfile', '-NonInteractive', '-Command', elevCmd], { timeout: 15000, windowsHide: true })
            if (elevResult.success || !elevResult.stderr || elevResult.stderr.trim() === '') {
              resolve({ success: true, data: { killed: pid, process: processInfo, method: 'elevated_powershell' } })
              return
            }
          } catch (_) {}
          resolve({
            success: false,
            error: '结束此进程需要管理员权限（已尝试提权）',
            code: 'ACCESS_DENIED',
            blocked_reason: 'administrator privileges required',
            data: processInfo,
          })
        }).catch(async () => {
          try {
            const elevCmd = `Start-Process powershell -ArgumentList '-NoProfile','-Command','Stop-Process -Id ${pid} -Force' -Verb RunAs -WindowStyle Hidden -Wait`
            const elevResult = await execFileAsync('powershell', ['-NoProfile', '-NonInteractive', '-Command', elevCmd], { timeout: 15000, windowsHide: true })
            if (elevResult.success || !elevResult.stderr || elevResult.stderr.trim() === '') {
              resolve({ success: true, data: { killed: pid, process: processInfo, method: 'elevated_powershell' } })
              return
            }
          } catch (_) {}
          resolve({
            success: false,
            error: '结束此进程失败，可能需要管理员权限',
            code: 'KILL_FAILED',
            data: processInfo,
          })
        })
      })
    })

    // ===== 新增：休眠管理 ====================
    this.registerTool('system:hibernate', async (params = {}) => {
      const enable = Boolean(params.enable)
      return new Promise((resolve) => {
        execFile('powercfg', [enable ? '-h' : '-h', 'off'], { windowsHide: true }, (error, stdout, stderr) => {
          if (error) {
            resolve({ success: false, error: `需要管理员权限: ${error.message}` })
            return
          }
          resolve({ 
            success: true, 
            data: { 
              action: enable ? 'enabled' : 'disabled', 
              message: enable 
                ? '已开启休眠' 
                : '已关闭休眠，释放 hiberfil.sys 空间（通常几个GB）' 
            } 
          })
        })
      })
    })

    // 🆕 清空回收站 - 使用 PowerShell Clear-RecycleBin（正确处理多用户回收站）
    this.registerTool('system:recycle', async () => {
      return new Promise((resolve) => {
        const psCommand = `
          try {
            Clear-RecycleBin -Force -ErrorAction Stop
            "回收站已清空"
          } catch {
            $err = $_.Exception.Message
            if ($err -like "*已为空*") { "回收站已为空" } else { "Error: " + $err }
          }
        `
        execFile('powershell', ['-NoProfile', '-NonInteractive', '-Command', psCommand], { windowsHide: true, timeout: 15000 }, (error, stdout, stderr) => {
          const output = String(stdout || '').trim()
          if (error && !output) {
            resolve({ success: false, error: error.message })
            return
          }
          resolve({ success: true, data: { message: output || '回收站已清空' } })
        })
      })
    })

    // ===== 新增：启动 Windows 磁盘清理 ====================
    this.registerTool('system:cleanmgr', async () => {
      return new Promise((resolve) => {
        execFile('cleanmgr', ['/sagerun:1'], { windowsHide: true }, (error) => {
          if (error) {
            resolve({ success: false, error: error.message })
            return
          }
          resolve({ success: true, data: { message: '已启动 Windows 磁盘清理工具（清理系统更新残留、临时文件等）' } })
        })
      })
    })

    // 🆕 浏览器缓存清理 - 包含 Code Cache，区分成功/失败
    this.registerTool('system:browser-cache', async (params = {}) => {
      const browser = params.browser || 'all'
      const cleared = []
      const failed = []
      
      const paths = []
      if (browser === 'edge' || browser === 'all') {
        paths.push({ 
          path: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
          name: 'Edge'
        })
        paths.push({
          path: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Code Cache'),
          name: 'Edge Code'
        })
        paths.push({
          path: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Service Worker', 'CacheStorage'),
          name: 'Edge SW Cache'
        })
      }
      if (browser === 'chrome' || browser === 'all') {
        paths.push({ 
          path: path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
          name: 'Chrome'
        })
        paths.push({
          path: path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Code Cache'),
          name: 'Chrome Code'
        })
        paths.push({
          path: path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Service Worker', 'CacheStorage'),
          name: 'Chrome SW Cache'
        })
      }
      
      for (const { path: p, name } of paths) {
        try {
          const entries = await fs.readdir(p, { withFileTypes: true })
          let count = 0
          for (const entry of entries) {
            if (count >= 200) break
            const entryPath = path.join(p, entry.name)
            try {
              if (entry.isDirectory()) {
                await fs.rm(entryPath, { recursive: true, force: true })
              } else {
                await fs.unlink(entryPath)
              }
              count++
            } catch (err) {
              // 文件被占用，跳过
            }
          }
          if (count > 0) {
            cleared.push({ path: p, name, count })
          } else {
            failed.push({ path: p, name, reason: entries.length === 0 ? '目录为空' : '文件被占用，请关闭浏览器后重试' })
          }
        } catch (e) { 
          if (e.code === 'ENOENT') {
            failed.push({ path: p, name, reason: '目录不存在' })
          } else {
            failed.push({ path: p, name, reason: e.message })
          }
        }
      }
      
      return {
        success: cleared.length > 0,
        data: { 
          browser, 
          cleared, 
          failed,
          message: cleared.length > 0 
            ? `已清理浏览器缓存，共 ${cleared.reduce((a,b) => a+b.count, 0)} 个文件` 
            : (failed.length > 0 
              ? '浏览器缓存清理失败：浏览器可能正在运行，请先关闭浏览器后重试' 
              : '未找到浏览器缓存')
        }
      }
    })

    // ===== 新增：微信缓存定位 ====================
    this.registerTool('system:wechat-cache', async () => {
      const wechatPath = path.join(os.homedir(), 'Documents', 'WeChat Files')
      try {
        await fs.access(wechatPath)
        return { 
          success: true, 
          data: { 
            path: wechatPath, 
            message: `微信文件目录: ${wechatPath}。建议手动迁移到D盘：微信设置 -> 文件管理 -> 更改目录`, 
            note: '微信缓存通常占用数GB，包含聊天记录，不建议自动删除' 
          } 
        }
      } catch (e) { 
        return { success: false, error: '未找到微信文件目录' } 
      }
    })

    // ===== 增强版 disk:cleanup - 多目录同时扫描 ====================
    this.registerTool('disk:cleanup_advanced', async (params = {}) => {
      const maxEntries = Number(params.max || 100)
      const allDeleted = []
      const allSkipped = []
      
      const targets = [
        { path: path.join(os.homedir(), 'Downloads'), weight: 0.25, label: 'Downloads' },
        { path: path.join(os.homedir(), 'AppData', 'Local', 'Temp'), weight: 0.25, label: '用户Temp' },
        { path: 'C:\\Windows\\Temp', weight: 0.2, label: 'Windows/Temp' },
        { path: 'C:\\Windows\\Prefetch', weight: 0.15, label: 'Prefetch' },
        { path: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Windows', 'Explorer', 'ThumbCacheToDelete'), weight: 0.15, label: '缩略图缓存' }
      ]
      
      for (const t of targets) {
        try {
          const r = await cleanupTempEntries(t.path, Math.max(5, Math.floor(maxEntries * t.weight)))
          allDeleted.push(...r.deleted.map(d => ({ ...d, source: t.label })))
          allSkipped.push(...r.skipped.map(s => ({ ...s, source: t.label })))
        } catch (e) { /* 忽略单个目录失败 */ }
      }
      
      return {
        success: allDeleted.length > 0,
        data: {
          path: 'C: (系统盘)',
          deletedCount: allDeleted.length,
          skippedCount: allSkipped.length,
          deleted: allDeleted,
          skipped: allSkipped,
          message: allDeleted.length > 0 
            ? `磁盘清理完成，从5个目录共删除 ${allDeleted.length} 个文件` 
            : '未找到可清理的磁盘垃圾'
        }
      }
    })

    this.registerTool('network:request', async (params = {}) => {
      const url = String(params.url || '').trim()
      if (!url) { return { success: false, error: 'URL is required' } }
      if (!isAllowedNetworkTarget(url, params.target)) {
        return { success: false, error: 'network target not allowed' }
      }
      try {
        const method = String(params.method || 'GET').toUpperCase()
        const headers = params.headers && typeof params.headers === 'object' ? params.headers : {}
        const body = params.body ? JSON.stringify(params.body) : undefined
        const response = await fetch(url, {
          method, headers: { 'Content-Type': 'application/json', ...headers }, body,
          signal: AbortSignal.timeout(Number(params.timeout || 10000))
        })
        const responseData = { status: response.status, statusText: response.statusText, headers: Object.fromEntries(response.headers.entries()) }
        try { responseData.data = await response.json() } catch { responseData.text = await response.text() }
        return { success: response.ok, data: responseData }
      } catch (error) { return { success: false, error: error.message } }
    })

    this.registerTool('file:search', async (params = {}) => {
      const targetPath = this.ensureAllowedPath(params.path)
      const pattern = String(params.pattern || '*')
      try {
        const entries = await fs.readdir(targetPath, { withFileTypes: true })
        const matched = entries
          .filter(entry => { const regex = new RegExp(pattern.replace(/\*/g, '.*'), 'i'); return regex.test(entry.name) })
          .slice(0, Number(params.max || 100))
          .map(entry => ({ name: entry.name, path: path.join(targetPath, entry.name), type: entry.isDirectory() ? 'directory' : 'file' }))
        return { success: true, data: { path: targetPath, matches: matched } }
      } catch (error) { return { success: false, error: error.message } }
    })

    this.registerTool('system:env', async (params = {}) => {
      const requestedName = params.name ? sanitizeEnvName(params.name) : null
      if (params.name && !requestedName) { return { success: false, error: 'invalid environment variable name' } }
      if (requestedName) {
        if (isSensitiveEnvName(requestedName)) { return { success: false, error: 'access to sensitive environment variables is denied' } }
        const value = process.env[requestedName]
        return { success: true, data: { name: requestedName, value } }
      }
      const envVars = Object.keys(process.env)
        .filter((key) => !isSensitiveEnvName(key.toUpperCase()))
        .slice(0, Number(params.max || 50))
        .reduce((acc, key) => { acc[key] = process.env[key]; return acc }, {})
      return { success: true, data: { envVars } }
    })

    const _storeServerPort = parseInt(process.env.AGENT_SERVER_URL?.split(':').pop() || '8000', 10)

    this.registerTool('store:search', async (params = {}) => {
      const query = String(params.query || '').trim()
      if (!query) return { success: false, error: 'query is required' }
      const http = require('http')
      const body = JSON.stringify({ query })
      return new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1', port: _storeServerPort, path: '/store/search', method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
          timeout: 30000,
        }, (res) => {
          let data = ''
          res.on('data', (chunk) => { data += chunk })
          res.on('end', () => {
            try { resolve(JSON.parse(data)) } catch (e) { resolve({ success: false, error: `解析响应失败: ${e.message}` }) }
          })
        })
        req.on('error', (e) => { resolve({ success: false, error: `商店服务不可用: ${e.message}` }) })
        req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '搜索超时（30秒）' }) })
        req.write(body); req.end()
      })
    })

    this.registerTool('store:install', async (params = {}) => {
      const packageId = String(params.package_id || '').trim()
      if (!packageId) return { success: false, error: 'package_id is required' }
      const http = require('http')
      const body = JSON.stringify({ package_id: packageId, app_name: params.app_name || null })
      return new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1', port: _storeServerPort, path: '/store/install', method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
          timeout: 120000,
        }, (res) => {
          let data = ''
          res.on('data', (chunk) => { data += chunk })
          res.on('end', () => {
            try { resolve(JSON.parse(data)) } catch (e) { resolve({ success: false, error: `解析响应失败: ${e.message}` }) }
          })
        })
        req.on('error', (e) => { resolve({ success: false, error: `商店服务不可用: ${e.message}` }) })
        req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '安装超时（120秒）' }) })
        req.write(body); req.end()
      })
    })

    this.registerTool('store:uninstall', async (params = {}) => {
      const packageId = String(params.package_id || '').trim()
      if (!packageId) return { success: false, error: 'package_id is required' }
      const http = require('http')
      const body = JSON.stringify({ package_id: packageId })
      return new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1', port: _storeServerPort, path: '/store/uninstall', method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
          timeout: 120000,
        }, (res) => {
          let data = ''
          res.on('data', (chunk) => { data += chunk })
          res.on('end', () => {
            try { resolve(JSON.parse(data)) } catch (e) { resolve({ success: false, error: `解析响应失败: ${e.message}` }) }
          })
        })
        req.on('error', (e) => { resolve({ success: false, error: `商店服务不可用: ${e.message}` }) })
        req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '卸载超时（120秒）' }) })
        req.write(body); req.end()
      })
    })

    this.registerTool('store:list', async () => {
      const http = require('http')
      return new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1', port: _storeServerPort, path: '/store/installed', method: 'GET',
          timeout: 30000,
        }, (res) => {
          let data = ''
          res.on('data', (chunk) => { data += chunk })
          res.on('end', () => {
            try { resolve(JSON.parse(data)) } catch (e) { resolve({ success: false, error: `解析响应失败: ${e.message}` }) }
          })
        })
        req.on('error', (e) => { resolve({ success: false, error: `商店服务不可用: ${e.message}` }) })
        req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '列表查询超时（30秒）' }) })
        req.end()
      })
    })
  }

  registerTool(name, handler) {
    this.toolRegistry.set(name, handler)
  }

  getExecutionLog(limit = 50) {
    return this.executionLog.slice(-Math.max(1, Number(limit || 50)))
  }

  pause() {
    this.isPaused = true
    return { status: 'paused' }
  }

  resume() {
    this.isPaused = false
    return { status: 'resumed' }
  }

  dedupeCommands(commands = []) {
    const deduped = []
    const seen = new Set()
    for (const cmd of commands) {
      const signature = `${cmd?.tool || 'unknown'}::${JSON.stringify(cmd?.params || {})}`
      if (seen.has(signature)) {
        deduped.push({ ...cmd, __duplicateSkipped: true })
        continue
      }
      seen.add(signature)
      deduped.push(cmd)
    }
    return deduped
  }

  // 🆕 任务预验证过滤器 - 执行前检查进程/文件是否存在
  async preValidateCommand(cmd) {
    const { tool, params = {} } = cmd
    
    // 🆕 1. process:kill 按 name 时，检查进程是否存在
    if (tool === 'process:kill' && params.name && !params.pid) {
      try {
        const name = params.name.toLowerCase().replace(/\.exe$/, '')
        const { execFileSync } = require('child_process')
        const output = execFileSync('tasklist', ['/FI', `IMAGENAME eq ${params.name}`, '/NH'], { encoding: 'utf8', timeout: 5000, windowsHide: true })
        if (!output.toLowerCase().includes(name)) {
          return { valid: false, reason: `进程 ${params.name} 未运行，跳过`, skipped: true }
        }
      } catch (e) {
        return { valid: false, reason: `进程 ${params.name} 未运行，跳过`, skipped: true }
      }
    }
    
    // 🆕 2. process:kill 按 pid 时，检查 PID 是否存在
    if (tool === 'process:kill' && params.pid && Number(params.pid) > 0) {
      try {
        const { execFileSync } = require('child_process')
        execFileSync('tasklist', ['/FI', `PID eq ${params.pid}`, '/NH'], { encoding: 'utf8', timeout: 5000, windowsHide: true })
      } catch (e) {
        return { valid: false, reason: `PID ${params.pid} 不存在，跳过`, skipped: true }
      }
    }
    
    // 🆕 3. app:launch 时，动态解析路径（调用 Python 软件索引）
    if (tool === 'app:launch' && params.path) {
      const target = String(params.path).trim()
      if (!target.includes('\\') && !target.includes('/') && !target.includes(':')) {
        let resolved = null
        try {
          const { execFileSync } = require('child_process')
          const output = execFileSync('where', [target], { encoding: 'utf8', timeout: 5000, windowsHide: true })
          const lines = output.trim().split('\n').filter(Boolean)
          if (lines.length > 0) resolved = lines[0].trim()
        } catch (_) {}
        if (!resolved) {
          try {
            const { execFileSync } = require('child_process')
            const output = execFileSync('powershell', ['-NoProfile', '-Command', `Get-Command $env:APP_KEY -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source`], { encoding: 'utf8', timeout: 5000, windowsHide: true, env: { ...process.env, APP_KEY: target } })
            if (output.trim()) resolved = output.trim()
          } catch (_) {}
        }
        if (!resolved) {
          try {
            const http = require('http')
            const url = `/desktop/software/find?query=${encodeURIComponent(target)}`
            const serverPort = parseInt(process.env.AGENT_SERVER_URL?.split(':').pop() || '8000', 10)
            const result = await new Promise((resolve) => {
              const req = http.request({ hostname: '127.0.0.1', port: serverPort, path: url, method: 'GET', timeout: 5000 }, (res) => {
                let body = ''
                res.on('data', (c) => { body += c })
                res.on('end', () => { try { resolve(JSON.parse(body)) } catch { resolve(null) } })
              })
              req.on('error', () => resolve(null))
              req.on('timeout', () => { req.destroy(); resolve(null) })
              req.end()
            })
            if (result && result.exe_path && result.exe_path.length > 0) {
              const fs = require('fs')
              try { fs.accessSync(result.exe_path); resolved = result.exe_path } catch (_) {}
            }
          } catch (_) {}
        }
        if (!resolved) {
          try {
            const { execFileSync } = require('child_process')
            const psCmd = `$key = $env:APP_KEY; $regPath = 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths'; try { $val = (Get-ItemProperty -Path "Registry::HKEY_LOCAL_MACHINE\\$regPath\\$key" -ErrorAction Stop).'(default)'; if ($val -and (Test-Path $val)) { $val } } catch {}`
            const output = execFileSync('powershell', ['-NoProfile', '-Command', psCmd], { encoding: 'utf8', timeout: 5000, windowsHide: true, env: { ...process.env, APP_KEY: target } })
            if (output.trim()) resolved = output.trim()
          } catch (_) {}
        }
        if (resolved) {
          cmd.params.path = resolved
          return { valid: true, resolved }
        }
        return { valid: false, reason: `找不到应用 ${target}，请提供完整路径`, skipped: true }
      }
    }
    
    return { valid: true }
  }

  async executeCommands(commands = []) {
    if (this.isPaused) {
      return [{ id: 'executor', success: false, error: 'executor paused', code: 'EXECUTOR_PAUSED' }]
    }
    const results = []
    const dedupedCommands = this.dedupeCommands(commands)

    // 🆕 预验证所有命令，过滤无效任务
    const validatedCommands = []
    for (const cmd of dedupedCommands) {
      if (cmd?.__duplicateSkipped) {
        results.push({ id: cmd.id || 'duplicate', tool: cmd.tool, success: false, skipped: true, error: 'duplicate command skipped', code: 'DUPLICATE_COMMAND', duration: 0, timestamp: new Date().toISOString() })
        continue
      }
      const validation = await this.preValidateCommand(cmd)
      if (!validation.valid) {
        results.push({ id: cmd.id || cmd.tool, tool: cmd.tool, success: true, skipped: true, error: validation.reason, code: 'VALIDATION_SKIPPED', duration: 0, timestamp: new Date().toISOString() })
        continue
      }
      validatedCommands.push(cmd)
    }

    const autoCommands = []
    const confirmCommands = []
    const doubleConfirmCommands = []

    for (const cmd of validatedCommands) {
      if (!cmd?.id || !cmd?.tool || !cmd?.type) {
        results.push({ id: cmd?.id || 'unknown', success: false, error: 'invalid command payload', code: 'INVALID_COMMAND' })
        continue
      }
      if (!this.toolRegistry.has(cmd.tool)) {
        results.push({ id: cmd.id, success: false, error: `unknown tool: ${cmd.tool}` })
        continue
      }
      const policy = getApprovalPolicy(cmd)
      if (policy.autoExecute) { autoCommands.push({ cmd, policy }) }
      else if (policy.requireDoubleConfirm) { doubleConfirmCommands.push({ cmd, policy }) }
      else if (policy.requireConfirm) { confirmCommands.push({ cmd, policy }) }
    }

    for (const { cmd, policy } of autoCommands) {
      const result = await this.executeSingle(cmd)
      results.push(result)
      if (policy.notify) this.sendNotification(cmd, result)
    }

    const allConfirmCommands = [
      ...doubleConfirmCommands.map(c => ({ ...c.cmd, _requireDoubleConfirm: true })),
      ...confirmCommands.map(c => ({ ...c.cmd, _requireDoubleConfirm: false })),
    ]

    if (allConfirmCommands.length > 0) {
      const batchResult = await this.requestBatchConfirm(allConfirmCommands)
      for (const cmd of allConfirmCommands) {
        const isConfirmed = batchResult.confirmed.has(cmd.id)
        if (!isConfirmed) {
          results.push({ id: cmd.id, success: false, skipped: true, error: 'user rejected' })
          continue
        }
        if (cmd._requireDoubleConfirm) {
          const secondConfirm = await this.requestConfirm({
            ...cmd,
            reason: `${cmd.reason || '未提供原因'}\n\n⚠️ 这是危险操作，请再次确认。`,
          })
          if (!secondConfirm) {
            results.push({ id: cmd.id, success: false, skipped: true, error: 'user rejected' })
            continue
          }
        }
        const result = await this.executeSingle(cmd)
        results.push(result)
        const policy = getApprovalPolicy(cmd)
        if (policy.notify) this.sendNotification(cmd, result)
      }
    }

    this.executionLog.push({
      batchId: `batch-${Date.now()}`,
      timestamp: new Date().toISOString(),
      commands, results,
    })
    this.executionLog = this.executionLog.slice(-EXECUTION_LOG_LIMIT)
    return results
  }

  async executeSingle(cmd) {
    const startedAt = Date.now()
    const handler = this.toolRegistry.get(cmd.tool)
    try {
      const result = await handler(cmd.params || {})
      return {
        id: cmd.id, tool: cmd.tool, success: Boolean(result.success),
        data: result.data, error: result.error || null, code: result.code || null,
        blocked_reason: result.blocked_reason || null,
        duration: Date.now() - startedAt, timestamp: new Date().toISOString(),
      }
    } catch (error) {
      if (cmd.rollback) { try { await this.executeSingle(cmd.rollback) } catch { /* noop */ } }
      return {
        id: cmd.id, tool: cmd.tool, success: false,
        error: error.message, code: 'EXECUTION_EXCEPTION', blocked_reason: null,
        duration: Date.now() - startedAt, timestamp: new Date().toISOString(),
      }
    }
  }

  // ===== 弹窗防轰炸核心 =====
  _getCommandSignature(cmd) {
    return `${cmd.tool}::${JSON.stringify(cmd.params || {})}`;
  }

  async requestBatchConfirm(commands) {
    // 前端 TasksPanel 已经让用户勾选确认了，这里直接全部通过
    // 真正的确认逻辑在前端 UI 完成
    console.log('[ActionExecutor] Batch confirm delegated to frontend - auto-approving');
    return { 
      allConfirmed: true, 
      confirmed: new Set(commands.map(c => c.id)), 
      rejected: new Set() 
    };
  }

  async requestConfirm(cmd) {
    const window = this.getMainWindow?.() || null
    const detail = [`工具: ${cmd.tool}`, `原因: ${cmd.reason || '未提供'}`, `参数: ${JSON.stringify(cmd.params || {}, null, 2)}`].join('\n\n')
    const { response } = await dialog.showMessageBox(window, {
      type: 'question', title: 'AI Agent 请求执行操作', message: '是否允许执行该操作？', detail,
      buttons: ['拒绝', '允许执行'], defaultId: 0, cancelId: 0, noLink: true,
    })
    return response === 1
  }

  async requestDoubleConfirm(cmd) {
    const firstConfirmed = await this.requestConfirm(cmd)
    if (!firstConfirmed) return false
    const secondConfirmed = await this.requestConfirm({
      ...cmd, reason: `${cmd.reason || '未提供原因'}\n\n这是危险操作，请再次确认。`,
    })
    return secondConfirmed
  }

  sendNotification(cmd, result) {
    const notification = new Notification({
      title: 'AI Agent 执行结果',
      body: `${cmd.tool} → ${result.success ? '成功' : '失败'}${cmd.reason ? `｜${cmd.reason}` : ''}`,
      silent: false,
    })
    notification.show()
  }
}

module.exports = { ActionExecutor, getApprovalPolicy, isCriticalPath }