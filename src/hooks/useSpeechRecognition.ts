import { useCallback, useEffect, useRef, useState } from 'react'
import { isTauri } from '@tauri-apps/api/core'
import { mergeRollingText } from '../lib/incrementalTypingEngine'

interface SpeechRecognitionEventLike extends Event { results: SpeechRecognitionResultList; resultIndex: number }
interface SpeechRecognitionErrorEventLike extends Event { error: string }
interface SpeechRecognitionInstance {
  continuous: boolean
  interimResults: boolean
  lang: string
  onend: (() => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  start: () => void
  stop: () => void
}
interface SpeechRecognitionConstructor { new (): SpeechRecognitionInstance }
type SpeechRecognitionWindow = Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor }

export const useSpeechRecognition = (language = 'en-IN') => {
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const restartRef = useRef(false)
  const [state, setState] = useState({ isListening: false, isSupported: false, transcript: '', interimTranscript: '', latestSegment: '', error: null as string | null })

  useEffect(() => {
    // Warm the mic permission in plain-browser runs only — the desktop app
    // uses the local streaming voice hook and should not prompt at startup.
    if (isTauri()) return
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        stream.getTracks().forEach(track => track.stop())
      }).catch(() => {
        // user denied or no mic
      })
    }
  }, [])

  useEffect(() => {
    const speechWindow = window as SpeechRecognitionWindow
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
    if (!Recognition) return

    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = language
    recognition.onresult = event => {
      let finalText = ''
      let interimText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        if (result.isFinal) finalText += `${result[0].transcript} `
        else interimText += `${result[0].transcript} `
      }
      setState(current => {
        const seg = finalText.trim() || interimText.trim()
        const newTranscript = finalText.trim() ? mergeRollingText(current.transcript, finalText.trim()) : current.transcript
        return {
          ...current,
          transcript: newTranscript,
          latestSegment: seg,
          interimTranscript: interimText.trim(),
          error: null,
        }
      })
    }
    recognition.onerror = event => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        restartRef.current = false
        setState(current => ({ ...current, isListening: false, error: 'Microphone access was denied.' }))
      } else if (event.error !== 'aborted') {
        setState(current => ({ ...current, error: `Voice input error: ${event.error}` }))
      }
    }
    recognition.onend = () => {
      if (restartRef.current) {
        // Brief backoff so a persistently failing recognition service doesn't
        // tight-loop start/stop cycles.
        window.setTimeout(() => {
          if (restartRef.current) {
            try { recognition.start() } catch { /* browser is still closing the previous session */ }
          }
        }, 300)
      } else setState(current => ({ ...current, isListening: false, interimTranscript: '' }))
    }
    recognitionRef.current = recognition
    setState(current => ({ ...current, isSupported: true }))
    return () => { restartRef.current = false; recognition.stop(); recognitionRef.current = null }
  }, [language])

  const startListening = useCallback(() => {
    if (!recognitionRef.current) return
    restartRef.current = true
    setState(current => ({ ...current, isListening: true, error: null }))
    try { recognitionRef.current.start() } catch { /* already active */ }
  }, [])
  const stopListening = useCallback(() => {
    restartRef.current = false
    recognitionRef.current?.stop()
    setState(current => ({ ...current, isListening: false, interimTranscript: '' }))
  }, [])
  const clearTranscript = useCallback(() => setState(current => ({ ...current, transcript: '', interimTranscript: '', error: null })), [])

  return { ...state, audioLevel: 0, startListening, stopListening, clearTranscript }
}
