import { useCallback, useEffect, useRef, useState } from 'react'
import { isTauri } from '@tauri-apps/api/core'

import { runGrammarRouter } from '../lib/grammarRouter'
import { stripVerbalBacktracks } from '../lib/backtrackStripper'
import { mergeRollingText } from '../lib/incrementalTypingEngine'
import { getServiceBaseUrl } from '../lib/modelsApi'
import {
  startAudioWorklet,
  type WorkletHandle,
} from './audioWorkletProcessor'

// ── Compact partial events (omit start_ms/end_ms/confidence to reduce overhead) ─
interface PartialEvent { kind: 'partial'; text: string; ts: number }
interface FinalEvent { kind: 'final'; text: string; ts: number; confidence?: number; language?: string }
interface DocumentEvent { kind: 'document'; text?: string; action?: string; version?: number }
interface ErrorEvent { kind: 'error'; error: string }
interface FlushComplete { kind: 'flush-complete' }
interface PingEvent { kind: 'ping' }
type VoiceEvent = PartialEvent | FinalEvent | DocumentEvent | ErrorEvent | FlushComplete | PingEvent

const getServiceUrl = () => {
  const configured = import.meta.env.VITE_KVIE_STT_URL
  if (configured) return configured
  return `${getServiceBaseUrl().replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')}/ws/transcribe`
}

const getHealthUrl = (serviceUrl: string) => {
  const health = new URL(serviceUrl)
  health.protocol = health.protocol === 'wss:' ? 'https:' : 'http:'
  health.pathname = '/health'
  health.search = ''
  return health.toString()
}

const MIC_PERMISSION_TIMEOUT_MS = 20_000
const SOCKET_OPEN_TIMEOUT_MS = 10_000
const MAX_SOCKET_BUFFERED_BYTES = 512 * 1024

// ── Latency tracking ──────────────────────────────────────────────────────
const toPCM16 = (input: Float32Array) => {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    output[i] = Math.max(-1, Math.min(1, input[i])) * 0x7fff
  }
  return output.buffer
}

