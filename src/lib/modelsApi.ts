/**
 * KVIE Real Model Management & Download Client
 */

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
    // Service might be offline or using local fallback
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
  const eventSource = new EventSource(`${SERVICE_BASE_URL}/api/models/download?model_id=${encodeURIComponent(modelId)}`)

  eventSource.onmessage = event => {
    try {
      const data: ModelProgressPayload = JSON.parse(event.data)
      onProgress(data)
      if (data.status === 'completed') {
        eventSource.close()
        onComplete()
      } else if (data.status === 'error') {
        eventSource.close()
        onError(data.error || 'Failed to download model weights')
      }
    } catch {
      // Parse error
    }
  }

  eventSource.onerror = () => {
    eventSource.close()
    onError('Connection to model download stream lost')
  }

  return () => {
    eventSource.close()
  }
}
