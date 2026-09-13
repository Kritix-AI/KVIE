import { useCallback, useEffect, useRef, useState } from 'react'

import { runGrammarRouter } from '../lib/grammarRouter'
import { mergeRollingText } from '../lib/incrementalTypingEngine'
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

const SERVICE_URL = import.meta.env.VITE_KVIE_STT_URL || 'ws://127.0.0.1:8765/ws/transcribe'
const HEALTH_URL = SERVICE_URL.replace(/^ws/, 'http').replace(/\/ws\/transcribe$/, '/health')

// ── Latency tracking ──────────────────────────────────────────────────────
const toPCM16 = (input: Float32Array) => {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    output[i] = Math.max(-1, Math.min(1, input[i])) * 0x7fff
  }
  return output.buffer
}

export const useLocalStreamingVoice = () => {
  const [isAvailable, setIsAvailable] = useState(false)
  const [state, setState] = useState({
    isListening: false,
    transcript: '',
    interimTranscript: '',
    latestSegment: '',
    documentText: '',
    action: '',
    error: null as string | null,
  })
  const socketRef = useRef<WebSocket | null>(null)
  const workletRef = useRef<WorkletHandle | null>(null)
  const onAudioDataRef = useRef<((data: ArrayBuffer) => void) | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const finalTranscriptRef = useRef('')
  const flushResolverRef = useRef<(() => void) | null>(null)
  // ── Latency metrics ─────────────────────────────────────────────────────
  const latencyMarkRef = useRef<{ t0: number; t1: number; t2: number } | null>(null)
  const [latencyDisplay, setLatencyDisplay] = useState<string>('')

  // ── Priority event queue & debounce state ────────────────────────────────
  const partialTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingPartialRef = useRef<string>('')
  const processingLockRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 500)
    fetch(HEALTH_URL, { signal: controller.signal })
      .then(r => { if (r.ok) setIsAvailable(true) })
      .catch(() => { })
      .finally(() => window.clearTimeout(timeout))
    return () => controller.abort()
  }, [])

  const cleanup = useCallback(() => {
    workletRef.current?.disconnect()
    workletRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    socketRef.current?.close()
    onAudioDataRef.current = null
    streamRef.current = null
    socketRef.current = null
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

    // Record capture time for latency metric
    if (!latencyMarkRef.current) {
      latencyMarkRef.current = { t0: performance.now(), t1: 0, t2: 0 }
    }
    socket.send(buffer)
  }, [])

  const startListening = useCallback(async () => {
    if (!isAvailable) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      const socket = new WebSocket(SERVICE_URL)
      socket.binaryType = 'arraybuffer'

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
          ;(async () => {
            let grammarText = ''
            try {
              grammarText = await runGrammarRouter(
                (parsed as FinalEvent).text?.trim() ?? '',
                { enabled: localStorage.getItem('kvie_grammar_router') !== 'false' }
              )
            } catch {
              grammarText = (parsed as FinalEvent).text?.trim() ?? ''
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
          })()
        } else if (parsed.kind === 'partial') {
          // ── Latency measurement: first partial arrives ──
          if (latencyMarkRef.current) {
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
          setState(current => ({ ...current, error: (parsed as ErrorEvent).error || 'Local transcription failed' }))
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

      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve()
        socket.onerror = () => reject(new Error('KVIE transcription service is unavailable'))
      })

      socket.send(JSON.stringify({ type: 'start', language: 'auto' }))

      // ── AudioWorklet pipeline ─────────────────────────────────────────────
      // Reset latency markers on new session
      latencyMarkRef.current = { t0: performance.now(), t1: 0, t2: 0 }

      const worklet = await startAudioWorklet(stream)
      workletRef.current = worklet

      // Override the onAudioData hook — AudioWorklet fires Int16Array here
      // We just pass the raw ArrayBuffer to the WebSocket
      ;(worklet as unknown as { onAudioData?: (data: ArrayBuffer) => void }).onAudioData = (data: ArrayBuffer) => {
        sendAudio(data)
      }

      streamRef.current = stream
      socketRef.current = socket
      setState(current => ({ ...current, isListening: true, error: null }))
    } catch (cause) {
      cleanup()
      setState(current => ({ ...current, error: cause instanceof Error ? cause.message : String(cause) }))
    }
  }, [cleanup, isAvailable, sendAudio])

  const stopListening = useCallback(async () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      const flushed = new Promise<void>(resolve => {
        flushResolverRef.current = resolve
        window.setTimeout(() => { flushResolverRef.current?.(); flushResolverRef.current = null; resolve() }, 10000)
      })
      socketRef.current.send(JSON.stringify({ type: 'flush' }))
      await flushed
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: 'stop' }))
      }
    }
    cleanup()
    setState(current => ({ ...current, isListening: false, interimTranscript: '' }))
  }, [cleanup])

  const clearTranscript = useCallback(() => {
    finalTranscriptRef.current = ''
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

  useEffect(() => cleanup, [cleanup])

  return {
    ...state,
    isAvailable,
    isSupported: isAvailable,
    latencyDisplay,
    startListening,
    stopListening,
    clearTranscript,
    backend: 'faster-whisper' as const,
  }
}
