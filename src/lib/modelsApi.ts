/**
 * KVIE Real Model Management & Download Client
 */

import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

export interface ModelProgressPayload {
  model_id: string
  progress: number // 0 to 100
  downloaded_bytes?: number
  total_bytes?: number
  status: 'starting' | 'connecting' | 'downloading' | 'completed' | 'error' | string
  speed?: string
  error?: string
}

export interface ModelsStatusResponse {
  installed: string[]
  active: string
}

const SERVICE_BASE_URL = 'http://127.0.0.1:8765'

export async function fetchModelsStatus(): Promise<ModelsStatusResponse | null> {
  try {
    const res = await fetch(`${SERVICE_BASE_URL}/api/models`, { method: 'GET' })
    if (res.ok) {
      return await res.json()
    }
  } catch {
    // Service might still be booting up
  }
  return null
}

export async function selectActiveModel(modelId: string): Promise<boolean> {
  try {
    const res = await fetch(`${SERVICE_BASE_URL}/api/models/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    })
    if (res.ok) {
      const data = await res.json()
      return data.ok === true
    }
  } catch {
    // Fallback
  }
  return false
}

export function downloadModelWithProgress(
  modelId: string,
  onProgress: (payload: ModelProgressPayload) => void,
  onComplete: () => void,
  onError: (err: string) => void
): () => void {
  let isCancelled = false
  let isFinished = false
  let unlistenFn: (() => void) | null = null

  const handlePayload = (payload: ModelProgressPayload) => {
    if (isCancelled || isFinished) return
    if (payload.model_id !== modelId) return

    onProgress(payload)

    if (payload.status === 'completed' || payload.progress >= 100) {
      isFinished = true
      onComplete()
    } else if (payload.status === 'error') {
      isFinished = true
      onError(payload.error || 'Failed to download model weights')
    }
  }

  const abortController = new AbortController()

  // 1. Primary: Direct Fetch Stream with ReadableStream reader
  const startFetchStream = async () => {
    try {
      const res = await fetch(
        `${SERVICE_BASE_URL}/api/models/download?model_id=${encodeURIComponent(modelId)}`,
        { signal: abortController.signal }
      )

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }

      if (!res.body) {
        throw new Error('No streaming response body available')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (!isCancelled && !isFinished) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (trimmed.startsWith('data:')) {
            try {
              const data: ModelProgressPayload = JSON.parse(trimmed.slice(5).trim())
              handlePayload(data)
            } catch {
              // ignore parse errors
            }
          }
        }
      }

      if (!isFinished && !isCancelled) {
        isFinished = true
        onComplete()
      }
    } catch (err: any) {
      if (isCancelled || isFinished) return
      // If fetch fails, try native Tauri invoke fallback
      try {
        await invoke('download_model_native', { model_id: modelId, modelId })
      } catch (nativeErr) {
        onError(err?.message || String(nativeErr))
      }
    }
  }

  void startFetchStream()

  // 2. Secondary: Listen to native Tauri events
  try {
    void listen<string>('model-download-progress', event => {
      try {
        const payload: ModelProgressPayload = JSON.parse(event.payload)
        handlePayload(payload)
      } catch {
        // parsing
      }
    }).then(fn => {
      unlistenFn = fn
    })
  } catch {
    // browser mode
  }

  return () => {
    isCancelled = true
    abortController.abort()
    if (unlistenFn) unlistenFn()
  }
}
