// 格式化工具函数

export function formatDateTime(value?: string | null): string {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function formatFileSize(size?: number): string {
  if (!size || size <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = size
  let index = 0
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024
    index += 1
  }
  return `${current.toFixed(current >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

let logIdCounter = 0
export function nextLogId(): string {
  logIdCounter += 1
  return `log-${Date.now()}-${logIdCounter}`
}
