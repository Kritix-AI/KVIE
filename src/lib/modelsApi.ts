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
  status: 'starting' | 'connecting' | 'downloading' | 'completed' | 'error' | 'idle' | string
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
  let pollTimer: any = null
  let unlistenFn: (() => void) | null = null

  const handlePayload = (payload: ModelProgressPayload) => {
    if (isCancelled || isFinished) return
    if (payload.model_id !== modelId) return

    onProgress(payload)

    if (payload.status === 'completed' || payload.progress >= 100) {
      isFinished = true
      if (pollTimer) clearInterval(pollTimer)
      onComplete()
    } else if (payload.status === 'error') {
      isFinished = true
      if (pollTimer) clearInterval(pollTimer)
      onError(payload.error || 'Failed to download model weights')
    }
  }

  // 1. Trigger background download on backend
  const startDownload = async () => {
    try {
      await fetch(`${SERVICE_BASE_URL}/api/models/download/start?model_id=${encodeURIComponent(modelId)}`, {
        method: 'POST',
      })
    } catch {
      // If REST start fails, try native Tauri invoke
      try {
        await invoke('download_model_native', { model_id: modelId, modelId })
      } catch {
        // Fallback
      }
    }

    // 2. Poll in-memory progress every 150ms (ultra-fast, zero-buffering)
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(async () => {
      if (isCancelled || isFinished) {
        clearInterval(pollTimer)
        return
      }

      try {
        const res = await fetch(`${SERVICE_BASE_URL}/api/models/progress?model_id=${encodeURIComponent(modelId)}`)
        if (res.ok) {
          const payload: ModelProgressPayload = await res.json()
          handlePayload(payload)
        }
      } catch {
        // Service temporarily busy
      }
    }, 150)
  }

  void startDownload()

  // 3. Also listen to native Tauri events as secondary channel
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
    if (pollTimer) clearInterval(pollTimer)
    if (unlistenFn) unlistenFn()
  }
}
