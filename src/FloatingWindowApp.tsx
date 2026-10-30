import React, { useEffect, useRef, useState } from 'react'
import { isTauri } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { useSpeechRecognition } from './hooks/useSpeechRecognition'
import { useLocalStreamingVoice } from './hooks/useLocalStreamingVoice'
import { useAppTheme } from './hooks/useAppTheme'
import { tauriBridge } from './lib/tauriBridge'
import { saveVoiceSession } from './lib/sessionRecorder'
import { runQwenAutoEdit } from './lib/autoEdit'
import { isVoiceCommandIntent, executeVoiceCommand } from './lib/voiceCommandEngine'
import { IncrementalTypingSession, toGraphemes } from './lib/incrementalTypingEngine'
import { applyCustomDictionary } from './lib/customDictionary'
import { expandVoiceSnippets } from './lib/snippetsEngine'
import { consensusTranscription } from './lib/consensusEngine'
import { stripVerbalBacktracks } from './lib/backtrackStripper'
import { SUPPORTED_LANGUAGES, getTranslationSettings, saveTranslationSettings } from './lib/translationEngine'
import FloatingMicWidget from './components/FloatingMicWidget'

export const FloatingWindowApp: React.FC = () => {
  useAppTheme() // Binds --accent-color, --accent-glow, --accent-subtle dynamically
  const browserSpeech = useSpeechRecognition()
  const localVoice = useLocalStreamingVoice()
  const speech = localVoice.isAvailable || isTauri() ? localVoice : browserSpeech

  const [injectionMessage, setInjectionMessage] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

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

  const typingSessionRef = useRef<IncrementalTypingSession | null>(null)
  const getTypingSession = (): IncrementalTypingSession => {
    if (!typingSessionRef.current) typingSessionRef.current = new IncrementalTypingSession()
    return typingSessionRef.current
  }
  const lastFinalTranscriptRef = useRef('')
  const lastProcessedFinalRef = useRef('')
  const lastProcessedInterimRef = useRef('')
  const pushToTalkActiveRef = useRef(false)
  const pushToTalkFinalizingRef = useRef(false)
  const pushToTalkStartPromiseRef = useRef<Promise<boolean> | null>(null)
  const pushToTalkReleasePendingRef = useRef(false)
  const pushToTalkHandlersRef = useRef<{ start: () => Promise<void>; stop: () => Promise<void> }>({
    start: async () => {},
    stop: async () => {},
  })
  const toggleListeningRef = useRef<() => Promise<void>>(async () => {})
  const injectQueueRef = useRef<Promise<void>>(Promise.resolve())

  const enqueueRawInject = (eraseCount: number, text: string, verify = false): Promise<void> => {
    if (typeof window !== 'undefined' && localStorage.getItem('kvie_trace_stages') === 'true') {
      console.log('[STAGE 5: TAURI INJECTION QUEUED]', { eraseCount, appendText: text, verify })
    }
    const run = async () => {
      try {
        const outcome = await tauriBridge.eraseAndInject(eraseCount, text, verify)
        if (verify && outcome.verification === 'unverified') {
          setInjectionMessage('Applied, but KVIE could not verify the paste — check the target app.')
        }
      } catch (err) {
        console.warn('Raw inject error:', err)
      }
    }
    const queued = injectQueueRef.current.then(run, run)
    injectQueueRef.current = queued.catch(() => {})
    return queued
  }

  const [isConsensusMode, setIsConsensusMode] = useState(false)
  const [consensusDraft, setConsensusDraft] = useState<string | null>(null)
  const [consensusCount, setConsensusCount] = useState(0)
  const consensusRef = useRef<string[]>([])

  useEffect(() => {
    localStorage.setItem('kvie_consensus_mode', String(isConsensusMode))
  }, [isConsensusMode])

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
    void tauriBridge.centerTopNotch().catch(() => {})
    const timer = setTimeout(() => {
      void tauriBridge.centerTopNotch().catch(() => {})
    }, 60)
    return () => clearTimeout(timer)
  }, [])

  const [isCommandMode, setIsCommandMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('kvie_command_mode')
    return saved !== null ? saved === 'true' : false
  })

  useEffect(() => {
    localStorage.setItem('kvie_command_mode', String(isCommandMode))
  }, [isCommandMode])

  const clearAll = (skipSave = false) => {
    const fullText = getTypingSession().getFullText()
    if (fullText && !skipSave) {
      void saveVoiceSession(fullText)
    }
    speech.clearTranscript()
    localVoice.clearTranscript()
    browserSpeech.clearTranscript()
    getTypingSession().reset()
    lastFinalTranscriptRef.current = ''
    lastProcessedFinalRef.current = ''
    lastProcessedInterimRef.current = ''
  }

  /**
   * Wispr Flow-style Unified Pipeline:
   * 1. Query active target app context without stealing focus
   * 2. Execute voice commands (Qwen2.5) if active or intent detected
   * 3. Natural language polish: strip verbal backtracks, expand snippets, apply custom dictionary & Qwen auto-edit
   * 4. Single atomic injection into target app
   * 5. Record session history and show quick success feedback
   */
  const processAndInjectFinal = async (rawInput: string, appSource = 'Floating Mic') => {
    const raw = rawInput.trim()
    if (!raw) {
      setInjectionMessage(localVoice.getLastError() || 'No speech detected. Speak clearly into the microphone.')
      return
    }

    setIsProcessing(true)
    setInjectionMessage('Polishing…')

    try {
      // Drain any queued live typing injections before checking final state
      await injectQueueRef.current

      const ctx = await tauriBridge.getActiveAppContext().catch(() => null)
      const appName = ctx?.app_name || appSource
      const liveTyped = getTypingSession().getFullText()

      // ── Step 1: Voice Command Mode / Intent ────────────────────────────────
      if (isCommandMode || isVoiceCommandIntent(raw)) {
        setInjectionMessage('Executing Voice Command…')
        // Erase any raw command words that were typed live into the target app
        if (liveTyped && isUniversalMode) {
          const liveGraphemeCount = toGraphemes(liveTyped).length
          if (liveGraphemeCount > 0) {
            await enqueueRawInject(liveGraphemeCount, '', false)
          }
        }
        const cmdResult = await executeVoiceCommand(raw, ctx?.surrounding_text || '', ctx?.app_name)
        if (cmdResult.isSuccess) {
          if (isUniversalMode) {
            await enqueueRawInject(0, cmdResult.transformedText, true)
          } else {
            await navigator.clipboard.writeText(cmdResult.transformedText).catch(() => {})
          }
          void saveVoiceSession(`[Command: ${raw}] -> ${cmdResult.transformedText}`, appName)
          setIsProcessing(false)
          setIsSuccess(true)
          setSuccessMessage('Voice Command Applied!')
          setTimeout(() => {
            setIsSuccess(false)
            setSuccessMessage(null)
            setInjectionMessage(null)
          }, 1400)
          return
        }
      }

      // ── Step 2: Natural Language Polish & Translation ────────────────────
      const stripped = stripVerbalBacktracks(raw)
      let cleaned = await runQwenAutoEdit(stripped, {
        surroundingText: ctx?.surrounding_text,
        targetApp: ctx?.app_name,
      })

      if (!cleaned || !cleaned.trim()) {
        cleaned = applyCustomDictionary(expandVoiceSnippets(stripped).expandedText)
      }

      if (!cleaned.trim()) {
        setIsProcessing(false)
        return
      }

      // ── Step 3: Single Atomic Injection / Live Reconciliation ─────────────
      let pasteSuccess = true
      if (isUniversalMode) {
        try {
          const liveClean = liveTyped.trim()
          const finalClean = cleaned.trim()

          if (liveClean && liveClean === finalClean) {
            // Text was already injected live in real time as user spoke — avoid duplicate typing!
            pasteSuccess = true
          } else if (liveClean) {
            const liveGraphemes = toGraphemes(liveTyped)
            const finalGraphemes = toGraphemes(cleaned)
            let commonPrefixLen = 0
            const minLen = Math.min(liveGraphemes.length, finalGraphemes.length)
            while (commonPrefixLen < minLen && liveGraphemes[commonPrefixLen] === finalGraphemes[commonPrefixLen]) {
              commonPrefixLen += 1
            }
            const eraseCount = liveGraphemes.length - commonPrefixLen
            const suffix = finalGraphemes.slice(commonPrefixLen).join('')
            if (eraseCount > 0 || suffix) {
              const isMinorDelta = commonPrefixLen > 0 && eraseCount <= 10
              await enqueueRawInject(eraseCount, suffix, !isMinorDelta)
            }
            pasteSuccess = true
          } else {
            // No live text typed (e.g. initial injection)
            await enqueueRawInject(0, cleaned, true)
          }
        } catch (pasteErr) {
          pasteSuccess = false
          const reason = pasteErr instanceof Error ? pasteErr.message : String(pasteErr)
          try {
            await navigator.clipboard.writeText(cleaned)
            setInjectionMessage(`Could not paste into ${appName} (${reason}). Copied to clipboard!`)
          } catch {
            setInjectionMessage(`Could not paste into ${appName}: ${reason}`)
          }
        }
      } else {
        await navigator.clipboard.writeText(cleaned).catch(() => {})
      }

      // ── Step 4: Save to Voice Session History ─────────────────────────────
      void saveVoiceSession(cleaned, appName)

      // ── Step 5: Visual Feedback ───────────────────────────────────────────
      setIsProcessing(false)
      if (pasteSuccess) {
        setIsSuccess(true)
        const label = isUniversalMode ? `Pasted into ${appName}` : 'Copied to clipboard'
        setSuccessMessage(label)
        setInjectionMessage(label)
        setTimeout(() => {
          setIsSuccess(false)
          setSuccessMessage(null)
          setInjectionMessage(null)
        }, 1400)
      }
    } catch (error) {
      setIsProcessing(false)
      setInjectionMessage(error instanceof Error ? error.message : String(error))
    }
  }

  const [isContinuousMode, setIsContinuousMode] = useState(false)

  const handleCancelListening = async () => {
    if (speech.isListening) {
      try {
        await speech.stopListening()
      } catch {}
    }
    pushToTalkActiveRef.current = false
    setIsContinuousMode(false)
    const liveTyped = getTypingSession().getFullText()
    if (liveTyped && isUniversalMode) {
      const liveGraphemes = toGraphemes(liveTyped).length
      if (liveGraphemes > 0) {
        void enqueueRawInject(liveGraphemes, '', false)
      }
    }
    clearAll(true)
    setInjectionMessage(null)
    setIsProcessing(false)
    void tauriBridge.resetHotkeyState().catch(() => {})
  }

  const startPushToTalk = async () => {
    if (pushToTalkActiveRef.current || localStorage.getItem('kvie_global_hotkey_enabled') === 'false') return
    if (!localVoice.isAvailable) {
      setInjectionMessage('Voice input unavailable. Check the STT service and selected model.')
      return
    }
    if (localVoice.isListening) {
      setInjectionMessage('Stop the current recording before using push-to-talk.')
      return
    }

    clearAll(true)
    pushToTalkActiveRef.current = true
    pushToTalkFinalizingRef.current = false
    pushToTalkReleasePendingRef.current = false
    setIsContinuousMode(false)
    setInjectionMessage('Push to talk')
    const startPromise = localVoice.startListening()
    pushToTalkStartPromiseRef.current = startPromise
    const started = await startPromise
    pushToTalkStartPromiseRef.current = null
    if (!started) {
      pushToTalkActiveRef.current = false
      setInjectionMessage('Microphone did not start. Check microphone permission and the STT service.')
      return
    }
    if (pushToTalkReleasePendingRef.current) {
      pushToTalkReleasePendingRef.current = false
      void pushToTalkHandlersRef.current.stop()
    }
  }

  const stopPushToTalk = async () => {
    if (!pushToTalkActiveRef.current) return
    if (pushToTalkStartPromiseRef.current) {
      pushToTalkReleasePendingRef.current = true
      await pushToTalkStartPromiseRef.current
      if (pushToTalkFinalizingRef.current || !pushToTalkActiveRef.current) return
    }
    if (pushToTalkFinalizingRef.current) return
    pushToTalkFinalizingRef.current = true
    try {
      const raw = await localVoice.stopListening()
      pushToTalkActiveRef.current = false
      await processAndInjectFinal(raw, 'Push to Talk')
    } catch (error) {
      setInjectionMessage(error instanceof Error ? error.message : String(error))
    } finally {
      pushToTalkActiveRef.current = false
      setIsContinuousMode(false)
      clearAll(true)
      pushToTalkFinalizingRef.current = false
    }
  }

  const handleToggleListening = async () => {
    if (speech.isListening) {
      if (pushToTalkFinalizingRef.current) return
      pushToTalkFinalizingRef.current = true
      try {
        const result = await speech.stopListening()
        const raw = (typeof result === 'string' && result.trim())
          ? result
          : (speech.transcript || speech.interimTranscript || '')
        await processAndInjectFinal(raw, 'Floating Mic')
      } catch (error) {
        setInjectionMessage(error instanceof Error ? error.message : String(error))
      } finally {
        setIsContinuousMode(false)
        clearAll(true)
        pushToTalkFinalizingRef.current = false
      }
    } else {
      clearAll(true)
      setIsContinuousMode(true)
      setInjectionMessage('Continuous listening')
      const started = await speech.startListening()
      if (started === false) {
        setIsContinuousMode(false)
        setInjectionMessage(localVoice.getLastError() || 'Microphone could not start. Check its permission and the STT service.')
      }
    }
  }

  pushToTalkHandlersRef.current = { start: startPushToTalk, stop: stopPushToTalk }
  toggleListeningRef.current = handleToggleListening

  // ── Global Hotkey Listeners ────────────────────────────────────────────────
  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen('toggle_mic_shortcut', () => {
      const isEnabled = localStorage.getItem('kvie_global_hotkey_enabled') !== 'false'
      if (!isEnabled) return
      void toggleListeningRef.current()
    }).then(fn => { unlisten = fn })

    return () => {
      if (unlisten) unlisten()
    }
  }, [])

  useEffect(() => {
    let unlistenStart: (() => void) | undefined
    let unlistenStop: (() => void) | undefined
    let unlistenMode: (() => void) | undefined
    void listen('push_to_talk_start', () => {
      setIsContinuousMode(false)
      void pushToTalkHandlersRef.current.start()
    }).then(unlisten => { unlistenStart = unlisten })
    void listen('push_to_talk_stop', () => {
      setIsContinuousMode(false)
      void pushToTalkHandlersRef.current.stop()
    }).then(unlisten => { unlistenStop = unlisten })
    void listen<string>('push_to_talk_mode', (event) => {
      // Double-tap Alt+` switches the running session to continuous listening —
      // the microphone stays on hands-free.
      if (event.payload === 'continuous') {
        setIsContinuousMode(true)
        setInjectionMessage('Continuous listening')
      }
    }).then(unlisten => { unlistenMode = unlisten })
    return () => {
      unlistenStart?.()
      unlistenStop?.()
      unlistenMode?.()
    }
  }, [])

  // ── Real-Time Incremental Typing Coordinator ─────────────────────────────
  // Bridges incoming streaming speech segments (partials and finals) to the
  // IncrementalTypingSession and dispatches low-latency keystroke/paste deltas
  // to the active external app via tauriBridge.eraseAndInject.
  useEffect(() => {
    if (!speech.isListening || !isUniversalMode || isConsensusMode || isCommandMode) {
      return
    }

    const currentFinal = (speech.transcript || '').trim()
    const currentInterim = (speech.interimTranscript || '').trim()

    // 1. Process finalized sentence segment first (commits and anchors)
    if (currentFinal && currentFinal !== lastProcessedFinalRef.current) {
      lastProcessedFinalRef.current = currentFinal
      lastProcessedInterimRef.current = '' // Reset interim tracking for clean continuation

      const delta = getTypingSession().processSegment(currentFinal, true)
      if (delta.eraseCount > 0 || delta.appendText) {
        void enqueueRawInject(delta.eraseCount, delta.appendText, false)
      }
      return
    }

    // 2. Process streaming interim partials (dynamic real-time writing)
    if (currentInterim && currentInterim !== lastProcessedInterimRef.current) {
      lastProcessedInterimRef.current = currentInterim

      const delta = getTypingSession().processSegment(currentInterim, false)
      if (delta.eraseCount > 0 || delta.appendText) {
        void enqueueRawInject(delta.eraseCount, delta.appendText, false)
      }
    }
  }, [
    speech.isListening,
    speech.transcript,
    speech.interimTranscript,
    isUniversalMode,
    isConsensusMode,
    isCommandMode,
  ])

  // ── Consensus Mode Multi-Take Collection ───────────────────────────────────
  useEffect(() => {
    if (!speech.isListening || !isConsensusMode) return
    const currentFinal = speech.transcript || ''
    const latestSeg = localVoice.latestSegment || ''
    const base = lastFinalTranscriptRef.current

    if (currentFinal && currentFinal !== base) {
      const portion = currentFinal.startsWith(base) && base
        ? currentFinal.slice(base.length).trim()
        : (latestSeg || currentFinal)
      lastFinalTranscriptRef.current = currentFinal
      if (portion) {
        const next = [...consensusRef.current, portion]
        consensusRef.current = next
        setConsensusCount(next.length)
        setInjectionMessage(`Recording #${next.length} — speak again (2-3x)`)
      }
    }
  }, [speech.transcript, speech.isListening, localVoice.latestSegment, isConsensusMode])

  const handleConsensusToggle = () => {
    if (!isConsensusMode) {
      consensusRef.current = []
      setConsensusCount(0)
      setConsensusDraft(null)
      setIsConsensusMode(true)
    }
  }

  const handleConsensusComplete = () => {
    if (consensusRef.current.length < 2) {
      setInjectionMessage('Need at least 2 recordings for consensus')
      setTimeout(() => setInjectionMessage(null), 3000)
      return
    }
    if (speech.isListening) {
      void speech.stopListening()
    }
    const result = consensusTranscription(consensusRef.current)
    setConsensusDraft(result)
    setConsensusCount(0)
    consensusRef.current = []
    setIsConsensusMode(false)
    void enqueueRawInject(0, result)
      .then(() => {
        setIsSuccess(true)
        setSuccessMessage('Consensus typed!')
        setTimeout(() => {
          setIsSuccess(false)
          setSuccessMessage(null)
        }, 1400)
      })
      .catch(() => {
        setInjectionMessage('Consensus ready — copied to clipboard')
        navigator.clipboard.writeText(result).catch(() => {})
        setTimeout(() => setInjectionMessage(null), 3000)
      })
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        background: 'transparent',
        overflow: 'visible',
        padding: 0,
        margin: 0,
      }}
    >
      <FloatingMicWidget
        isListening={speech.isListening}
        isSupported={speech.isSupported}
        isUniversalMode={isUniversalMode}
        isCommandMode={isCommandMode}
        isTranslationEnabled={isTranslationEnabled}
        isConsensusMode={isConsensusMode}
        consensusCount={consensusCount}
        targetLanguageName={SUPPORTED_LANGUAGES.find(l => l.code === targetLanguage)?.name || targetLanguage}
        audioLevel={localVoice.audioLevel || 0}
        isProcessing={isProcessing}
        isSuccess={isSuccess}
        successMessage={successMessage}
        onToggleListening={handleToggleListening}
        onToggleUniversalMode={() => setIsUniversalMode(prev => !prev)}
        onToggleCommandMode={() => setIsCommandMode(prev => !prev)}
        onToggleTranslation={handleToggleTranslation}
        onToggleConsensus={handleConsensusToggle}
        onConsensusComplete={handleConsensusComplete}
        onClearText={clearAll}
        onCancelListening={handleCancelListening}
        isContinuousListening={isContinuousMode}
        interimTranscript={speech.interimTranscript}
        recentTranscript={speech.transcript || localVoice.latestSegment}
        statusMessage={injectionMessage}
      />
    </div>
  )
}

export default FloatingWindowApp
