// 命令相关工具函数

import type {
  ActionCommand,
  ActionExecutionResult,
  ProcessTopData,
  DiskListData,
  TempScanData,
} from '../types'

// 类型检查辅助函数
export function hasProcesses(data: unknown): data is ProcessTopData {
  return typeof data === 'object' && data !== null && 'processes' in data
}

export function hasDrives(data: unknown): data is DiskListData {
  return typeof data === 'object' && data !== null && 'drives' in data
}

export function hasEntries(data: unknown): data is TempScanData {
  return typeof data === 'object' && data !== null && 'entries' in data
}

// 对对象key排序，确保JSON签名一致（用于去重）
export function sortKeys(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) return obj.map(sortKeys)
  const sorted: Record<string, unknown> = {}
  for (const key of Object.keys(obj as Record<string, unknown>).sort()) {
    sorted[key] = sortKeys((obj as Record<string, unknown>)[key])
  }
  return sorted
}

// 创建命令签名（工具+排序后的参数）
export function createCommandSignature(tool: string, params: Record<string, unknown> | undefined): string {
  return `${tool}::${JSON.stringify(sortKeys(params || {}))}`
}

// 本地建议生成（后端不可用时）- 支持去重和跳过已分析工具
export function generateAdviceFromResults(
  results: ActionExecutionResult[],
  existingCommands: ActionCommand[] = [],
  _analyzedTools: Set<string> = new Set()
): ActionCommand[] {
  const advice: ActionCommand[] = []
  const existingSigs = new Set(existingCommands.map(c => createCommandSignature(c.tool, c.params)))

  const addIfNew = (cmd: ActionCommand) => {
    const sig = createCommandSignature(cmd.tool, cmd.params)
    if (!existingSigs.has(sig)) {
      advice.push(cmd)
      existingSigs.add(sig)
    }
  }

  // 查找进程数据
  const processResult = results.find(r => r.tool === 'process:top' && r.success && hasProcesses(r.data))
  if (processResult?.data) {
    const processes = (processResult.data as ProcessTopData).processes
    if (processes && processes.length > 0) {
      const topProc = processes[0]
      if (topProc.mem > 500000) { // 500MB+
        addIfNew({
          id: `advice-${Date.now()}-kill`,
          tool: 'process:kill',
          type: 'destructive',
          params: { pid: topProc.pid },
          reason: `🤖 AI 建议: ${topProc.name} 占用 ${(topProc.mem / 1024).toFixed(0)}MB 内存，建议结束以释放资源`,
          confidence: 0.85,
          risk: 'high',
          require_confirmation: true,
          recommended: true,
        })
      }
    }
  }

  // 查找磁盘数据
  const diskResult = results.find(r => r.tool === 'disk:list' && r.success && hasDrives(r.data))
  if (diskResult?.data) {
    const drives = (diskResult.data as DiskListData).drives
    const fullDrive = drives.find(d => d.usePercent > 85)
    if (fullDrive) {
      addIfNew({
        id: `advice-${Date.now()}-cleanup`,
        tool: 'temp:cleanup',
        type: 'destructive',
        params: { max: 100 },
        reason: `🤖 AI 建议: ${fullDrive.name}盘已使用 ${fullDrive.usePercent}%，建议清理临时文件`,
        confidence: 0.9,
        risk: 'high',
        require_confirmation: true,
        recommended: true,
      })
    }
  }

  // 查找临时文件数据
  const tempResult = results.find(r => r.tool === 'temp:scan' && r.success && hasEntries(r.data))
  if (tempResult?.data) {
    const entries = (tempResult.data as TempScanData).entries
    if (entries.length > 20) {
      addIfNew({
        id: `advice-${Date.now()}-temp`,
        tool: 'temp:cleanup',
        type: 'destructive',
        params: { max: 50 },
        reason: `🤖 AI 建议: 发现 ${entries.length} 个临时文件，建议清理`,
        confidence: 0.88,
        risk: 'high',
        require_confirmation: true,
        recommended: true,
      })
    }
  }

  return advice
}

