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
  let unlistenFn: (() => void) | null = null
  let isFinished = false

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

  // 1. Setup EventSource stream (high-throughput SSE connection)
  let eventSource: EventSource | null = null
  try {
    eventSource = new EventSource(`${SERVICE_BASE_URL}/api/models/download?model_id=${encodeURIComponent(modelId)}`)

    eventSource.onmessage = event => {
      try {
        const data: ModelProgressPayload = JSON.parse(event.data)
        handlePayload(data)
        if (isFinished) {
          eventSource?.close()
        }
      } catch {
        // parse error
      }
    }

    eventSource.onerror = () => {
      eventSource?.close()
      // If SSE stream closed before finishing, try native invoke
      if (!isFinished && !isCancelled) {
        void invoke('download_model_native', { model_id: modelId, modelId }).catch(err => {
          onError(String(err))
        })
      }
    }
  } catch {
    // SSE fallback
  }

  // 2. Listen to native Tauri events
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
    if (unlistenFn) unlistenFn()
    if (eventSource) eventSource.close()
  }
}
