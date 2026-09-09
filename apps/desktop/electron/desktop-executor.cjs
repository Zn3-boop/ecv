const { exec, spawn, execFile } = require('child_process')
const { promisify } = require('util')
const { shell } = require('electron')
const http = require('http')
const path = require('path')
const os = require('os')

const execAsync = promisify(exec)
const execFileAsync = promisify(execFile)

// ========== 🆕 进程白名单配置 ==========
const PROCESS_WHITELIST = {
  // 系统核心 —— 绝对保护
  system: ['explorer.exe', 'svchost.exe', 'csrss.exe', 'services.exe', 'wininit.exe', 'winlogon.exe', 
           'lsass.exe', 'smss.exe', 'dwm.exe', 'conhost.exe', 'taskhostw.exe', 'fontdrvhost.exe',
           'searchindexer.exe', 'searchhost.exe', 'RuntimeBroker.exe', 'ctfmon.exe'],
  // 用户工作区 —— 保护常用办公/开发
  work: ['Code.exe', 'chrome.exe', 'msedge.exe', 'firefox.exe', 'WeChat.exe', 'DingTalk.exe',
         'WXWork.exe', 'Feishu.exe', 'Slack.exe', 'Discord.exe', 'Teams.exe', 'QQ.exe',
         'Notion.exe', 'CapCut.exe', 'cloudmusic.exe', 'QQMusic.exe', 'Spotify.exe',
         'WINWORD.EXE', 'EXCEL.EXE', 'POWERPNT.EXE', 'AcroRd32.exe', 'FoxitReader.exe',
         'Photoshop.exe', 'Illustrator.exe', 'Figma.exe', 'Blender.exe'],
  // 语音服务自身 —— 防止自杀
  self: ['aits.exe', 'electron.exe', 'python.exe', 'node.exe', 'java.exe', 'javaw.exe']
}

/**
 * 检查进程是否在白名单中
 * @param {string} processName - 进程名
 * @returns {boolean} 是否受保护
 */
function isProcessProtected(processName) {
  const lowerName = processName.toLowerCase()
  for (const tier of Object.values(PROCESS_WHITELIST)) {
    if (tier.some(p => p.toLowerCase() === lowerName)) {
      return true
    }
  }
  return false
}

/**
 * 过滤可安全结束的进程
 * @param {Array} processes - 进程列表
 * @param {Object} options - 过滤选项
 * @returns {Array} 可结束的进程
 */
function filterKillableProcesses(processes, options = {}) {
  const { minCpu = 5, minMemoryMB = 100, maxCount = 5 } = options
  return processes
    .filter(p => !isProcessProtected(p.name))
    .filter(p => p.cpu > minCpu || p.memory > minMemoryMB)
    .slice(0, maxCount)
}

/**
 * 桌面工具执行器 - 通过 HTTP API 暴露给后端 Python 调用
 */