export const useLocalStreamingVoice = (enabled = true) => {
  const [isAvailable, setIsAvailable] = useState(false)
  const [serviceConnected, setServiceConnected] = useState(false)
  const [state, setState] = useState({
    isListening: false,
    transcript: '',
    interimTranscript: '',
    latestSegment: '',
    documentText: '',
    action: '',
    error: null as string | null,
  })
  const [audioLevel, setAudioLevel] = useState<number>(0)
  const socketRef = useRef<WebSocket | null>(null)
  const workletRef = useRef<WorkletHandle | null>(null)
  const onAudioDataRef = useRef<((data: ArrayBuffer) => void) | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const finalTranscriptRef = useRef('')
  const lastErrorRef = useRef<string | null>(null)
  const stopRequestedRef = useRef(false)
  const startingRef = useRef(false)
  const pendingFinalProcessingRef = useRef<Promise<void>>(Promise.resolve())
  const flushResolverRef = useRef<(() => void) | null>(null)
  // ── Latency metrics ─────────────────────────────────────────────────────
  const latencyMarkRef = useRef<{ t0: number; t1: number; t2: number } | null>(null)
  const [latencyDisplay, setLatencyDisplay] = useState<string>('')

  // ── Priority event queue & debounce state ────────────────────────────────
  const partialTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingPartialRef = useRef<string>('')
  const processingLockRef = useRef(false)

  useEffect(() => {
    if (!enabled) {
      setServiceConnected(false)
      setIsAvailable(false)
      return
    }

    let disposed = false
    let retryTimer: number | undefined
    let controller: AbortController | undefined

    const checkService = async () => {
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 1500)
      let connected = false
      let modelReady = false
      try {
        const response = await fetch(getHealthUrl(getServiceUrl()), {
          signal: controller.signal,
          cache: 'no-store',
        })
        connected = response.ok
        if (connected) {
          const health = await response.json() as { model_ready?: boolean }
          modelReady = health.model_ready === true
        }
      } catch {
        connected = false
        modelReady = false
      } finally {
        window.clearTimeout(timeout)
      }

      if (disposed) return
      setServiceConnected(connected)
      setIsAvailable(connected && modelReady)
      retryTimer = window.setTimeout(checkService, connected ? 4000 : 1000)
    }

    void checkService()
    return () => {
      disposed = true
      controller?.abort()
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [enabled])

  const cleanup = useCallback(() => {
    stopRequestedRef.current = true
    if (partialTimerRef.current) {
      window.clearTimeout(partialTimerRef.current)
      partialTimerRef.current = null
    }
    pendingPartialRef.current = ''
    flushResolverRef.current?.()
    flushResolverRef.current = null
    workletRef.current?.disconnect()
    workletRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    socketRef.current?.close()
    onAudioDataRef.current = null
    streamRef.current = null
    socketRef.current = null
    setAudioLevel(0)
  }, [])

  // ── Apply grammar pipeline to text (runs on main thread, non-blocking) ──
  const applyGrammar = useCallback(async (text: string): Promise<string> => {
    const grammarEnabled = localStorage.getItem('kvie_grammar_router') !== 'false'
    if (!grammarEnabled) return text
    try {
      return await runGrammarRouter(text, { enabled: true })
    } catch {
      return text
    }
  }, [])

  // ── Process queued events with priority ordering ─────────────────────────
  const processEventQueue = useCallback(async (socket: WebSocket) => {
    if (processingLockRef.current) return
    if (socket.readyState !== WebSocket.OPEN) return
    processingLockRef.current = true

    try {
      // Process pending partial (debounced) first to keep latency low
      if (pendingPartialRef.current) {
        const text = pendingPartialRef.current
        pendingPartialRef.current = ''

        // Don't run grammar on partials — they're noisy and mid-speech,
        // aggressive corrections mangle correct speech. Use raw STT output.
        setState(current => ({
          ...current,
          interimTranscript: mergeRollingText(finalTranscriptRef.current, text),
          error: null,
        }))
      }
    } finally {
      processingLockRef.current = false
    }
  }, [])

  // ── Send compact partial events ─────────────────────────────────────────
  const sendAudio = useCallback((buffer: ArrayBuffer) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return

    if (socket.bufferedAmount + buffer.byteLength > MAX_SOCKET_BUFFERED_BYTES) {
      const message = 'Audio upload is falling behind the network. Dictation stopped to prevent increasing latency; try again on a faster connection.'
      lastErrorRef.current = message
      cleanup()
      setState(current => ({ ...current, isListening: false, error: message }))
      return
    }

    // Compute real-time audio RMS level for UI waveform
    try {
      const pcm = new Int16Array(buffer)
      let sum = 0
      const step = 4
      const count = Math.floor(pcm.length / step)
      for (let i = 0; i < pcm.length; i += step) {
        const norm = pcm[i] / 32768
        sum += norm * norm
      }
      const rms = count > 0 ? Math.sqrt(sum / count) : 0
      // Boost sensitivity for speech RMS
      const level = Math.min(1, Math.max(0, rms * 4.5))
      setAudioLevel(level)
    } catch {
      // ignore
    }

    // Record capture time for latency metric
    if (!latencyMarkRef.current) {
      latencyMarkRef.current = { t0: performance.now(), t1: 0, t2: 0 }
    }
    socket.send(buffer)
  }, [cleanup])

  const startListening = useCallback(async (language?: string) => {
    if (!isAvailable) return false
    // Re-entrancy guard: two rapid hotkey/button events both pass the async
    // isListening check and would create two WebSockets + mic streams, with
    // the first leaked forever.
    if (startingRef.current) return false
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) return false
    startingRef.current = true
    try {
      stopRequestedRef.current = false
      lastErrorRef.current = null
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Microphone capture is unavailable in this runtime. Check Windows microphone privacy settings and restart KVIE.')
      }
      const pendingStream = navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      const stream = await new Promise<MediaStream>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          // getUserMedia cannot be cancelled consistently across WebViews. Stop
          // a stream if permission resolves after this timeout.
          void pendingStream.then(lateStream => lateStream.getTracks().forEach(track => track.stop())).catch(() => {})
          reject(new Error('Microphone permission timed out. Check Windows microphone privacy settings, then retry.'))
        }, MIC_PERMISSION_TIMEOUT_MS)
        pendingStream.then(value => {
          window.clearTimeout(timeout)
          if (stopRequestedRef.current) {
            value.getTracks().forEach(track => track.stop())
            reject(new Error('Microphone start was cancelled.'))
            return
          }
          resolve(value)
        }, error => {
          window.clearTimeout(timeout)
          reject(error)
        })
      })
      // Own the microphone immediately so any later socket/worklet failure
      // reaches cleanup and releases the device.
      streamRef.current = stream
      const socket = new WebSocket(getServiceUrl())
      socket.binaryType = 'arraybuffer'
      // Publish before awaiting the connection so timeout, unmount, and
      // startup cancellation can all close this pending socket.
      socketRef.current = socket

      socket.onmessage = (message) => {
        const event = message.data as string | ArrayBuffer
        if (typeof event !== 'string') return

        let parsed: VoiceEvent
        try {
          parsed = JSON.parse(event) as VoiceEvent
        } catch {
          return
        }

        // Priority handling: final events bypass all debounce
        // Partial events are debounced to reduce re-renders while keeping latency low

        if (parsed.kind === 'final') {
          // Clear any pending partial debounce — final takes priority
          if (partialTimerRef.current) {
            window.clearTimeout(partialTimerRef.current)
            partialTimerRef.current = null
          }
          pendingPartialRef.current = ''

          // ── Client-side grammar pipeline (async IIFE) ──────────────
          pendingFinalProcessingRef.current = pendingFinalProcessingRef.current.then(async () => {
            let grammarText = ''
            try {
              // Strip self-corrections ("meeting at 3, actually 4" -> "4")
              // BEFORE the grammar router sees the text.
              grammarText = await runGrammarRouter(
                stripVerbalBacktracks((parsed as FinalEvent).text ?? ''),
                { enabled: localStorage.getItem('kvie_grammar_router') !== 'false' }
              )
            } catch {
              grammarText = stripVerbalBacktracks((parsed as FinalEvent).text?.trim() ?? '')
            }

            // Latency measurement
            if (latencyMarkRef.current) {
              latencyMarkRef.current.t2 = performance.now()
              const { t0, t2 } = latencyMarkRef.current
              const total = t2 - t0
              setLatencyDisplay(`${total.toFixed(0)}ms → final`)
              setTimeout(() => {
                if (latencyMarkRef.current?.t0 === t0) {
                  latencyMarkRef.current = null
                  setLatencyDisplay('')
                }
              }, 4000)
            }
            const seg = grammarText
            finalTranscriptRef.current = `${finalTranscriptRef.current} ${seg}`.trim()
            setState(current => ({
              ...current,
              transcript: finalTranscriptRef.current,
              latestSegment: seg,
              interimTranscript: '',
              error: null,
            }))
          }).catch(() => {})
        } else if (parsed.kind === 'partial') {
          // ── Latency measurement: first partial only (updating on every
          // partial re-rendered the whole floating window for nothing) ──
          if (latencyMarkRef.current && !latencyMarkRef.current.t1) {
            latencyMarkRef.current.t1 = performance.now()
            const { t0, t1 } = latencyMarkRef.current
            const firstByte = t1 - t0
            setLatencyDisplay(`${firstByte.toFixed(0)}ms → partial`)
            if (t0 > 0 && t1 > 0) {
              setTimeout(() => {
                if (latencyMarkRef.current?.t0 === t0) {
                  latencyMarkRef.current = null
                  setLatencyDisplay('')
                }
              }, 3000)
            }
          }

          // Debounce partial: accumulate but only re-render at ~80ms intervals
          // This keeps perceived latency sub-100ms while reducing re-render overhead
          const rawText = (parsed as PartialEvent).text || ''
          pendingPartialRef.current = rawText

          if (partialTimerRef.current) {
            window.clearTimeout(partialTimerRef.current)
          }

          partialTimerRef.current = window.setTimeout(async () => {
            partialTimerRef.current = null
            if (!pendingPartialRef.current) return

            const text = pendingPartialRef.current
            pendingPartialRef.current = ''

            // Don't run grammar on partials — they're noisy and mid-speech
            const grammarText = text

            // Use mergeRollingText for overlap elimination (prevents word doubling)
            const merged = mergeRollingText(finalTranscriptRef.current, grammarText)

            setState(current => ({
              ...current,
              interimTranscript: merged,
              error: null,
            }))
          }, 80) // 80ms debounce — sub-100ms visual response
        }

        // Non-transcript events (document, error, ping) — no debounce needed
        if (parsed.kind === 'error') {
          if (partialTimerRef.current) {
            window.clearTimeout(partialTimerRef.current)
            partialTimerRef.current = null
            pendingPartialRef.current = ''
          }
          const message = (parsed as ErrorEvent).error || 'Local transcription failed'
          lastErrorRef.current = message
          setState(current => ({ ...current, error: message }))
          // A flush error is terminal for this capture attempt; release the
          // stopListening() waiter so it can stop and clean up the socket.
          flushResolverRef.current?.()
          flushResolverRef.current = null
        }
        if (parsed.kind === 'document') {
          setState(current => ({
            ...current,
            documentText: (parsed as DocumentEvent).text ?? current.documentText,
            action: (parsed as DocumentEvent).action || '',
          }))
        }
        if (parsed.kind === 'flush-complete') {
          flushResolverRef.current?.()
          flushResolverRef.current = null
        }
      }

      socket.onclose = (event) => {
        if (!stopRequestedRef.current) {
          // Server went away mid-dictation: stop capture so the OS mic
          // indicator turns off instead of streaming into a dead socket while
          // the UI already shows "not listening".
          workletRef.current?.disconnect()
          workletRef.current = null
          streamRef.current?.getTracks().forEach(track => track.stop())
          streamRef.current = null
          onAudioDataRef.current = null
          const reason = event.reason || 'Transcription connection closed before the final text arrived.'
          lastErrorRef.current = reason
          setState(current => ({ ...current, error: reason, isListening: false }))
          flushResolverRef.current?.()
          flushResolverRef.current = null
          return
        }
        flushResolverRef.current?.()
      }

      await new Promise<void>((resolve, reject) => {
        const finish = (error?: Error) => {
          window.clearTimeout(timeout)
          socket.removeEventListener('open', onOpen)
          socket.removeEventListener('error', onError)
          socket.removeEventListener('close', onClose)
          if (error) reject(error)
          else resolve()
        }
        const onOpen = () => finish()
        const onError = () => finish(new Error('KVIE transcription service is unavailable'))
        const onClose = () => finish(new Error('KVIE transcription service closed before capture started'))
        const timeout = window.setTimeout(() => {
          socket.close()
          finish(new Error('Timed out connecting to the KVIE transcription service.'))
        }, SOCKET_OPEN_TIMEOUT_MS)
        socket.addEventListener('open', onOpen, { once: true })
        socket.addEventListener('error', onError, { once: true })
        socket.addEventListener('close', onClose, { once: true })
      })

      const sttLanguage = language || localStorage.getItem('kvie_stt_language') || 'auto'
      socket.send(JSON.stringify({ type: 'start', language: sttLanguage }))

      // ── AudioWorklet pipeline ─────────────────────────────────────────────
      // Reset latency markers on new session
      // Publish the socket before starting audio so frames are not dropped
      // while the worklet is being installed or resumed from a global hotkey.
      latencyMarkRef.current = { t0: performance.now(), t1: 0, t2: 0 }

      const worklet = await startAudioWorklet(stream, sendAudio)
      workletRef.current = worklet

      // Override the onAudioData hook — AudioWorklet fires Int16Array here
      setState(current => ({ ...current, isListening: true, error: null }))
      return true
    } catch (cause) {
      cleanup()
      if (cause instanceof Error && cause.message.includes('transcription service is unavailable')) {
        setIsAvailable(false)
      }
      setState(current => ({ ...current, error: cause instanceof Error ? cause.message : String(cause) }))
      return false
    } finally {
      startingRef.current = false
    }
  }, [cleanup, isAvailable, sendAudio])

  const stopListening = useCallback(async () => {
    // Stop capturing immediately on key release, then flush audio already sent to the service.
    workletRef.current?.disconnect()
    workletRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      const flushed = new Promise<void>(resolve => {
        const timeout = window.setTimeout(() => {
          const message = 'Transcription timed out while waiting for the speech model. Try again after the model finishes loading.'
          lastErrorRef.current = message
          // Surface the timeout in the UI, not just the internal ref.
          setState(current => ({ ...current, error: current.error ?? message }))
          flushResolverRef.current = null
          resolve()
        }, 60000)
        flushResolverRef.current = () => {
          window.clearTimeout(timeout)
          flushResolverRef.current = null
          resolve()
        }
      })
      socketRef.current.send(JSON.stringify({ type: 'flush' }))
      await flushed
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        stopRequestedRef.current = true
        socketRef.current.send(JSON.stringify({ type: 'stop' }))
      }
    }
    await pendingFinalProcessingRef.current
    const finalTranscript = finalTranscriptRef.current
    cleanup()
    setState(current => ({ ...current, isListening: false, interimTranscript: '' }))
    return finalTranscript
  }, [cleanup])

  const clearTranscript = useCallback(() => {
    finalTranscriptRef.current = ''
    lastErrorRef.current = null
    latencyMarkRef.current = null
    setLatencyDisplay('')
    setState(current => ({
      ...current,
      transcript: '',
      interimTranscript: '',
      documentText: '',
      action: '',
      error: null,
    }))
  }, [])

  // Ask the backend service to wipe its persisted copy of the document —
  // otherwise a cleared workspace resurrects from the SQLite snapshot on the
  // next dictation.
  const clearServerDocument = useCallback(() => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'clear' }))
    }
  }, [])

  useEffect(() => cleanup, [cleanup])

  return {
    ...state,
    isAvailable,
    serviceConnected,
    isSupported: isAvailable,
    audioLevel,
    latencyDisplay,
    startListening,
    stopListening,
    clearTranscript,
    clearServerDocument,
    getLastError: () => lastErrorRef.current,
    backend: 'faster-whisper' as const,
  }
}
