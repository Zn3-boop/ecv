// API 工具函数 - 支持运行时动态后端地址

import type { BrowserSpeechWindow, DesktopAPI } from '../types'

// 默认后端地址（环境变量或 localhost）
const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

// 运行时后端地址缓存
let _apiBase: string | null = null

/**
 * 获取 desktopAPI 实例
 */
export function getDesktopAPI(): DesktopAPI | undefined {
  return (window as unknown as BrowserSpeechWindow).desktopAPI
}

/**
 * 异步获取 API 基础地址
 * 优先从 IPC 配置读取，其次用环境变量，最后用默认值
 */
export async function getApiBase(): Promise<string> {
  if (_apiBase) return _apiBase
  
  const api = getDesktopAPI()
  if (api?.getBackendConfig) {
    try {
      const cfg = await api.getBackendConfig()
      if (cfg?.apiBase) {
        _apiBase = cfg.apiBase
        return _apiBase
      }
    } catch (e) {
      console.warn('[api] failed to get backend config from IPC:', e)
    }
  }
  
  _apiBase = DEFAULT_API_BASE
  return _apiBase as string
}

/**
 * 设置后端地址（会持久化到主进程）
 */
export async function setApiBase(url: string): Promise<void> {
  const api = getDesktopAPI()
  if (api?.setBackendConfig) {
    await api.setBackendConfig({ apiBase: url })
  }
  _apiBase = url
}

/**
 * 通用 fetchJSON 封装
 */
export async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

/**
 * 获取存储 API 基础地址
 */
export async function getStorageApiBase(): Promise<string> {
  return `${await getApiBase()}/storage`
}

/**
 * 获取语音 API 基础地址
 */
export async function getVoiceApiBase(): Promise<string> {
  return `${await getApiBase()}/voice`
}

// 预加载默认 API 地址（启动时调用一次）
getApiBase()