// 本地默认命令生成（后端不可用时的降级）
export function generateDefaultCommands(text: string): ActionCommand[] {
  const nl = text.toLowerCase()
  const commands: ActionCommand[] = []

  const hasOpen = nl.includes('打开') || nl.includes('启动') || nl.includes('运行')
  const hasWrite = nl.includes('写') || nl.includes('生成') || nl.includes('创建') || nl.includes('制作') || nl.includes('编写') || nl.includes('设计')
  const hasSearch = nl.includes('搜索') || nl.includes('搜一下') || nl.includes('查找') || nl.includes('查一下')
  const hasPreview = nl.includes('预览') || nl.includes('浏览器查看') || nl.includes('查看页面')

  if (hasOpen) {
    const appMap: Record<string, string> = {
      '记事本': 'notepad.exe', '微信': 'WeChat.exe', 'qq': 'QQ.exe',
      'vscode': 'Code.exe', 'edge': 'msedge.exe', '浏览器': 'msedge.exe',
      '计算器': 'calc.exe', '资源管理器': 'explorer.exe',
      'chrome': 'chrome.exe', '谷歌': 'chrome.exe', 'photoshop': 'Photoshop.exe',
      'ps': 'Photoshop.exe', 'wps': 'wps.exe',
      'pycharm': 'pycharm64.exe',
    }
    const officeApps = ['word', 'excel', 'ppt']
    let openedOfficeApp: string | null = null
    for (const app of officeApps) {
      if (nl.includes(app)) {
        openedOfficeApp = app
        break
      }
    }
    if (openedOfficeApp && hasWrite) {
      // "打开Word写XXX" → 不单独 app:launch，content:generate 的 auto_open 会自动启动
    } else {
      if (openedOfficeApp) {
        const officeExeMap: Record<string, string> = {
          'word': 'WINWORD.EXE', 'excel': 'EXCEL.EXE', 'ppt': 'POWERPNT.EXE',
        }
        commands.push({
          id: `default-${Date.now()}-app`,
          tool: 'app:launch',
          type: 'write',
          params: { path: officeExeMap[openedOfficeApp!] },
          reason: `打开${openedOfficeApp}`,
          confidence: 0.9,
          risk: 'low',
        })
      }
      for (const [key, path] of Object.entries(appMap)) {
        if (nl.includes(key)) {
          commands.push({
            id: `default-${Date.now()}-app`,
            tool: 'app:launch',
            type: 'write',
            params: { path },
            reason: `打开${key}`,
            confidence: 0.9,
            risk: 'low',
          })
          break
        }
      }
    }
  }

  if (hasSearch) {
    const searchMatch = text.match(/(?:搜索|搜一下|查找|查一下)(.{1,30})/)
    const query = searchMatch ? searchMatch[1].trim() : text.slice(0, 20)
    const encodedQuery = encodeURIComponent(query)
    commands.push({
      id: `default-${Date.now()}-search`,
      tool: 'app:launch',
      type: 'write',
      params: { path: 'msedge.exe', url: `https://www.baidu.com/s?wd=${encodedQuery}` },
      reason: `搜索「${query}」`,
      confidence: 0.9,
      risk: 'low',
    })
  }

  if (hasWrite) {
    const writeMatch = text.match(/(?:写|生成|创建|制作|编写|设计)(.{1,30})/)
    const theme = writeMatch ? writeMatch[1].trim() : text.slice(0, 20)
    let contentType = 'word'
    if (/登录页面|网页|html|网站|页面/.test(nl)) contentType = 'html'
    else if (/代码|程序|脚本|python/.test(nl)) contentType = 'python'
    commands.push({
      id: `default-${Date.now()}-content`,
      tool: 'content:generate',
      type: 'write',
      params: { task: theme, content_type: contentType, theme, length: '中', auto_open: true },
      reason: `生成「${theme}」${contentType}内容`,
      confidence: 0.85,
      risk: 'low',
    })
  }

  if (hasPreview) {
    commands.push({
      id: `default-${Date.now()}-preview`,
      tool: 'app:launch',
      type: 'write',
      params: { path: 'msedge.exe' },
      reason: '打开浏览器预览',
      confidence: 0.8,
      risk: 'low',
    })
  }

  if (nl.includes('cpu') || nl.includes('处理器') || nl.includes('卡顿') || nl.includes('卡') || nl.includes('慢')) {
    commands.push({
      id: `default-${Date.now()}-sysinfo`,
      tool: 'system:info',
      type: 'read',
      params: {},
      reason: '获取系统状态',
      confidence: 0.9,
      risk: 'low',
    })
    commands.push({
      id: `default-${Date.now()}-top`,
      tool: 'process:top',
      type: 'read',
      params: { max: 10 },
      reason: '查看高占用进程',
      confidence: 0.9,
      risk: 'low',
    })
  }
  if (nl.includes('内存') || nl.includes('memory')) {
    commands.push({
      id: `default-${Date.now()}-mem`,
      tool: 'process:top',
      type: 'read',
      params: { max: 10 },
      reason: '查看高内存占用进程',
      confidence: 0.9,
      risk: 'low',
    })
  }
  if (nl.includes('磁盘') || nl.includes('c盘') || nl.includes('空间') || nl.includes('清理') || nl.includes('垃圾')) {
    commands.push({
      id: `default-${Date.now()}-disk`,
      tool: 'disk:list',
      type: 'read',
      params: {},
      reason: '获取磁盘使用情况',
      confidence: 0.9,
      risk: 'low',
    })
    commands.push({
      id: `default-${Date.now()}-temp`,
      tool: 'temp:scan',
      type: 'read',
      params: { max: 50 },
      reason: '扫描可清理的临时文件',
      confidence: 0.85,
      risk: 'low',
    })
  }
  if (commands.length === 0) {
    commands.push({
      id: `default-${Date.now()}-fallback`,
      tool: 'system:info',
      type: 'read',
      params: {},
      reason: '获取系统整体状态',
      confidence: 0.9,
      risk: 'low',
    })
  }

  const seen = new Set<string>()
  return commands.filter(cmd => {
    const sig = `${cmd.tool}:${JSON.stringify(cmd.params)}`
    if (seen.has(sig)) return false
    seen.add(sig)
    return true
  })
}