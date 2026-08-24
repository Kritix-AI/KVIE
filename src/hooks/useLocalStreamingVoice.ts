import { useCallback, useEffect, useRef, useState } from 'react'

import { mergeRollingText } from '../lib/incrementalTypingEngine'

interface VoiceEvent { kind: string; text?: string; language?: string; confidence?: number; error?: string; action?: string }

const SERVICE_URL = import.meta.env.VITE_KVIE_STT_URL || 'ws://127.0.0.1:8765/ws/transcribe'
const HEALTH_URL = SERVICE_URL.replace(/^ws/, 'http').replace(/\/ws\/transcribe$/, '/health')


const downsample = (input: Float32Array, inputRate: number, outputRate: number) => {
  if (inputRate === outputRate) return input
  const ratio = inputRate / outputRate
  const outputLength = Math.round(input.length / ratio)
  const output = new Float32Array(outputLength)
  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio)
    const end = Math.min(Math.floor((index + 1) * ratio), input.length)
    let total = 0
    for (let source = start; source < end; source += 1) total += input[source]
    output[index] = total / Math.max(1, end - start)
  }
  return output
}

const toPCM16 = (input: Float32Array) => {
  const output = new Int16Array(input.length)
  for (let index = 0; index < input.length; index += 1) output[index] = Math.max(-1, Math.min(1, input[index])) * 0x7fff
  return output.buffer
}

export const useLocalStreamingVoice = () => {
  const [isAvailable, setIsAvailable] = useState(false)
  const [state, setState] = useState({ isListening: false, transcript: '', interimTranscript: '', latestSegment: '', documentText: '', action: '', error: null as string | null })
  const socketRef = useRef<WebSocket | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const finalTranscriptRef = useRef('')
  const flushResolverRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 500)
    fetch(HEALTH_URL, { signal: controller.signal }).then(response => { if (response.ok) setIsAvailable(true) }).catch(() => { }).finally(() => window.clearTimeout(timeout))
    return () => controller.abort()
  }, [])

  const cleanup = useCallback(() => {
    processorRef.current?.disconnect()
    contextRef.current?.close()
    streamRef.current?.getTracks().forEach(track => track.stop())
    socketRef.current?.close()
    processorRef.current = null
    contextRef.current = null
    streamRef.current = null
    socketRef.current = null
  }, [])

  const startListening = useCallback(async () => {
    if (!isAvailable) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      const socket = new WebSocket(SERVICE_URL)
      socket.binaryType = 'arraybuffer'
      socket.onmessage = message => {
        const event = JSON.parse(message.data) as VoiceEvent
        if (event.kind === 'partial') setState(current => ({ ...current, interimTranscript: mergeRollingText(finalTranscriptRef.current, event.text || ''), error: null }))
        if (event.kind === 'final') {
          const seg = (event.text || '').trim()
          finalTranscriptRef.current = `${finalTranscriptRef.current} ${seg}`.trim()
          setState(current => ({ ...current, transcript: finalTranscriptRef.current, latestSegment: seg, interimTranscript: '', error: null }))
        }
        if (event.kind === 'error') setState(current => ({ ...current, error: event.error || 'Local transcription failed' }))
        if (event.kind === 'document') setState(current => ({ ...current, documentText: event.text ?? current.documentText, action: event.action || '' }))
        if (event.kind === 'flush-complete') { flushResolverRef.current?.(); flushResolverRef.current = null }
      }
      await new Promise<void>((resolve, reject) => { socket.onopen = () => resolve(); socket.onerror = () => reject(new Error('KVIE transcription service is unavailable')) })
      socket.send(JSON.stringify({ type: 'start', language: 'auto' }))
      const context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const processor = context.createScriptProcessor(1024, 1, 1)
      processor.onaudioprocess = event => { if (socket.readyState === WebSocket.OPEN) socket.send(toPCM16(downsample(event.inputBuffer.getChannelData(0), context.sampleRate, 16000))) }
      source.connect(processor)
      processor.connect(context.destination)
      streamRef.current = stream; socketRef.current = socket; contextRef.current = context; processorRef.current = processor
      setState(current => ({ ...current, isListening: true, error: null }))
    } catch (cause) {
      cleanup()
      setState(current => ({ ...current, error: cause instanceof Error ? cause.message : String(cause) }))
    }
  }, [cleanup, isAvailable])

  const stopListening = useCallback(async () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      const flushed = new Promise<void>(resolve => {
        flushResolverRef.current = resolve
        window.setTimeout(() => { flushResolverRef.current?.(); flushResolverRef.current = null; resolve() }, 10000)
      })
      socketRef.current.send(JSON.stringify({ type: 'flush' }))
      await flushed
      if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'stop' }))
    }
    cleanup()
    setState(current => ({ ...current, isListening: false, interimTranscript: '' }))
  }, [cleanup])

  const clearTranscript = useCallback(() => { finalTranscriptRef.current = ''; setState(current => ({ ...current, transcript: '', interimTranscript: '', documentText: '', action: '', error: null })) }, [])

  useEffect(() => cleanup, [cleanup])
  return { ...state, isAvailable, isSupported: isAvailable, startListening, stopListening, clearTranscript, backend: 'faster-whisper' as const }
}
