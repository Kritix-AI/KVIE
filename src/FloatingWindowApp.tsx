import React, { useEffect, useRef, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { useSpeechRecognition } from './hooks/useSpeechRecognition'
import { useLocalStreamingVoice } from './hooks/useLocalStreamingVoice'
import { useAppTheme } from './hooks/useAppTheme'
import { tauriBridge } from './lib/tauriBridge'
import { saveVoiceSession } from './lib/sessionRecorder'
import { runQwenAutoEdit } from './lib/autoEdit'
import { isVoiceCommandIntent, executeVoiceCommand } from './lib/voiceCommandEngine'
import { IncrementalTypingSession } from './lib/incrementalTypingEngine'
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

  const typingSessionRef = useRef<IncrementalTypingSession>(new IncrementalTypingSession())
  const lastFinalTranscriptRef = useRef('')

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

  // Smart Incremental Real-time live streaming typing + tail word overlap analysis
  useEffect(() => {
    if (!isUniversalMode || !speech.isListening) return

    const session = typingSessionRef.current
    const currentFinal = speech.transcript || ''
    const currentInterim = speech.interimTranscript || ''
    const latestSeg = localVoice.latestSegment || ''

    // Case 1: Final segment arrived (e.g. after a pause)
    if (currentFinal && currentFinal !== lastFinalTranscriptRef.current) {
      // Find the new portion of finalized transcript
      let newFinalPortion = currentFinal
      if (currentFinal.startsWith(lastFinalTranscriptRef.current)) {
        newFinalPortion = currentFinal.slice(lastFinalTranscriptRef.current.length).trim()
      } else if (latestSeg) {
        newFinalPortion = latestSeg
      }

      lastFinalTranscriptRef.current = currentFinal

      if (newFinalPortion) {
        const delta = session.processSegment(newFinalPortion, true)
        if (delta.eraseCount > 0 || delta.appendText.length > 0) {
          void tauriBridge.eraseAndInject(delta.eraseCount, delta.appendText).then(() => {
            setInjectionMessage('Sentence typed & saved')
          }).catch(err => {
            setInjectionMessage(err instanceof Error ? err.message : String(err))
          })
        }
      }
      return
    }

    // Case 2: Active Interim speech clause while speaking
    if (currentInterim) {
      const delta = session.processSegment(currentInterim, false)
      if (delta.eraseCount > 0 || delta.appendText.length > 0) {
        void tauriBridge.eraseAndInject(delta.eraseCount, delta.appendText).then(() => {
          setInjectionMessage('Typing...')
        }).catch(err => {
          setInjectionMessage(err instanceof Error ? err.message : String(err))
        })
      }
    }
  }, [speech.interimTranscript, speech.transcript, speech.isListening, localVoice.latestSegment, isUniversalMode])


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
    await saveVoiceSession(textToInject)
    await tauriBridge.eraseAndInject(0, textToInject)
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
        isDesktop={true}
        isStandalone={true}
        onToggleListening={handleToggleListening}
        onToggleUniversalMode={() => setIsUniversalMode(prev => !prev)}
        onToggleCommandMode={() => setIsCommandMode(prev => !prev)}
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
