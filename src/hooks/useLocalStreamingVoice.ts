import { useCallback, useEffect, useRef, useState } from 'react'

import { mergeRollingText } from '../lib/incrementalTypingEngine'

interface VoiceEvent { kind: string; text?: string; language?: string; confidence?: number; error?: string; action?: string }

const SERVICE_URL = import.meta.env.VITE_KVIE_STT_URL || 'ws://127.0.0.1:8765/ws/transcribe'
const HEALTH_URL = SERVICE_URL.replace(/^ws/, 'http').replace(/\/ws\/transcribe$/, '/health')


const downsample = (input: Float32Array, inputRate: number, outputRate: number) => {
  if (inputRate === outputRate) return input
  const ratio = inputRate / outputRate
  if (ratio > 1) {
    // Anti-aliasing: low-pass filter at Nyquist of output rate, then decimate
    const cutoff = Math.min(1 / ratio, 0.5)
    const outputLength = Math.round(input.length / ratio)
    const output = new Float32Array(outputLength)
    // Simple 3-tap FIR low-pass (windowed sinc approximation)
    const tapRadius = 2
    const taps: number[] = []
    for (let i = -tapRadius; i <= tapRadius; i++) {
      const x = i
      const w = 0.5 * (1 + Math.cos((Math.PI * x) / (tapRadius + 1))) // Hamming window
      const sinc = x === 0 ? 1 : Math.sin(2 * Math.PI * cutoff * x) / (2 * Math.PI * cutoff * x)
      taps.push(sinc * w)
    }
    const tapSum = taps.reduce((a, b) => a + b, 0)
    const normalized = taps.map(t => t / tapSum)

    for (let i = 0; i < outputLength; i++) {
      const srcCenter = i * ratio
      let total = 0
      for (let j = -tapRadius; j <= tapRadius; j++) {
        const srcIdx = Math.round(srcCenter + j)
        if (srcIdx >= 0 && srcIdx < input.length) {
          total += input[srcIdx] * normalized[j + tapRadius]
        }
      }
      output[i] = total
    }
    return output
  }
  // Upsampling (shouldn't happen for mic → 16kHz)
  const outputLength = Math.round(input.length * ratio)
  const output = new Float32Array(outputLength)
  for (let i = 0; i < outputLength; i++) {
    const srcIdx = Math.floor(i / ratio)
    output[i] = srcIdx < input.length ? input[srcIdx] : 0
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

    const connect = async (retriesLeft = 3): Promise<void> => {
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
        if (retriesLeft > 0) {
          await new Promise(r => setTimeout(r, 800))
          return connect(retriesLeft - 1)
        }
        cleanup()
        setState(current => ({ ...current, error: cause instanceof Error ? cause.message : String(cause), isListening: false }))
      }
    }

    await connect(3)
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
