/**
 * KVIE Real Model Management & Download Client
 */

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { isAndroid } from './androidKeyboard'

export interface ModelProgressPayload {
  model_id: string
  progress: number // 0 to 100
  downloaded_bytes?: number
  total_bytes?: number
  status: 'starting' | 'connecting' | 'downloading' | 'completed' | 'error' | 'idle' | string
  speed?: string
  error?: string
}

export interface ModelsStatusResponse {
  installed: string[]
  active: string
}

export interface ServiceHealthResponse {
  ok: boolean
  model_ready: boolean
  active_model?: string
}

export const getServiceBaseUrl = (): string => {
  const DEFAULT = 'http://127.0.0.1:8765'
  if (typeof window !== 'undefined') {
    const custom = localStorage.getItem('kvie_backend_url')
    if (custom) {
      try {
        const parsed = new URL(custom.trim())
        // Only allow loopback addresses to prevent SSRF
        if (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost') {
          return parsed.origin
        }
      } catch {
        // Invalid URL — fall through to default
      }
    }
  }
  return DEFAULT
}

export async function fetchServiceHealth(): Promise<ServiceHealthResponse | null> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 2500)
  try {
    const response = await fetch(`${getServiceBaseUrl()}/health`, {
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!response.ok) return null
    const data = await response.json() as ServiceHealthResponse
    return data.ok === true ? data : null
  } catch {
    return null
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function fetchModelsStatus(): Promise<ModelsStatusResponse | null> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 2500)
  try {
    const res = await fetch(`${getServiceBaseUrl()}/api/models`, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    })
    if (res.ok) {
      const data = await res.json() as ModelsStatusResponse
      if (Array.isArray(data.installed) && typeof data.active === 'string') return data
    }
  } catch {
    // Service might still be booting up
  } finally {
    window.clearTimeout(timeout)
  }
  return null
}

export async function selectActiveModel(modelId: string): Promise<boolean> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 2500)
  try {
    const res = await fetch(`${getServiceBaseUrl()}/api/models/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
      signal: controller.signal,
    })
    if (res.ok) {
      const data = await res.json()
      return data.ok === true
    }
  } catch {
    // Fallback
  } finally {
    window.clearTimeout(timeout)
  }
  return false
}

export async function refineVoiceTextWithLLM(text: string, style = 'clean'): Promise<string> {
  if (!text || !text.trim()) return text

  try {
    if (isAndroid()) throw new Error('Android uses its local keyboard engine')
    const res = await fetch(`${getServiceBaseUrl()}/api/autoedit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, style }),
    })
    if (res.ok) {
      const data = await res.json()
      if (data && data.refined_text && data.refined_text.trim()) {
        return data.refined_text.trim()
      }
    }
  } catch {}

  // On-Device Client Fallback (SmolLM2 Heuristic Edge Polish)
  let refined = text.trim()
  const spokenPunctuation: Record<string, string> = {
    ' comma': ',',
    ' period': '.',
    ' full stop': '.',
    ' question mark': '?',
    ' exclamation mark': '!',
    ' exclamation point': '!',
    ' new line': '\n',
  }
  for (const [cue, sym] of Object.entries(spokenPunctuation)) {
    refined = refined.replace(new RegExp(cue, 'gi'), sym)
  }

  const fillers = [/\bum+\b/gi, /\buh+\b/gi, /\blike\b/gi, /\byou know\b/gi, /\bmatlab\b/gi, /\bbasically\b/gi, /\bactually\b/gi]
  fillers.forEach(f => { refined = refined.replace(f, '') })
  refined = refined.replace(/\s+/g, ' ').trim()

  // Capitalize isolated "i" and sentence start
  refined = refined.replace(/\bi\b/g, 'I')
  refined = refined.replace(/(^\s*|[.!?]\s*)([a-z])/g, (_, p1, p2) => p1 + p2.toUpperCase())

  if (refined.split(/\s+/).length >= 4 && !/[.!?]$/.test(refined)) {
    refined += '.'
  }
  return refined
}

export function downloadModelWithProgress(
  modelId: string,
  onProgress: (payload: ModelProgressPayload) => void,
  onComplete: () => void,
  onError: (err: string) => void
): () => void {
  let isCancelled = false
  let isFinished = false
  let pollInFlight = false
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let unlistenFn: (() => void) | null = null
  let unlistenErrorFn: (() => void) | null = null

  const cleanupListeners = () => {
    unlistenFn?.()
    unlistenErrorFn?.()
    unlistenFn = null
    unlistenErrorFn = null
  }

  const handlePayload = (payload: ModelProgressPayload) => {
    if (isCancelled || isFinished) return
    if (payload.model_id !== modelId) return

    onProgress(payload)

    if (payload.status === 'completed' || payload.progress >= 100) {
      isFinished = true
      if (pollTimer) clearInterval(pollTimer)
      cleanupListeners()
      onComplete()
    } else if (payload.status === 'error') {
      isFinished = true
      if (pollTimer) clearInterval(pollTimer)
      cleanupListeners()
      onError(payload.error || 'Failed to download model weights')
    }
  }

  const finishWithError = (message: string) => {
    if (isCancelled || isFinished) return
    isFinished = true
    if (pollTimer) clearInterval(pollTimer)
    cleanupListeners()
    onError(message)
  }

  // 1. Trigger background download on backend
  const startDownload = async () => {
    try {
      const response = await fetch(`${getServiceBaseUrl()}/api/models/download/start?model_id=${encodeURIComponent(modelId)}`, {
        method: 'POST',
        cache: 'no-store',
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Model service returned HTTP ${response.status}`)
      }
      const body = await response.json()
      if (body.ok !== true) throw new Error(body.detail || 'Model service rejected the download')
    } catch (backendError) {
      // The packaged desktop app can use the Rust command if the local Python service is unavailable.
      try {
        await invoke('download_model_native', { modelId })
      } catch (nativeError: any) {
        finishWithError(nativeError?.message || (backendError instanceof Error ? backendError.message : 'Model service unavailable'))
      }
    }
  }

  const registerAndStart = async () => {
    try {
      unlistenFn = await listen<string>('model-download-progress', (event) => {
        try {
          const data = typeof event.payload === 'string' ? JSON.parse(event.payload) : event.payload
          handlePayload(data)
        } catch {}
      })
      unlistenErrorFn = await listen<{ model_id?: string; error?: string }>('model-download-error', (event) => {
        const payload = event.payload
        if (payload?.model_id && payload.model_id !== modelId) return
        finishWithError(payload?.error || 'Model download failed')
      })
    } catch {
      // Web preview has no native event bus; backend polling still works.
    }
    if (isCancelled) {
      // Cancel ran while the listeners were still being registered.
      cleanupListeners()
      return
    }

    // 2. Poll the Python service; Tauri events cover the native fallback.
    pollTimer = setInterval(async () => {
      if (isCancelled || isFinished) {
        if (pollTimer) clearInterval(pollTimer)
        return
      }
      if (pollInFlight) return
      pollInFlight = true
      try {
        const res = await fetch(`${getServiceBaseUrl()}/api/models/progress?model_id=${encodeURIComponent(modelId)}`, {
          cache: 'no-store',
        })
        if (res.ok) handlePayload(await res.json() as ModelProgressPayload)
      } catch {
        // Offline / connecting
      } finally {
        pollInFlight = false
      }
    }, 1000)

    await startDownload()
  }

  void registerAndStart()

  // Return cancel function
  return () => {
    isCancelled = true
    if (pollTimer) clearInterval(pollTimer)
    cleanupListeners()
  }
}
