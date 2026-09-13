import React, { useEffect, useRef, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { useSpeechRecognition } from './hooks/useSpeechRecognition'
import { useLocalStreamingVoice } from './hooks/useLocalStreamingVoice'
import { useAppTheme } from './hooks/useAppTheme'
import { tauriBridge } from './lib/tauriBridge'
import { saveVoiceSession } from './lib/sessionRecorder'
import { runQwenAutoEdit } from './lib/autoEdit'
import { isVoiceCommandIntent, executeVoiceCommand } from './lib/voiceCommandEngine'
import { IncrementalTypingSession, processSpokenVoiceText } from './lib/incrementalTypingEngine'
import { applyCustomDictionary } from './lib/customDictionary'
import { expandVoiceSnippets } from './lib/snippetsEngine'
import { SUPPORTED_LANGUAGES, getTranslationSettings, saveTranslationSettings } from './lib/translationEngine'
import FloatingMicWidget from './components/FloatingMicWidget'

export const FloatingWindowApp: React.FC = () => {
  useAppTheme() // Binds --accent-color, --accent-glow, --accent-subtle dynamically
  const browserSpeech = useSpeechRecognition()
  const localVoice = useLocalStreamingVoice()
  const speech = localVoice.isAvailable ? localVoice : browserSpeech
  const [injectionMessage, setInjectionMessage] = useState<string | null>(null)

  const [isUniversalMode, setIsUniversalMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('kvie_universal_mode')
    return saved !== null ? saved === 'true' : true
  })

  const [isTranslationEnabled, setIsTranslationEnabled] = useState<boolean>(() => getTranslationSettings().isEnabled)
  const [targetLanguage, setTargetLanguage] = useState<string>(() => getTranslationSettings().targetLanguage)

  useEffect(() => {
    const syncTranslation = () => {
      const current = getTranslationSettings()
      setIsTranslationEnabled(current.isEnabled)
      setTargetLanguage(current.targetLanguage)
    }
    window.addEventListener('storage', syncTranslation)
    return () => window.removeEventListener('storage', syncTranslation)
  }, [])

  const handleToggleTranslation = () => {
    const next = !isTranslationEnabled
    setIsTranslationEnabled(next)
    saveTranslationSettings(next, targetLanguage)
  }

  const typingSessionRef = useRef<IncrementalTypingSession>(new IncrementalTypingSession())
  const lastFinalTranscriptRef = useRef('')

  // ── Serialized injection queue to prevent race conditions ──────────────────
  const injectionQueueRef = useRef<Array<() => Promise<void>>>([])
  const isInjectingRef = useRef(false)
  const injectAbortRef = useRef(false)

  const drainInjectionQueue = useCallback(async () => {
    if (isInjectingRef.current) return
    isInjectingRef.current = true
    injectAbortRef.current = false

    while (injectionQueueRef.current.length > 0) {
      if (injectAbortRef.current) break
      const task = injectionQueueRef.current.shift()!
      try {
        await task()
      } catch {
        // individual injection failure — continue with next queued item
      }
    }
    isInjectingRef.current = false
  }, [])

  // Helper: queue an injection so they execute strictly in order
  const queueInjection = useCallback(async (eraseCount: number, appendText: string, message?: string) => {
    return new Promise<void>((resolve, reject) => {
      injectionQueueRef.current.push(async () => {
        if (injectAbortRef.current) { resolve(); return }
        try {
          await tauriBridge.eraseAndInject(eraseCount, appendText)
          if (message) setInjectionMessage(message)
          resolve()
        } catch (err) {
          reject(err instanceof Error ? err : new Error(String(err)))
        }
      })
      void drainInjectionQueue()
    })
  }, [drainInjectionQueue])

  // Cancel all pending injections (called when recording stops)
  const cancelPendingInjections = useCallback(() => {
    injectAbortRef.current = true
    injectionQueueRef.current = []
    isInjectingRef.current = false
  }, [])

  // ── End serialized injection queue ─────────────────────────────────────────

  useEffect(() => {
    document.body.classList.add('floating-window-mode')
    document.documentElement.classList.add('floating-window-mode')
    return () => {
      document.body.classList.remove('floating-window-mode')
      document.documentElement.classList.remove('floating-window-mode')
    }
  }, [])

  useEffect(() => {
    localStorage.setItem('kvie_universal_mode', String(isUniversalMode))
  }, [isUniversalMode])

  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen('toggle_mic_shortcut', () => {
      const isEnabled = localStorage.getItem('kvie_global_hotkey_enabled') !== 'false'
      if (!isEnabled) return

      if (speech.isListening) {
        const fullText = typingSessionRef.current.getFullText()
        if (fullText) {
          void saveVoiceSession(fullText)
        }
        browserSpeech.stopListening()
        if (localVoice.isAvailable) localVoice.stopListening()
        clearAll()
      } else {
        clearAll()
        browserSpeech.startListening()
        if (localVoice.isAvailable) {
          void localVoice.startListening()
        }
      }
    }).then(fn => { unlisten = fn })

    return () => {
      if (unlisten) unlisten()
    }
  }, [speech.isListening, browserSpeech, localVoice])

  const clearAll = () => {
    cancelPendingInjections()
    const fullText = typingSessionRef.current.getFullText()
    if (fullText) {
      void saveVoiceSession(fullText)
    }
    speech.clearTranscript()
    localVoice.clearTranscript()
    browserSpeech.clearTranscript()
    typingSessionRef.current.reset()
    lastFinalTranscriptRef.current = ''
  }

  const [isCommandMode, setIsCommandMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('kvie_command_mode')
    return saved !== null ? saved === 'true' : false
  })

  useEffect(() => {
    localStorage.setItem('kvie_command_mode', String(isCommandMode))
  }, [isCommandMode])

  // Auto-save voice session, execute commands, or finalize buffer whenever recording stops
  useEffect(() => {
    if (!speech.isListening) {
      const fullText = typingSessionRef.current.getFullText()
      if (fullText) {
        typingSessionRef.current.commitCurrent()
        const raw = fullText
        void tauriBridge.getActiveAppContext().then(async ctx => {
          if (isCommandMode || isVoiceCommandIntent(raw)) {
            setInjectionMessage('Executing Voice Command (Qwen2.5)...')
            const cmdResult = await executeVoiceCommand(raw, ctx.surrounding_text, ctx.app_name)
            if (cmdResult.isSuccess) {
              const eraseCount = ctx.surrounding_text.length > 0 ? ctx.surrounding_text.length : raw.length
              await tauriBridge.eraseAndInject(eraseCount, cmdResult.transformedText)
              void saveVoiceSession(`[Command: ${raw}] -> ${cmdResult.transformedText}`, ctx.app_name)
              setInjectionMessage('Voice Command Applied!')
              return
            }
          }

          const cleaned = await runQwenAutoEdit(raw, {
            surroundingText: ctx.surrounding_text,
            targetApp: ctx.app_name,
          })
          void saveVoiceSession(cleaned || raw, ctx.app_name)
        }).catch(() => {
          void saveVoiceSession(raw)
        })
      }
      clearAll()
    }
  }, [speech.isListening, isCommandMode])

  // Smart Incremental Real-time live streaming typing + Custom Dictionary + Snippets + Live Translation
  useEffect(() => {
    if (!isUniversalMode || !speech.isListening) return

    const session = typingSessionRef.current
    const currentFinal = speech.transcript || ''
    const currentInterim = speech.interimTranscript || ''
    const latestSeg = localVoice.latestSegment || ''

    let isCancelled = false

    const markCancelled = () => { isCancelled = true }

    // Case 1: Final segment arrived (e.g. after a pause)
    if (currentFinal && currentFinal !== lastFinalTranscriptRef.current) {
      let newFinalPortion = currentFinal
      if (currentFinal.startsWith(lastFinalTranscriptRef.current)) {
        newFinalPortion = currentFinal.slice(lastFinalTranscriptRef.current.length).trim()
      } else if (latestSeg) {
        newFinalPortion = latestSeg
      }

      lastFinalTranscriptRef.current = currentFinal

      if (newFinalPortion) {
        void (async () => {
          try {
            const processedFinal = await processSpokenVoiceText(newFinalPortion, {
              applyTranslation: isTranslationEnabled,
              targetLanguage,
            })
            if (isCancelled) return

            const delta = session.processSegment(processedFinal, true)
            if (delta.eraseCount > 0 || delta.appendText.length > 0) {
              await queueInjection(delta.eraseCount, delta.appendText, isTranslationEnabled ? 'Translated & typed' : 'Typed & saved')
            }
          } catch (err) {
            if (!isCancelled) setInjectionMessage(err instanceof Error ? err.message : String(err))
          }
        })()
      }
      return markCancelled
    }

    // Case 2: Active Interim speech clause while speaking — synchronous only
    if (currentInterim) {
      try {
        const quickInterim = applyCustomDictionary(expandVoiceSnippets(currentInterim).expandedText)
        const delta = session.processSegment(quickInterim, false)
        if (delta.eraseCount > 0 || delta.appendText.length > 0) {
          // Don't await — queue it so it doesn't block interim updates
          void queueInjection(delta.eraseCount, delta.appendText, 'Typing...')
        }
      } catch {
        // non-fatal interim processing error
      }
    }

    return markCancelled
  }, [speech.interimTranscript, speech.transcript, speech.isListening, localVoice.latestSegment, isUniversalMode, isTranslationEnabled, targetLanguage, queueInjection])


  const handleToggleListening = () => {
    if (speech.isListening) {
      const fullText = typingSessionRef.current.getFullText()
      if (fullText) {
        void saveVoiceSession(fullText)
      }
      speech.stopListening()
      clearAll()
    } else {
      clearAll()
      void speech.startListening()
    }
  }

  const injectDraft = async () => {
    const textToInject = speech.interimTranscript || speech.transcript || localVoice.latestSegment
    if (!textToInject.trim()) return
    const processed = await processSpokenVoiceText(textToInject, {
      applyTranslation: isTranslationEnabled,
      targetLanguage,
    })
    await saveVoiceSession(processed)
    await tauriBridge.eraseAndInject(0, processed)
  }

  return (
    <div
      data-tauri-drag-region
      style={{
        width: 'max-content',
        height: 'max-content',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'transparent',
        overflow: 'visible',
        padding: '4px',
        margin: 'auto',
      }}
    >
      <FloatingMicWidget
        isListening={speech.isListening}
        isSupported={speech.isSupported}
        isUniversalMode={isUniversalMode}
        isCommandMode={isCommandMode}
        isTranslationEnabled={isTranslationEnabled}
        targetLanguageName={SUPPORTED_LANGUAGES.find(l => l.code === targetLanguage)?.name || targetLanguage}
        isDesktop={true}
        isStandalone={true}
        onToggleListening={handleToggleListening}
        onToggleUniversalMode={() => setIsUniversalMode(prev => !prev)}
        onToggleCommandMode={() => setIsCommandMode(prev => !prev)}
        onToggleTranslation={handleToggleTranslation}
        onInjectCurrentText={() => void injectDraft()}
        onClearText={clearAll}
        interimTranscript={speech.interimTranscript}
        recentTranscript={speech.transcript || localVoice.latestSegment}
        statusMessage={injectionMessage}
      />
    </div>
  )
}

export default FloatingWindowApp