const DesktopTools = {
  /**
   * 启动应用程序
   * @param {Object} params - 参数对象
   * @param {string} params.path - 应用程序路径或名称，如 WeChat.exe、msedge.exe
   */
  async 'app:launch'({ path: appPath, args: appArgs = [], url: targetUrl = '' }) {
    if (!appPath) {
      return { ok: false, error: 'path 参数缺失' }
    }
    
    try {
      // 收集所有参数
      const params = []
      
      // 处理 URL 协议（如 baidu://, chrome://, etc.）
      if (targetUrl) {
        // 直接打开 URL
        spawn('cmd', ['/c', 'start', '', targetUrl], { detached: true, stdio: 'ignore', windowsHide: true })
        return { ok: true, type: 'url', detail: targetUrl, message: `正在打开 ${targetUrl}` }
      }
      
      // 如果是 exe 文件
      if (appPath.match(/\.exe$/i)) {
        // 有额外参数时，使用完整命令
        if (appArgs && appArgs.length > 0) {
          const fullCmd = `"${appPath}" ${appArgs.join(' ')}`
          spawn('cmd', ['/c', 'start', '', '""', appPath, ...appArgs], { detached: true, stdio: 'ignore', windowsHide: true })
          return { ok: true, type: 'app_with_args', detail: appPath, args: appArgs, message: `正在启动 ${appPath} ${appArgs.join(' ')}` }
        }
        spawn('cmd', ['/c', 'start', '', appPath], { detached: true, stdio: 'ignore', windowsHide: true })
        return { ok: true, type: 'app', detail: appPath, message: `正在启动 ${appPath}` }
      }
      
      // 如果是特殊路径（如 ms-settings:）或URI
      if (appPath.includes(':')) {
        // 使用 shell.openExternal 或 cmd 打开 URI
        const { shell } = require('electron')
        try {
          shell.openExternal(appPath)
          return { ok: true, type: 'uri', detail: appPath, message: `正在打开 ${appPath}` }
        } catch (e) {
          // 降级到命令行方式
          require('child_process').exec(`start "" "${appPath}"`, { windowsHide: true })
          return { ok: true, type: 'uri', detail: appPath, message: `正在打开 ${appPath}` }
        }
      }
      
      // 尝试作为命令直接执行
      spawn('cmd', ['/c', 'start', '', appPath], { detached: true, stdio: 'ignore', windowsHide: true })
      return { ok: true, type: 'command', detail: appPath }
    } catch (e) {
      return { ok: false, error: `无法启动应用: ${e.message}` }
    }
  },

  /**
   * 打开应用、文件、文件夹或网址
   */
  async open({ target }) {
    if (!target) {
      return { ok: false, error: 'target 参数缺失' }
    }

    // URL 链接
    if (target.startsWith('http://') || target.startsWith('https://')) {
      try {
        await shell.openExternal(target)
        return { ok: true, type: 'url', detail: target }
      } catch (e) {
        return { ok: false, error: `无法打开链接: ${e.message}` }
      }
    }

    // Windows 快捷方式或可执行文件
    if (target.match(/\.(exe|lnk|bat|cmd|ps1)$/i)) {
      try {
        spawn('cmd', ['/c', 'start', '', target], { detached: true, stdio: 'ignore', windowsHide: true })
        return { ok: true, type: 'app', detail: target }
      } catch (e) {
        return { ok: false, error: `无法启动应用: ${e.message}` }
      }
    }

    // 文件或文件夹
    try {
      const result = await shell.openPath(target)
      if (result === 'SUCCESS') {
        return { ok: true, type: 'path', detail: target }
      }
      return { ok: false, error: '无法打开该文件', detail: target }
    } catch (e) {
      const code = e.message || String(e)
      if (code === 'FILE_NOT_FOUND') {
        return { ok: false, error: '文件不存在', detail: target }
      }
      return { ok: false, error: '无法打开该文件', detail: target }
    }
  },

  /**
   * 执行系统命令
   */
  async shell({ command, args = [] }) {
    if (!command) {
      return { ok: false, error: 'command 参数缺失' }
    }

    const fullCmd = `${command} ${args.join(' ')}`
    
    // 危险命令黑名单
    const blacklist = [
      'rm -rf /',
      'format',
      'del /f /s /q c:\\',
      'rd /s /q c:',
      'mkfs',
      'fdisk',
    ]
    
    if (blacklist.some(b => fullCmd.toLowerCase().includes(b))) {
      return { ok: false, error: '危险命令被拦截', blocked: true }
    }

    try {
      const { stdout, stderr } = await execAsync(fullCmd, { 
        timeout: 30000, 
        windowsHide: true,
        maxBuffer: 1024 * 1024  // 1MB buffer
      })
      return { 
        ok: true, 
        stdout: stdout.slice(0, 2000), 
        stderr: stderr.slice(0, 500) 
      }
    } catch (e) {
      return { 
        ok: false, 
        error: e.message, 
        stdout: e.stdout?.slice(0, 1000) || '', 
        stderr: e.stderr?.slice(0, 500) || '' 
      }
    }
  },

  /**
   * 系统控制：音量、静音、睡眠、关机等
   */
  async systemControl({ action, value }) {
    const platform = process.platform
    
    if (platform !== 'win32') {
      return { ok: false, error: '暂只支持 Windows 系统控制' }
    }

    // 危险操作返回确认请求（后端会处理弹窗）
    if (['shutdown', 'sleep', 'reboot'].includes(action)) {
      return {
        ok: false,
        confirm_required: true,
        action,
        message: `即将执行 ${action === 'shutdown' ? '关机' : action === 'sleep' ? '睡眠' : '重启'}，请确认`,
      }
    }

    try {
      switch (action) {
        case 'volume_up':
          // 使用 PowerShell 调高音量
          await execAsync(
            `powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys([char]175)"`,
            { windowsHide: true }
          )
          return { ok: true, result: '音量已增大' }
          
        case 'volume_down':
          await execAsync(
            `powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"`,
            { windowsHide: true }
          )
          return { ok: true, result: '音量已减小' }
          
        case 'mute':
          await execAsync(
            `powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"`,
            { windowsHide: true }
          )
          return { ok: true, result: '已静音' }
          
        case 'brightness_up':
          return { ok: true, result: '亮度调节需要显示器支持' }
          
        case 'brightness_down':
          return { ok: true, result: '亮度调节需要显示器支持' }
          
        default:
          return { ok: false, error: `不支持的操作: ${action}` }
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 搜索本地文件
   */
  async searchFiles({ keyword, dir }) {
    const searchDir = dir || os.homedir()
    
    if (!keyword) {
      return { ok: false, error: 'keyword 参数缺失' }
    }

    const platform = process.platform
    
    try {
      let cmd
      let parseOutput
      
      if (platform === 'win32') {
        cmd = `powershell -Command "Get-ChildItem -Path '${searchDir}' -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*${keyword}*' } | Select-Object -First 10 FullName,Name,Length | ConvertTo-Json"`
        parseOutput = (stdout) => {
          if (!stdout.trim()) return []
          try {
            const parsed = JSON.parse(stdout)
            const items = Array.isArray(parsed) ? parsed : [parsed]
            return items.map(item => ({
              name: item.Name || path.basename(item.FullName || ''),
              path: item.FullName || '',
              size: item.Length || 0
            }))
          } catch {
            return []
          }
        }
      } else {
        cmd = `find "${searchDir}" -name "*${keyword}*" -maxdepth 3 -type f 2>/dev/null | head -10`
        parseOutput = (stdout) => {
          return stdout.split('\n')
            .filter(Boolean)
            .slice(0, 10)
            .map(line => ({
              name: path.basename(line.trim()),
              path: line.trim()
            }))
        }
      }
      
      const { stdout } = await execAsync(cmd, { timeout: 15000, windowsHide: true })
      const files = parseOutput(stdout)
      
      return { ok: true, count: files.length, files }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 获取系统信息（CPU、内存、磁盘）
   */
  async getSystemInfo() {
    const platform = process.platform
    
    try {
      if (platform === 'win32') {
        const [{ stdout: cpu }, { stdout: mem }, { stdout: disk }] = await Promise.all([
          execAsync('wmic cpu get loadpercentage /value', { windowsHide: true }),
          execAsync('wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value', { windowsHide: true }),
          execAsync('wmic logicaldisk get size,freespace,caption /value', { windowsHide: true }),
        ])
        
        // 解析 CPU 使用率
        let cpuUsage = 'N/A'
        const cpuMatch = cpu.match(/LoadPercentage=(\d+)/)
        if (cpuMatch) {
          cpuUsage = `${cpuMatch[1]}%`
        }
        
        // 解析内存
        let memInfo = { total: 0, free: 0, used: 0, percent: 0 }
        const memMatch = mem.match(/TotalVisibleMemorySize=(\d+).*?FreePhysicalMemory=(\d+)/s)
        if (memMatch) {
          const total = parseInt(memMatch[1]) || 0
          const free = parseInt(memMatch[2]) || 0
          const used = total - free
          memInfo = {
            total: Math.round(total / 1024),
            free: Math.round(free / 1024),
            used: Math.round(used / 1024),
            percent: Math.round((used / total) * 100)
          }
        }
        
        // 解析磁盘
        const diskInfos = []
        const diskLines = disk.split('\n').filter(l => l.includes('='))
        for (const line of diskLines) {
          const captionMatch = line.match(/Caption=([A-Z]:)/)
          const freeMatch = line.match(/FreeSpace=(\d+)/)
          const sizeMatch = line.match(/Size=(\d+)/)
          
          if (captionMatch && freeMatch && sizeMatch) {
            const total = Math.round(parseInt(sizeMatch[1]) / (1024 * 1024 * 1024) * 100) / 100
            const free = Math.round(parseInt(freeMatch[1]) / (1024 * 1024 * 1024) * 100) / 100
            diskInfos.push({
              drive: captionMatch[1],
              total: `${total} GB`,
              free: `${free} GB`,
              used: `${(total - free).toFixed(2)} GB`
            })
          }
        }
        
        return {
          ok: true,
          platform: 'windows',
          cpu: cpuUsage,
          memory: memInfo,
          disk: diskInfos
        }
      }
      
      // macOS / Linux
      return { 
        ok: true, 
        platform,
        note: '非 Windows 系统，信息有限' 
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 磁盘清理扫描
   */
  async diskCleanup({ max = 50 } = {}) {
    try {
      const tempDir = os.tmpdir()
      const { stdout } = await execAsync(
        `powershell -Command "Get-ChildItem '${tempDir}' -File -ErrorAction SilentlyContinue | Select-Object -First ${max} Name,Length,LastWriteTime | ConvertTo-Json"`,
        { windowsHide: true, timeout: 15000 }
      )
      
      let files = []
      if (stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout)
          files = (Array.isArray(parsed) ? parsed : [parsed]).map(f => ({
            name: f.Name,
            size: f.Length || 0,
            modified: f.LastWriteTime
          }))
        } catch {
          // 解析失败
        }
      }
      
      const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0)
      
      return { 
        ok: true, 
        scanned: max,
        found: files.length,
        totalSize,
        files,
        tempDir,
        note: '扫描完成，实际清理需用户确认'
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 临时文件扫描
   */
  async tempScan({ max = 50 } = {}) {
    return this.diskCleanup({ max })
  },

  /**
   * 进程列表（按 CPU/内存排序）
   * @param {Object} params
   * @param {number} params.max - 返回最大数量，默认30
   * @param {string} params.sortBy - 排序方式：cpu|memory，默认cpu
   */
  async processList({ max = 30, sortBy = 'cpu' } = {}) {
    const platform = process.platform
    
    try {
      if (platform === 'win32') {
        // 使用 wmic 获取进程信息
        const { stdout } = await execAsync(
          `powershell -Command "Get-Process | Select-Object -First ${max * 2} Id,ProcessName,CPU,WorkingSet64,@{N='MemoryMB';E={[math]::Round($_.WorkingSet64/1MB,2)}} | Sort-Object -Property ${sortBy === 'memory' ? 'MemoryMB' : 'CPU'} -Descending | Select-Object -First ${max} | ConvertTo-Json"`,
          { windowsHide: true, timeout: 15000 }
        )
        
        let processes = []
        if (stdout.trim()) {
          try {
            const parsed = JSON.parse(stdout)
            processes = (Array.isArray(parsed) ? parsed : [parsed]).map(p => ({
              pid: p.Id || 0,
              name: p.ProcessName || 'Unknown',
              cpu: p.CPU ? parseFloat(p.CPU.toFixed(2)) : 0,
              memory: p.MemoryMB || 0,
              memoryBytes: p.WorkingSet64 || 0
            }))
          } catch {
            // 解析失败
          }
        }
        
        return { 
          ok: true, 
          count: processes.length,
          sortBy,
          processes
        }
      }
      
      return { ok: false, error: '仅支持 Windows' }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 结束进程
   * @param {Object} params
   * @param {number} params.pid - 进程ID
   * @param {string} params.name - 进程名（如 WeChat.exe）
   */
  async processKill({ pid, name } = {}) {
    try {
      // 🆕 白名单检查
      if (name && isProcessProtected(name)) {
        return { 
          ok: false, 
          error: `「${name}」是系统或工作进程，已保护不终止`,
          protected: true 
        }
      }
      
      if (pid && pid > 0) {
        await execAsync(`taskkill /PID ${pid} /F`, { windowsHide: true })
        return { ok: true, message: `已结束进程 PID=${pid}` }
      }
      
      if (name) {
        await execAsync(`taskkill /IM "${name}" /F`, { windowsHide: true })
        return { ok: true, message: `已结束进程 ${name}` }
      }
      
      return { ok: false, error: '需要提供 pid 或 name' }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 深度磁盘清理
   * @param {Object} params
   * @param {number} params.max - 最大扫描文件数
   * @param {boolean} params.doDelete - 是否实际删除，默认false（仅扫描）
   */
  async diskCleanupDeep({ max = 100, doDelete = false } = {}) {
    const results = {
      tempFiles: { count: 0, size: 0, paths: [] },
      browserCache: { count: 0, size: 0, paths: [] },
      windowsTemp: { count: 0, size: 0, paths: [] },
      recentFiles: { count: 0, size: 0, paths: [] }
    }
    
    const cleanupDirs = [
      { key: 'tempFiles', path: os.tmpdir() },
      { key: 'windowsTemp', path: 'C:\\Windows\\Temp' },
      { key: 'browserCache', path: path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache') },
      { key: 'browserCache', path: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache') },
    ]
    
    for (const dir of cleanupDirs) {
      try {
        const { stdout } = await execAsync(
          `powershell -Command "Get-ChildItem -Path '${dir.path}' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First ${max} FullName,Length | ConvertTo-Json"`,
          { windowsHide: true, timeout: 20000 }
        )
        
        if (stdout.trim()) {
          try {
            const parsed = JSON.parse(stdout)
            const files = (Array.isArray(parsed) ? parsed : [parsed]).filter(f => f.FullName)
            const totalSize = files.reduce((sum, f) => sum + (f.Length || 0), 0)
            
            results[dir.key].count += files.length
            results[dir.key].size += totalSize
            results[dir.key].paths = files.map(f => f.FullName).slice(0, 10)
          } catch {}
        }
      } catch {}
    }
    
    const totalSize = Object.values(results).reduce((sum, r) => sum + r.size, 0)
    const totalCount = Object.values(results).reduce((sum, r) => sum + r.count, 0)
    
    return {
      ok: true,
      summary: { totalFiles: totalCount, totalSize },
      details: results,
      note: doDelete ? '已清理' : '扫描完成，确认后将执行清理'
    }
  },

  /**
   * 回收站清理
   * @param {Object} params
   * @param {boolean} params.doDelete - true=清空，false=扫描
   */
  async recycleBin({ doDelete = false } = {}) {
    try {
      if (doDelete) {
        await execAsync(
          `powershell -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"`,
          { windowsHide: true, timeout: 30000 }
        )
        return { ok: true, message: '回收站已清空' }
      }
      
      // 扫描回收站大小
      const { stdout } = await execAsync(
        `powershell -Command "(New-Object -ComObject Shell.Application).NameSpace(0xA).Items() | Measure-Object -Property Size -Sum | Select-Object Count,@{N='SizeMB';E={[math]::Round($_.Sum/1MB,2)}} | ConvertTo-Json"`,
        { windowsHide: true, timeout: 10000 }
      )
      
      let info = { count: 0, size: 0 }
      if (stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout)
          info = { count: parsed.Count || 0, size: parsed.SizeMB || 0 }
        } catch {}
      }
      
      return {
        ok: true,
        count: info.count,
        sizeMB: info.size,
        message: `回收站有 ${info.count} 个文件，约 ${info.size} MB`
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 浏览器缓存清理
   * @param {Object} params
   * @param {string} params.browser - 浏览器：chrome|edge|firefox|all，默认all
   * @param {boolean} params.doDelete - 是否实际删除
   */
  async browserCache({ browser = 'all', doDelete = false } = {}) {
    const browsers = browser === 'all' 
      ? ['chrome', 'edge', 'firefox'] 
      : [browser]
    
    const results = []
    const cachePaths = {
      chrome: path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
      edge: path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
      firefox: path.join(os.homedir(), 'AppData', 'Local', 'Mozilla', 'Firefox', 'Profiles')
    }
    
    for (const b of browsers) {
      const cachePath = cachePaths[b]
      if (!cachePath) continue
      
      try {
        if (doDelete) {
          await execFileAsync(
            'powershell',
            ['-NoProfile', '-Command', `Remove-Item -Path (Join-Path $env:CACHE_PATH '*') -Recurse -Force -ErrorAction SilentlyContinue`],
            { windowsHide: true, timeout: 30000, env: { ...process.env, CACHE_PATH: cachePath } }
          )
          results.push({ browser: b, status: 'cleaned' })
        } else {
          const { stdout } = await execFileAsync(
            'powershell',
            ['-NoProfile', '-Command', `Get-ChildItem -Path $env:CACHE_PATH -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum | Select-Object Count,@{N='SizeMB';E={[math]::Round($_.Sum/1MB,2)}} | ConvertTo-Json`],
            { windowsHide: true, timeout: 10000, env: { ...process.env, CACHE_PATH: cachePath } }
          )
          
          let info = { count: 0, size: 0 }
          if (stdout.trim()) {
            try {
              const parsed = JSON.parse(stdout)
              info = { count: parsed.Count || 0, size: parsed.SizeMB || 0 }
            } catch {}
          }
          results.push({ browser: b, count: info.count, sizeMB: info.size })
        }
      } catch (e) {
        results.push({ browser: b, error: e.message })
      }
    }
    
    return {
      ok: true,
      results,
      note: doDelete ? '清理完成' : '扫描完成'
    }
  },

  /**
   * 内存使用详情
   */
  async memoryInfo() {
    try {
      const { stdout } = await execAsync(
        `powershell -Command "Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 15 Id,ProcessName,@{N='MemoryMB';E={[math]::Round($_.WorkingSet64/1MB,2)}} | ConvertTo-Json"`,
        { windowsHide: true, timeout: 10000 }
      )
      
      let processes = []
      if (stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout)
          processes = Array.isArray(parsed) ? parsed : [parsed]
        } catch {}
      }
      
      const { stdout: memInfo } = await execAsync(
        `powershell -Command "(Get-CimInstance Win32_OperatingSystem) | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json"`,
        { windowsHide: true, timeout: 5000 }
      )
      
      let memStats = { total: 0, free: 0, used: 0, percent: 0 }
      if (memInfo.trim()) {
        try {
          const parsed = JSON.parse(memInfo)
          const total = parseInt(parsed.TotalVisibleMemorySize) || 0
          const free = parseInt(parsed.FreePhysicalMemory) || 0
          const used = total - free
          memStats = {
            total: Math.round(total / 1024),
            free: Math.round(free / 1024),
            used: Math.round(used / 1024),
            percent: Math.round((used / total) * 100)
          }
        } catch {}
      }
      
      return {
        ok: true,
        memory: memStats,
        topProcesses: processes
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  /**
   * 🆕 一键优化模式
   * 组合执行：内存清理 + 磁盘清理 + 浏览器缓存清理
   * @param {Object} params
   * @param {boolean} params.silent - 静默模式（不清理高风险项）
   */
  async systemOptimize({ silent = false } = {}) {
    const results = {
      memory: { freed: 0, killed: [] },
      disk: { scanned: 0, cleaned: 0 },
      browser: { cleaned: [] },
      recycleBin: { cleaned: false },
      protected: []
    }
    
    try {
      // 1. 内存清理：自动识别高占用非保护进程
      const memResult = await this.processList({ max: 20, sortBy: 'memory' })
      if (memResult.ok && memResult.processes) {
        const killable = filterKillableProcesses(
          memResult.processes.map(p => ({ name: p.name, cpu: p.cpu || 0, memory: p.memory || 0 })),
          { minCpu: 3, minMemoryMB: 200, maxCount: silent ? 2 : 5 }
        )
        
        for (const proc of killable) {
          const killResult = await this.processKill({ name: proc.name })
          if (killResult.ok) {
            results.memory.killed.push(proc.name)
            results.memory.freed += (proc.memory || 0)
          } else if (killResult.protected) {
            results.protected.push(proc.name)
          }
        }
      }
      
      // 2. 磁盘清理
      const diskResult = await this.diskCleanupDeep({ max: 100, doDelete: !silent })
      if (diskResult.ok) {
        results.disk.scanned = diskResult.summary?.totalFiles || 0
        results.disk.cleaned = diskResult.summary?.totalSize || 0
      }
      
      // 3. 浏览器缓存清理（默认不清理，需用户确认）
      if (!silent) {
        const browserResult = await this.browserCache({ browser: 'all', doDelete: true })
        if (browserResult.ok) {
          results.browser.cleaned = browserResult.results?.map(r => r.browser) || []
        }
      }
      
      // 4. 回收站清理（静默模式跳过）
      if (!silent) {
        const recycleResult = await this.recycleBin({ doDelete: true })
        results.recycleBin.cleaned = recycleResult.ok
      }
      
      // 生成报告
      const freedMB = Math.round(results.memory.freed)
      const cleanedMB = Math.round(results.disk.cleaned / (1024 * 1024))
      const killedList = results.memory.killed.join('、') || '无'
      const protectedList = results.protected.join('、') || '无'
      
      return {
        ok: true,
        summary: `优化完成：释放内存 ${freedMB}MB，清理磁盘 ${cleanedMB}MB`,
        details: results,
        message: `已结束进程：${killedList}。系统进程和工作应用（${protectedList}）已保护。`,
        speechText: `一键优化完成，释放了 ${freedMB} 兆内存，${cleanedMB} 兆磁盘空间。`
      }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  },

  async 'browser:search'({ query, browser = 'edge' }) {
    if (!query) {
      return { ok: false, error: 'query 参数缺失' }
    }
    try {
      const isChinese = /[\u4e00-\u9fff]/.test(query)
      const searchUrl = isChinese
        ? `https://www.baidu.com/s?wd=${encodeURIComponent(query)}`
        : `https://www.google.com/search?q=${encodeURIComponent(query)}`
      
      const browserExe = browser === 'chrome' ? 'chrome.exe' : 'msedge.exe'
      spawn('cmd', ['/c', 'start', '', browserExe, searchUrl], { detached: true, stdio: 'ignore', windowsHide: true }).unref()
      
      return { ok: true, type: 'search', detail: searchUrl, message: `正在搜索: ${query}` }
    } catch (e) {
      return { ok: false, error: `搜索失败: ${e.message}` }
    }
  },

  async 'keyboard:type'({ text }) {
    if (!text) return { ok: false, error: 'text 参数缺失' }
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
      spawn('powershell', [
        '-NoProfile', '-Command',
        'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^v")'
      ], { windowsHide: true, detached: true, stdio: 'ignore' }).unref()
      return { ok: true, message: `已输入文本: ${text.substring(0, 50)}` }
    } catch (e) {
      return { ok: false, error: `输入失败: ${e.message}` }
    }
  },

  async 'ide:launch'({ ide = 'vscode', project_path = '', project_name = '', action = 'open_file', files = [], args = [] }) {
    try {
      const fs = require('fs')
      const pathModule = require('path')
      let idePath = ide === 'vscode' ? 'Code.exe' : ide === 'cursor' ? 'Cursor.exe' : ide
      let resolvedProjectPath = project_path
      const createdFiles = []
      
      if (action === 'create_project' && !project_path) {
        const baseDir = 'D:\\'
        const dirName = project_name || 'project'
        const safeName = dirName.replace(/[<>:"/\\|?*]/g, '_')
        resolvedProjectPath = pathModule.join(baseDir, safeName)
        
        if (!fs.existsSync(resolvedProjectPath)) {
          fs.mkdirSync(resolvedProjectPath, { recursive: true })
        }
        
        if (files.length > 0) {
          for (const file of files) {
            const filePath = pathModule.join(resolvedProjectPath, file.path || 'index.html')
            const fileDir = pathModule.dirname(filePath)
            if (!fs.existsSync(fileDir)) fs.mkdirSync(fileDir, { recursive: true })
            let content = file.content || ''
            if (!content) {
              const ext = pathModule.extname(filePath).toLowerCase()
              if (ext === '.html') {
                content = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>${project_name || 'Page'}</title>\n  <style>\n    body { font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }\n    .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }\n    h1 { color: #333; }\n    p { color: #666; line-height: 1.6; }\n  </style>\n</head>\n<body>\n  <div class="container">\n    <h1>${project_name || 'Hello World'}</h1>\n    <p>This is a generated page. Edit me in VSCode!</p>\n  </div>\n</body>\n</html>`
              } else {
                content = `# ${project_name || 'Project'}\n`
              }
            }
            fs.writeFileSync(filePath, content, 'utf-8')
            createdFiles.push(filePath)
          }
        } else {
          const defaultHtml = pathModule.join(resolvedProjectPath, 'index.html')
          if (!fs.existsSync(defaultHtml)) {
            const content = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>${project_name || 'Page'}</title>\n  <style>\n    body { font-family: 'Microsoft YaHei', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }\n    .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }\n    h1 { color: #333; }\n    p { color: #666; line-height: 1.6; }\n  </style>\n</head>\n<body>\n  <div class="container">\n    <h1>${project_name || 'Hello World'}</h1>\n    <p>This is a generated page. Edit me in VSCode!</p>\n  </div>\n</body>\n</html>`
            fs.writeFileSync(defaultHtml, content, 'utf-8')
            createdFiles.push(defaultHtml)
          }
        }
      }
      
      const launchArgs = []
      if (resolvedProjectPath) launchArgs.push(resolvedProjectPath)
      else if (args.length > 0) launchArgs.push(...args)
      
      spawn('cmd', ['/c', 'start', '', idePath, ...launchArgs, '--reuse-window'], {
        windowsHide: false, detached: true, stdio: 'ignore'
      }).unref()
      
      let message = resolvedProjectPath ? `${ide} 已打开项目: ${resolvedProjectPath}` : `${ide} 已启动`
      if (createdFiles.length > 0) message += `，已创建 ${createdFiles.length} 个文件`
      
      if (createdFiles.length > 0) {
        const htmlFile = createdFiles.find(f => f.endsWith('.html'))
        if (htmlFile) {
          setTimeout(() => {
            try {
              spawn('cmd', ['/c', 'start', '', 'msedge.exe', htmlFile], {
                windowsHide: false, detached: true, stdio: 'ignore'
              }).unref()
            } catch (e) {
              console.error('[ide:launch] 自动预览失败:', e)
            }
          }, 3000)
          message += '，浏览器预览将在3秒后打开'
        }
      }
      
      return { ok: true, message, projectPath: resolvedProjectPath, createdFiles }
    } catch (e) {
      return { ok: false, error: `IDE启动失败: ${e.message}` }
    }
  },
}

/**
 * 启动本地 HTTP 服务供后端 Python 调用
 * @param {number} port - 端口
 * @param {object} options - 安全配置
 * @param {function|null} options.validateCommand - 命令安全校验函数，返回 {ok:boolean,error?:string}
 * @param {object|null} options.actionExecutor - ActionExecutor 实例，提供全部28个工具
 */
function startToolServer(port = 9000, options = {}) {
  const { validateCommand = null, actionExecutor = null } = options
  const server = http.createServer(async (req, res) => {
    // CORS 头 —— 仅允许本地回环
    res.setHeader('Content-Type', 'application/json')
    res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:*')
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

    if (req.method === 'OPTIONS') {
      res.writeHead(204)
      res.end()
      return
    }

    if (req.method === 'POST' && req.url === '/execute') {
      let body = ''
      req.on('data', chunk => { body += chunk })
      req.on('end', async () => {
        try {
          const { tool, params } = JSON.parse(body)

          if (!tool || typeof tool !== 'string') {
            res.writeHead(400)
            res.end(JSON.stringify({ ok: false, error: 'tool 参数缺失' }))
            return
          }

          // 安全校验：与 IPC handler 相同的检查
          if (validateCommand) {
            const check = validateCommand(tool, params || {})
            if (!check.ok) {
              res.writeHead(403)
              res.end(JSON.stringify({ ok: false, error: check.error || 'command rejected by security check' }))
              return
            }
          }

          // 优先查 DesktopTools（4个专用工具），再委托给 actionExecutor（28个工具）
          let result
          const toolFn = DesktopTools[tool]
          if (toolFn && typeof toolFn === 'function') {
            result = await toolFn(params || {})
          } else if (actionExecutor && actionExecutor.toolRegistry && actionExecutor.toolRegistry.has(tool)) {
            const handler = actionExecutor.toolRegistry.get(tool)
            const execResult = await handler(params || {})
            result = { ok: execResult.success !== false, ...execResult }
          } else {
            res.writeHead(404)
            res.end(JSON.stringify({ ok: false, error: `Unknown tool: ${tool}` }))
            return
          }

          res.writeHead(200)
          res.end(JSON.stringify(result))
        } catch (e) {
          res.writeHead(500)
          res.end(JSON.stringify({ ok: false, error: e.message }))
        }
      })
    } else if (req.method === 'GET' && req.url === '/health') {
      const aeTools = actionExecutor ? Array.from(actionExecutor.toolRegistry.keys()) : []
      res.writeHead(200)
      res.end(JSON.stringify({ status: 'ok', tools: [...Object.keys(DesktopTools), ...aeTools.filter(t => !DesktopTools[t])] }))
    } else {
      res.writeHead(404)
      res.end(JSON.stringify({ error: 'Not found' }))
    }
  })

  server.on('error', (e) => {
    if (e.code === 'EADDRINUSE') {
      console.warn(`[ToolServer] Port ${port} is already in use, skipping tool server`)
    } else {
      console.error('[ToolServer] Server error:', e)
    }
  })

  server.listen(port, '127.0.0.1', () => {
    console.log(`[ToolServer] Desktop executor listening on http://127.0.0.1:${port}`)
  })

  return server
}

module.exports = {
  DesktopTools,
  startToolServer
}