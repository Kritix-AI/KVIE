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
  status: 'starting' | 'connecting' | 'downloading' | 'completed' | 'error'
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
  let unlistenFn: (() => void) | null = null

  // 1. Try Native Tauri Invoke Method
  try {
    void listen<string>('model-download-progress', event => {
      if (isCancelled) return
      try {
        const payload: ModelProgressPayload = JSON.parse(event.payload)
        if (payload.model_id === modelId) {
          onProgress(payload)
          if (payload.status === 'completed') {
            onComplete()
          } else if (payload.status === 'error') {
            onError(payload.error || 'Failed to download model weights')
          }
        }
      } catch {
        // parsing
      }
    }).then(fn => {
      unlistenFn = fn
    })

    void invoke('download_model_native', { modelId }).catch(() => {
      // If native invoke fails, try SSE fallback below
    })
  } catch {
    // Webview fallback
  }

  // 2. HTTP Server-Sent Events (SSE) Fallback
  let eventSource: EventSource | null = null
  try {
    eventSource = new EventSource(`${SERVICE_BASE_URL}/api/models/download?model_id=${encodeURIComponent(modelId)}`)

    eventSource.onmessage = event => {
      if (isCancelled) return
      try {
        const data: ModelProgressPayload = JSON.parse(event.data)
        onProgress(data)
        if (data.status === 'completed') {
          eventSource?.close()
          onComplete()
        } else if (data.status === 'error') {
          eventSource?.close()
          onError(data.error || 'Failed to download model weights')
        }
      } catch {
        // Parse error
      }
    }

    eventSource.onerror = () => {
      eventSource?.close()
      // Only trigger error if not handled by native invoke
    }
  } catch {
    // Fallback
  }

  return () => {
    isCancelled = true
    if (unlistenFn) unlistenFn()
    if (eventSource) eventSource.close()
  }
}
