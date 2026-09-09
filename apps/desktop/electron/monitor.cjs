const os = require('os')
const si = require('systeminformation')

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let index = 0

  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }

  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

function formatSpeed(bytesPerSec) {
  if (!Number.isFinite(bytesPerSec) || bytesPerSec <= 0) return '0 B/s'
  return `${formatBytes(bytesPerSec)}/s`
}

function getCpuSnapshot() {
  const cpus = os.cpus()
  const total = cpus.reduce(
    (acc, cpu) => {
      Object.values(cpu.times).forEach((time) => {
        acc.total += time
      })
      acc.idle += cpu.times.idle
      return acc
    },
    { idle: 0, total: 0 },
  )

  return total
}

let previousCpu = getCpuSnapshot()

function getCpuUsagePercent() {
  const currentCpu = getCpuSnapshot()
  const idleDiff = currentCpu.idle - previousCpu.idle
  const totalDiff = currentCpu.total - previousCpu.total
  previousCpu = currentCpu

  if (totalDiff <= 0) return 0
  return Math.max(0, Math.min(100, Number(((1 - idleDiff / totalDiff) * 100).toFixed(1))))
}

async function getDiskMetrics() {
  const [fsSize, rawFsStats] = await Promise.all([si.fsSize(), si.fsStats()])
  const fsStats = rawFsStats ?? {}
  const disks = fsSize.slice(0, 4).map((disk) => ({
    fs: disk.fs,
    type: disk.type,
    mount: disk.mount,
    size: disk.size,
    used: disk.used,
    available: disk.available,
    usePercent: Number((disk.use ?? 0).toFixed(1)),
    sizeLabel: formatBytes(disk.size),
    usedLabel: formatBytes(disk.used),
    availableLabel: formatBytes(disk.available),
  }))

  return {
    readBytesPerSec: fsStats.rxSec ?? 0,
    writeBytesPerSec: fsStats.wxSec ?? 0,
    readLabel: formatSpeed(fsStats.rxSec ?? 0),
    writeLabel: formatSpeed(fsStats.wxSec ?? 0),
    disks,
  }
}

async function getNetworkMetrics() {
  const [defaultInterface, stats] = await Promise.all([si.networkInterfaceDefault(), si.networkStats()])
  const primary = stats.find((item) => item.iface === defaultInterface) ?? stats[0]

  // 计算总的网络速度
  const totalRxSec = stats.reduce((sum, item) => sum + (item.rx_sec ?? 0), 0)
  const totalTxSec = stats.reduce((sum, item) => sum + (item.tx_sec ?? 0), 0)

  return {
    defaultInterface: defaultInterface || primary?.iface || 'unknown',
    bytesRecvPerSec: totalRxSec,
    bytesSentPerSec: totalTxSec,
    recvLabel: formatSpeed(totalRxSec),
    sentLabel: formatSpeed(totalTxSec),
    interfaces: stats.slice(0, 4).map((item) => ({
      iface: item.iface,
      operstate: item.operstate,
      rxBytesPerSec: item.rx_sec ?? 0,
      txBytesPerSec: item.tx_sec ?? 0,
      rxLabel: formatSpeed(item.rx_sec ?? 0),
      txLabel: formatSpeed(item.tx_sec ?? 0),
      rxDropped: item.rx_dropped ?? 0,
      txDropped: item.tx_dropped ?? 0,
    })),
  }
}

async function getProcessMetrics() {
  const processes = await si.processes()
  const topProcesses = processes.list
    .filter((proc) => proc.name !== 'System Idle Process' && proc.name !== 'Idle')
    .sort((a, b) => (b.cpu ?? 0) - (a.cpu ?? 0))
    .slice(0, 6)
    .map((proc) => {
      // memRss is in KB from systeminformation, convert to bytes for formatBytes
      const memBytes = (proc.memRss ?? 0) * 1024
      return {
        pid: proc.pid,
        name: proc.name,
        cpu: Number((proc.cpu ?? 0).toFixed(1)),
        memory: Number((proc.memRss ?? 0).toFixed(1)),
        memoryLabel: formatBytes(memBytes),
        state: proc.state,
        path: proc.path,
      }
    })

  return {
    all: processes.all,
    running: processes.running,
    blocked: processes.blocked,
    sleeping: processes.sleeping,
    topProcesses,
  }
}

function buildAlerts({ cpuUsagePercent, memoryUsagePercent, disks }) {
  const alerts = []

  if (cpuUsagePercent >= 85) {
    alerts.push({
      level: 'critical',
      type: 'cpu',
      title: 'CPU 占用过高',
      message: `当前 CPU 使用率达到 ${cpuUsagePercent}%`,
    })
  } else if (cpuUsagePercent >= 70) {
    alerts.push({
      level: 'warning',
      type: 'cpu',
      title: 'CPU 占用偏高',
      message: `当前 CPU 使用率达到 ${cpuUsagePercent}%`,
    })
  }

  if (memoryUsagePercent >= 90) {
    alerts.push({
      level: 'critical',
      type: 'memory',
      title: '内存占用过高',
      message: `当前内存使用率达到 ${memoryUsagePercent}%`,
    })
  } else if (memoryUsagePercent >= 80) {
    alerts.push({
      level: 'warning',
      type: 'memory',
      title: '内存占用偏高',
      message: `当前内存使用率达到 ${memoryUsagePercent}%`,
    })
  }

  disks.forEach((disk) => {
    if (disk.usePercent >= 90) {
      alerts.push({
        level: 'critical',
        type: 'disk',
        title: `磁盘空间告急 · ${disk.fs}`,
        message: `${disk.fs} 已使用 ${disk.usePercent}%，剩余 ${disk.availableLabel}`,
      })
    } else if (disk.usePercent >= 80) {
      alerts.push({
        level: 'warning',
        type: 'disk',
        title: `磁盘空间偏紧 · ${disk.fs}`,
        message: `${disk.fs} 已使用 ${disk.usePercent}%，剩余 ${disk.availableLabel}`,
      })
    }
  })

  return alerts
}

async function getSystemMetrics() {
  const totalMemory = os.totalmem()
  const freeMemory = os.freemem()
  const usedMemory = totalMemory - freeMemory
  const memoryUsagePercent = totalMemory > 0 ? Number(((usedMemory / totalMemory) * 100).toFixed(1)) : 0
  const loadAverage = os.loadavg().map((value) => Number(value.toFixed(2)))

  const [disk, network, processes] = await Promise.all([
    getDiskMetrics(),
    getNetworkMetrics(),
    getProcessMetrics(),
  ])

  const cpuUsagePercent = getCpuUsagePercent()
  const alerts = buildAlerts({
    cpuUsagePercent,
    memoryUsagePercent,
    disks: disk.disks,
  })

  return {
    timestamp: new Date().toISOString(),
    hostname: os.hostname(),
    platform: `${os.platform()} ${os.release()}`,
    uptimeSeconds: os.uptime(),
    cpu: {
      usagePercent: cpuUsagePercent,
      cores: os.cpus().length,
      model: os.cpus()[0]?.model ?? 'unknown',
      loadAverage,
    },
    memory: {
      total: totalMemory,
      free: freeMemory,
      used: usedMemory,
      usagePercent: memoryUsagePercent,
      totalLabel: formatBytes(totalMemory),
      usedLabel: formatBytes(usedMemory),
      freeLabel: formatBytes(freeMemory),
    },
    disk,
    network,
    processes,
    alerts,
    temp_path: os.tmpdir(),
  }
}

module.exports = {
  getSystemMetrics,
}