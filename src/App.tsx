import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutDashboard,
  MessageSquare,
  Cpu,
  Settings as SettingsIcon,
  Zap,
  Pin,
  Mic,
  Square,
  Undo2,
  Redo2,
  Trash2,
  Send,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  Palette,
  Check,
  Sliders,
  Copy,
  Search,
  Clock,
  Activity,
  Download,
  CheckCircle2,
  Monitor,
  AppWindow,
  Plus,
  BookOpen,
  Languages,
} from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { useKvieDocument } from './hooks/useKvieDocument'
import { useSpeechRecognition } from './hooks/useSpeechRecognition'
import { useLocalStreamingVoice } from './hooks/useLocalStreamingVoice'
import { useAppTheme } from './hooks/useAppTheme'
import { tauriBridge } from './lib/tauriBridge'
import { saveVoiceSession } from './lib/sessionRecorder'
import { VoiceSnippet, getVoiceSnippets, saveVoiceSnippets } from './lib/snippetsEngine'
import { CustomWord, getCustomDictionary, saveCustomDictionary } from './lib/customDictionary'
import { SUPPORTED_LANGUAGES, getTranslationSettings, saveTranslationSettings } from './lib/translationEngine'

const navItems = ['Workspace', 'Sessions', 'Models', 'Settings']

export interface STTModel {
  id: string
  name: string
  provider: string
  size: string
  params: string
  hinglishRating: string
  latency: string
  isDefault?: boolean
  description: string
}

export interface VoiceSession {
  id: string
  text: string
  targetApp: string
  timestamp: string
  wordCount: number
}

const MODEL_CATALOG: STTModel[] = [
  {
    id: 'large-v3-turbo',
    name: 'Whisper Large-v3 Turbo ⭐',
    provider: 'OpenAI / CTranslate2',
    size: '1.5 GB',
    params: '808M',
    hinglishRating: '96.5% Accuracy (Gold Standard)',
    latency: '180ms - 250ms',
    isDefault: true,
    description: 'Pruned decoder layers (32 to 4) deliver 7x faster inference with top-tier Hinglish code-switching accuracy.',
  },
  {
    id: 'indicwhisper',
    name: 'IndicWhisper (AI4Bharat)',
    provider: 'IIT Madras / AI4Bharat',
    size: '466 MB',
    params: '466M',
    hinglishRating: '97.0% Accuracy (Indic Native)',
    latency: '300ms - 450ms',
    description: 'Trained on 10,000+ hours of Indian audio. Unmatched accuracy for regional accents & Indic code-switched speech.',
  },
  {
    id: 'medium',
    name: 'Whisper Medium Multilingual',
    provider: 'OpenAI / CTranslate2',
    size: '1.5 GB',
    params: '769M',
    hinglishRating: '91.0% Accuracy',
    latency: '350ms - 500ms',
    description: 'Robust multilingual model with strong general vocabulary accuracy across 99 languages.',
  },
  {
    id: 'small',
    name: 'Whisper Small (Lightweight)',
    provider: 'OpenAI / CTranslate2',
    size: '466 MB',
    params: '244M',
    hinglishRating: '84.0% Accuracy',
    latency: '150ms - 250ms',
    description: 'Balanced speed and low memory footprint (~400MB RAM/VRAM). Great for low-spec laptops.',
  },
  {
    id: 'tiny',
    name: 'Whisper Tiny (Fast CPU)',
    provider: 'OpenAI / CTranslate2',
    size: '150 MB',
    params: '39M',
    hinglishRating: '75.0% Accuracy',
    latency: '< 100ms',
    description: 'Ultra lightweight model for legacy hardware and instant low-precision audio transcription.',
  },
]

const App = () => {
  const [activeNav, setActiveNav] = useState('Workspace')
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const theme = useAppTheme()

  const browserSpeech = useSpeechRecognition()
  const localVoice = useLocalStreamingVoice()
  const speech = localVoice.isAvailable ? localVoice : browserSpeech
  const document = useKvieDocument()
  const lastCommittedRef = useRef('')
  const [injectionMessage, setInjectionMessage] = useState<string | null>(null)
  const [sessionSearch, setSessionSearch] = useState('')

  // STT Model Management State
  const [activeModelId, setActiveModelId] = useState<string>(() => {
    return localStorage.getItem('kvie_active_stt_model') || 'large-v3-turbo'
  })

  const [downloadedModels, setDownloadedModels] = useState<string[]>(() => {
    const saved = localStorage.getItem('kvie_downloaded_stt_models')
    return saved ? JSON.parse(saved) : ['large-v3-turbo', 'small']
  })

  const [downloadProgress, setDownloadProgress] = useState<Record<string, number>>({})

  const [isUniversalMode, setIsUniversalMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('kvie_universal_mode')
    return saved !== null ? saved === 'true' : true
  })

  const [isGlobalHotkeyEnabled, setIsGlobalHotkeyEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('kvie_global_hotkey_enabled')
    return saved !== null ? saved === 'true' : true
  })

  const [snippets, setSnippets] = useState<VoiceSnippet[]>(getVoiceSnippets)
  const [newTriggerCue, setNewTriggerCue] = useState('')
  const [newExpandedText, setNewExpandedText] = useState('')

  const [customWords, setCustomWords] = useState<CustomWord[]>(getCustomDictionary)
  const [newWord, setNewWord] = useState('')
  const [newPhoneticVariants, setNewPhoneticVariants] = useState('')

  const [isTranslationEnabled, setIsTranslationEnabled] = useState<boolean>(() => getTranslationSettings().isEnabled)
  const [targetLanguage, setTargetLanguage] = useState<string>(() => getTranslationSettings().targetLanguage)

  const handleToggleTranslation = () => {
    const next = !isTranslationEnabled
    setIsTranslationEnabled(next)
    saveTranslationSettings(next, targetLanguage)
  }

  const handleSelectTargetLanguage = (code: string) => {
    setTargetLanguage(code)
    saveTranslationSettings(isTranslationEnabled, code)
  }

  const handleAddCustomWord = () => {
    if (!newWord.trim()) return
    const variants = newPhoneticVariants
      .split(',')
      .map(v => v.trim())
      .filter(Boolean)

    const item: CustomWord = {
      id: String(Date.now()),
      word: newWord.trim(),
      phoneticVariants: variants,
      enabled: true,
    }
    const updated = [item, ...customWords]
    setCustomWords(updated)
    saveCustomDictionary(updated)
    setNewWord('')
    setNewPhoneticVariants('')
  }

  const handleToggleCustomWord = (id: string) => {
    const updated = customWords.map(w => (w.id === id ? { ...w, enabled: !w.enabled } : w))
    setCustomWords(updated)
    saveCustomDictionary(updated)
  }

  const handleDeleteCustomWord = (id: string) => {
    const updated = customWords.filter(w => w.id !== id)
    setCustomWords(updated)
    saveCustomDictionary(updated)
  }

  const [sessions, setSessions] = useState<VoiceSession[]>(() => {
    const saved = localStorage.getItem('kvie_voice_sessions')
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch {
        // fallback default
      }
    }
    return [
      { id: '1', text: 'Aaj ka kya plan hai bhai, meeting kitne baje rakhein?', targetApp: 'WhatsApp Desktop', timestamp: '10:08 AM', wordCount: 9 },
      { id: '2', text: 'Please send me the project report by 5 PM today.', targetApp: 'Notepad', timestamp: '09:45 AM', wordCount: 10 },
      { id: '3', text: 'Kritix Voice Intelligence Engine is working smoothly across desktop apps.', targetApp: 'VS Code', timestamp: '09:12 AM', wordCount: 10 },
    ]
  })

  const handleAddSnippet = () => {
    if (!newTriggerCue.trim() || !newExpandedText.trim()) return
    const newSnippet: VoiceSnippet = {
      id: String(Date.now()),
      triggerCue: newTriggerCue.trim(),
      expandedText: newExpandedText.trim(),
      enabled: true,
    }
    const updated = [newSnippet, ...snippets]
    setSnippets(updated)
    saveVoiceSnippets(updated)
    setNewTriggerCue('')
    setNewExpandedText('')
  }

  const handleToggleSnippet = (id: string) => {
    const updated = snippets.map(s => (s.id === id ? { ...s, enabled: !s.enabled } : s))
    setSnippets(updated)
    saveVoiceSnippets(updated)
  }

  const handleDeleteSnippet = (id: string) => {
    const updated = snippets.filter(s => s.id !== id)
    setSnippets(updated)
    saveVoiceSnippets(updated)
  }

  useEffect(() => {
    localStorage.setItem('kvie_universal_mode', String(isUniversalMode))
  }, [isUniversalMode])

  useEffect(() => {
    localStorage.setItem('kvie_global_hotkey_enabled', String(isGlobalHotkeyEnabled))
  }, [isGlobalHotkeyEnabled])

  useEffect(() => {
    localStorage.setItem('kvie_active_stt_model', activeModelId)
  }, [activeModelId])

  useEffect(() => {
    localStorage.setItem('kvie_downloaded_stt_models', JSON.stringify(downloadedModels))
  }, [downloadedModels])

  useEffect(() => {
    const syncSessions = () => {
      const saved = localStorage.getItem('kvie_voice_sessions')
      if (saved) {
        try {
          setSessions(JSON.parse(saved))
        } catch {
          // ignore
        }
      }
    }

    window.addEventListener('storage', syncSessions)
    const interval = setInterval(syncSessions, 500)
    return () => {
      window.removeEventListener('storage', syncSessions)
      clearInterval(interval)
    }
  }, [])

  // System-wide Global Hotkey (Ctrl + Alt + R) to toggle Mic ON/OFF
  useEffect(() => {
    if (!isGlobalHotkeyEnabled) return

    let unlisten: (() => void) | undefined
    if (document.isDesktop) {
      void listen('toggle_mic_shortcut', () => {
        const currentEnabled = localStorage.getItem('kvie_global_hotkey_enabled') !== 'false'
        if (!currentEnabled) return

        if (speech.isListening) {
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
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.altKey && (e.key.toLowerCase() === 'r' || e.code === 'KeyR')) {
        e.preventDefault()
        const currentEnabled = localStorage.getItem('kvie_global_hotkey_enabled') !== 'false'
        if (!currentEnabled) return

        if (speech.isListening) {
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
      }
    }
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      if (unlisten) unlisten()
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [document.isDesktop, isGlobalHotkeyEnabled, speech.isListening, browserSpeech, localVoice])

  const autoInject = async (textToInject: string) => {
    if (!textToInject.trim()) return
    await saveVoiceSession(textToInject)

    if (document.isDesktop) {
      try {
        await tauriBridge.injectText(textToInject)
        setInjectionMessage(`Injected "${textToInject.slice(0, 25)}${textToInject.length > 25 ? '...' : ''}" into active app`)
      } catch (cause) {
        setInjectionMessage(cause instanceof Error ? cause.message : String(cause))
      }
    } else {
      try {
        await navigator.clipboard.writeText(textToInject)
        setInjectionMessage(`Copied "${textToInject.slice(0, 25)}..." to clipboard`)
      } catch {
        setInjectionMessage('Clipboard access denied by browser')
      }
    }
    window.setTimeout(() => setInjectionMessage(null), 3000)
  }

  const activeDocumentText = localVoice.isAvailable && localVoice.documentText ? localVoice.documentText : document.text
  const wordCount = useMemo(() => activeDocumentText.trim() ? activeDocumentText.trim().split(/\s+/).length : 0, [activeDocumentText])

  const clearAll = () => {
    speech.clearTranscript()
    lastCommittedRef.current = ''
    void document.apply({ action: 'clear' })
  }

  const injectDraft = async (overrideText?: string) => {
    const textToInject = overrideText || activeDocumentText
    if (!textToInject.trim()) return
    await autoInject(textToInject)
  }

  const handleDownloadModel = (modelId: string) => {
    if (downloadProgress[modelId] !== undefined) return
    setDownloadProgress(prev => ({ ...prev, [modelId]: 5 }))

    const interval = setInterval(() => {
      setDownloadProgress(prev => {
        const current = prev[modelId] || 5
        if (current >= 100) {
          clearInterval(interval)
          setDownloadedModels(old => [...new Set([...old, modelId])])
          const updated = { ...prev }
          delete updated[modelId]
          return updated
        }
        return { ...prev, [modelId]: current + Math.floor(Math.random() * 18) + 10 }
      })
    }, 350)
  }

  const handleSelectModel = (modelId: string) => {
    setActiveModelId(modelId)
  }

  const filteredSessions = useMemo(() => {
    if (!sessionSearch.trim()) return sessions
    return sessions.filter(s => s.text.toLowerCase().includes(sessionSearch.toLowerCase()) || s.targetApp.toLowerCase().includes(sessionSearch.toLowerCase()))
  }, [sessions, sessionSearch])

  const activeModelDetails = useMemo(() => {
    return MODEL_CATALOG.find(m => m.id === activeModelId) || MODEL_CATALOG[0]
  }, [activeModelId])

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-ink font-sans text-zinc-100 flex">
      {/* Background Cosmic Glows (Fixed viewport positioning) */}
      <div
        className="pointer-events-none fixed -left-40 -top-40 h-96 w-96 rounded-full blur-3xl opacity-20 transition-all duration-500 z-0"
        style={{ backgroundColor: theme.accentColor }}
      />
      <div
        className="pointer-events-none fixed -bottom-40 -right-20 h-96 w-96 rounded-full blur-3xl opacity-15 transition-all duration-500 z-0"
        style={{ backgroundColor: theme.accentColor }}
      />

      <div className="relative flex h-full w-full overflow-hidden z-10">
        {/* Left Responsive Collapsible Sidebar */}
        <aside
          className={`h-full z-20 flex flex-col border-r border-line/70 px-4 py-8 transition-all duration-300 ease-in-out shrink-0 bg-ink/40 backdrop-blur-md ${
            isSidebarCollapsed ? 'w-20 items-center' : 'w-64'
          }`}
        >
          {/* Sidebar Header */}
          <div className="mb-12 flex items-center justify-between px-2">
            <div className="flex items-center gap-3">
              <img
                src="/logo.png"
                className="h-9 w-9 shrink-0 rounded-xl object-contain shadow-md transition-all duration-300"
                style={{ border: `1px solid ${theme.accentColor}`, boxShadow: `0 0 18px ${theme.accentColor}40` }}
                alt="Kritix Logo"
              />
              {!isSidebarCollapsed && (
                <div>
                  <p className="font-semibold tracking-tight text-transparent bg-clip-text bg-gradient-to-r" style={{ backgroundImage: `linear-gradient(to right, ${theme.accentColor}, #d946ef)` }}>
                    Kritix
                  </p>
                  <p className="text-xs text-zinc-400 font-medium">Voice Intelligence Engine</p>
                </div>
              )}
            </div>
          </div>

          {/* Nav Items */}
          <nav className="w-full space-y-2">
            {navItems.map(item => {
              const iconMap: Record<string, JSX.Element> = {
                Workspace: <LayoutDashboard className="h-4 w-4 shrink-0" />,
                Sessions: <MessageSquare className="h-4 w-4 shrink-0" />,
                Models: <Cpu className="h-4 w-4 shrink-0" />,
                Settings: <SettingsIcon className="h-4 w-4 shrink-0" />,
              }
              const isSelected = activeNav === item

              return (
                <button
                  key={item}
                  onClick={() => setActiveNav(item)}
                  title={isSidebarCollapsed ? item : undefined}
                  className={`flex w-full items-center gap-3.5 rounded-xl transition ${
                    isSidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3 text-left text-sm'
                  } ${
                    isSelected
                      ? 'bg-zinc-800/80 font-medium'
                      : 'text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200'
                  }`}
                  style={isSelected ? { color: theme.accentColor } : {}}
                >
                  {iconMap[item] || <Sparkles className="h-4 w-4 shrink-0" />}
                  {!isSidebarCollapsed && <span>{item}</span>}
                </button>
              )
            })}
          </nav>

          {/* Runtime Info Card */}
          <div className={`mt-auto rounded-2xl border border-line bg-panel/80 transition-all ${isSidebarCollapsed ? 'w-full p-3 text-center' : 'p-4'}`}>
            {!isSidebarCollapsed ? (
              <>
                <p className="mb-2 text-xs uppercase tracking-[.18em] text-zinc-500">Runtime</p>
                <p className="text-sm font-medium">{document.isDesktop ? 'Tauri Desktop' : 'Browser Mode'}</p>
                <div className="mt-3 flex items-center gap-2 text-xs" style={{ color: theme.accentColor }}>
                  <span className="h-2 w-2 animate-pulse rounded-full" style={{ backgroundColor: theme.accentColor }} />
                  {document.isDesktop ? 'KVIE bridge connected' : 'Local draft active'}
                </div>
              </>
            ) : (
              <div className="flex justify-center" title={document.isDesktop ? 'Tauri Desktop Connected' : 'Browser Mode'}>
                <span className="h-2.5 w-2.5 animate-pulse rounded-full" style={{ backgroundColor: theme.accentColor }} />
              </div>
            )}
          </div>
        </aside>

        {/* Main Content Area (Scrolls independently while background stays fixed) */}
        <section className="flex min-w-0 flex-1 flex-col h-full overflow-y-auto px-5 py-6 sm:px-10 sm:py-10">
          <header className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsSidebarCollapsed(prev => !prev)}
                className="rounded-xl border border-line bg-panel p-2 text-zinc-400 transition hover:text-zinc-100"
                title="Toggle Sidebar Layout"
              >
                {isSidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
              </button>
              <div>
                <p className="text-xs uppercase tracking-[.22em] text-zinc-500">{activeNav}</p>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
                  {activeNav === 'Workspace' && 'Voice Workspace'}
                  {activeNav === 'Sessions' && 'Voice Sessions & Injection History'}
                  {activeNav === 'Models' && 'STT Model Hub & Engine Manager'}
                  {activeNav === 'Settings' && 'Settings & Theme Customizer'}
                </h1>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsUniversalMode(prev => !prev)}
                className={`flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs transition ${
                  isUniversalMode
                    ? 'border-line bg-panel font-medium'
                    : 'border-line bg-panel text-zinc-400 hover:text-zinc-200'
                }`}
                style={isUniversalMode ? { color: theme.accentColor, borderColor: `${theme.accentColor}60` } : {}}
              >
                <Zap className="h-3.5 w-3.5" style={{ color: theme.accentColor }} />
                Universal Voice Typing: {isUniversalMode ? 'ON' : 'OFF'}
              </button>
              {document.isDesktop && (
                <button
                  onClick={() => void tauriBridge.toggleFloatingMic()}
                  className="flex items-center gap-1.5 rounded-full border border-line bg-panel px-3.5 py-1.5 text-xs transition hover:bg-zinc-800"
                  style={{ color: theme.accentColor }}
                  title="Open/Toggle OS Desktop Floating Mic Window"
                >
                  <Pin className="h-3.5 w-3.5" />
                  Desktop Floating Mic
                </button>
              )}
            </div>
          </header>

          {/* ──────────────── TAB VIEW 1: WORKSPACE ──────────────── */}
          {activeNav === 'Workspace' && (
            <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center py-10">
              <div className="mb-8 flex items-end justify-between gap-6">
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: theme.accentColor }}>
                    Living Document
                  </p>
                  <h2 className="max-w-xl text-3xl font-medium leading-tight tracking-tight sm:text-5xl">
                    Speak freely.<br />
                    <span className="text-zinc-500">KVIE shapes the draft.</span>
                  </h2>
                </div>
                <div className="hidden text-right sm:block">
                  <p className="text-3xl font-medium text-zinc-200">{wordCount}</p>
                  <p className="text-xs uppercase tracking-widest text-zinc-600">words</p>
                </div>
              </div>

              <motion.div
                layout
                className="relative min-h-[320px] rounded-3xl border bg-panel/80 p-6 backdrop-blur-xl sm:p-8 transition-all duration-300"
                style={{
                  borderColor: `${theme.accentColor}40`,
                  boxShadow: `0 0 70px ${theme.accentColor}25, inset 0 0 20px ${theme.accentColor}08`,
                }}
              >
                <div className="mb-6 flex items-center justify-between border-b border-line/50 pb-4">
                  <div className="flex items-center gap-2 text-xs text-zinc-400">
                    <span className={`h-2.5 w-2.5 rounded-full ${speech.isListening ? 'animate-pulse' : 'bg-zinc-700'}`} style={speech.isListening ? { backgroundColor: theme.accentColor } : {}} />
                    {speech.isListening ? 'Listening continuously' : 'Ready when you are'}
                    {isUniversalMode && (
                      <span className="ml-2 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-medium" style={{ color: theme.accentColor, borderColor: `${theme.accentColor}40`, backgroundColor: `${theme.accentColor}15` }}>
                        <Zap className="h-3 w-3" /> Universal Auto-Inject Active
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <button disabled={!document.can_undo} onClick={() => void document.undo()} className="flex items-center gap-1 text-xs text-zinc-500 transition hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-30">
                      <Undo2 className="h-3.5 w-3.5" /> Undo
                    </button>
                    <button disabled={!document.can_redo} onClick={() => void document.redo()} className="flex items-center gap-1 text-xs text-zinc-500 transition hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-30">
                      <Redo2 className="h-3.5 w-3.5" /> Redo
                    </button>
                    <button onClick={clearAll} className="flex items-center gap-1 text-xs text-zinc-500 transition hover:text-rose-400">
                      <Trash2 className="h-3.5 w-3.5" /> Clear
                    </button>
                  </div>
                </div>
                <div aria-live="polite" className="min-h-[160px] whitespace-pre-wrap text-xl leading-relaxed text-zinc-100 sm:text-2xl">
                  {activeDocumentText || speech.interimTranscript ? (
                    <>
                      {activeDocumentText}
                      <span style={{ color: theme.accentColor }} className="font-normal">{speech.interimTranscript}</span>
                    </>
                  ) : (
                    <span className="text-zinc-600 font-light">Press the microphone button or floating mic widget and start speaking...</span>
                  )}
                </div>
                <AnimatePresence>
                  {(speech.error || document.error) && (
                    <motion.p initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} className="absolute bottom-4 left-8 text-xs text-rose-400">
                      {speech.error || document.error}
                    </motion.p>
                  )}
                </AnimatePresence>
              </motion.div>

              <div className="mt-8 flex flex-col items-center gap-4">
                <motion.button
                  whileTap={{ scale: 0.94 }}
                  whileHover={{ scale: 1.04 }}
                  onClick={speech.isListening ? speech.stopListening : speech.startListening}
                  disabled={!speech.isSupported}
                  className={`grid h-20 w-20 place-items-center rounded-full border text-2xl transition ${
                    speech.isListening ? 'text-white shadow-lg' : 'border-line bg-zinc-900 text-zinc-300 hover:border-zinc-700'
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                  style={speech.isListening ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor, boxShadow: `0 0 50px ${theme.accentColor}60` } : {}}
                  aria-label={speech.isListening ? 'Stop listening' : 'Start listening'}
                >
                  {speech.isListening ? <Square className="h-7 w-7 fill-current" /> : <Mic className="h-8 w-8" style={{ color: theme.accentColor }} />}
                </motion.button>
                <button
                  onClick={() => void injectDraft()}
                  disabled={!activeDocumentText.trim()}
                  className="flex items-center gap-2 rounded-full border border-line px-5 py-2 text-xs text-zinc-400 transition hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-30"
                  style={activeDocumentText.trim() ? { borderColor: `${theme.accentColor}60`, color: theme.accentColor } : {}}
                >
                  <Send className="h-3.5 w-3.5" />
                  Inject into active app
                </button>
                <p className="text-xs text-zinc-600">
                  {speech.isSupported ? (speech.isListening ? 'Click to pause capture' : 'Click to start capture') : 'Speech recognition is unavailable in this runtime'}
                </p>
                {injectionMessage && <p className="text-xs font-medium" style={{ color: theme.accentColor }}>{injectionMessage}</p>}
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 2: SESSIONS WITH TARGET APP DETECTOR ──────────────── */}
          {activeNav === 'Sessions' && (
            <div className="mx-auto w-full max-w-4xl py-8">
              <div className="mb-6 flex items-center justify-between gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3.5 top-3 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    value={sessionSearch}
                    onChange={e => setSessionSearch(e.target.value)}
                    placeholder="Search sessions by voice text or target app (WhatsApp, Notepad, Chrome, VS Code)..."
                    className="w-full rounded-2xl border border-line bg-panel/80 pl-10 pr-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
                  />
                </div>
                <div className="text-xs text-zinc-500">{filteredSessions.length} voice sessions recorded</div>
              </div>

              <div className="space-y-4">
                {filteredSessions.length > 0 ? (
                  filteredSessions.map(session => (
                    <div key={session.id} className="rounded-2xl border border-line bg-panel/80 p-5 transition hover:border-zinc-700">
                      <div className="mb-3 flex items-center justify-between text-xs text-zinc-500">
                        <div className="flex items-center gap-2">
                          {/* Active Application Target Badge */}
                          <span
                            className="flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-medium shadow-sm"
                            style={{ color: theme.accentColor, borderColor: `${theme.accentColor}50`, backgroundColor: `${theme.accentColor}12` }}
                          >
                            <AppWindow className="h-3 w-3" />
                            {session.targetApp}
                          </span>
                          <span className="flex items-center gap-1 text-zinc-500">
                            <Clock className="h-3.5 w-3.5" /> {session.timestamp}
                          </span>
                        </div>
                        <span className="font-mono text-zinc-400">{session.wordCount} words</span>
                      </div>
                      <p className="text-base text-zinc-200 leading-relaxed mb-4">{session.text}</p>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => void autoInject(session.text)}
                          className="flex items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-xs text-zinc-300 transition hover:text-zinc-100"
                          style={{ borderColor: `${theme.accentColor}50`, color: theme.accentColor }}
                        >
                          <Send className="h-3 w-3" /> Re-Inject to App
                        </button>
                        <button
                          onClick={() => void navigator.clipboard.writeText(session.text)}
                          className="flex items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-xs text-zinc-400 transition hover:text-zinc-200"
                        >
                          <Copy className="h-3 w-3" /> Copy Text
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-2xl border border-line bg-panel/40 p-12 text-center text-zinc-500">
                    No voice sessions found matching "{sessionSearch}"
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 3: MODELS HUB ──────────────── */}
          {activeNav === 'Models' && (
            <div className="mx-auto w-full max-w-4xl py-8 space-y-8">
              {/* ACTIVE MODEL BANNER */}
              <div className="rounded-3xl border border-line bg-panel/90 p-6 relative overflow-hidden shadow-xl" style={{ borderColor: `${theme.accentColor}40` }}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 relative z-10">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wider" style={{ color: theme.accentColor, backgroundColor: `${theme.accentColor}18`, border: `1px solid ${theme.accentColor}40` }}>
                        ✓ Active STT Engine (Default)
                      </span>
                      <span className="text-xs text-zinc-400 font-mono">100% Offline Local</span>
                    </div>
                    <h2 className="text-2xl font-bold text-zinc-100 mb-1">{activeModelDetails.name}</h2>
                    <p className="text-xs text-zinc-400 max-w-xl leading-relaxed">{activeModelDetails.description}</p>
                  </div>

                  <div className="flex items-center gap-4 border-l border-line/60 pl-6 shrink-0">
                    <div>
                      <p className="text-xs text-zinc-500 uppercase tracking-wider">Hinglish Accuracy</p>
                      <p className="text-base font-semibold" style={{ color: theme.accentColor }}>{activeModelDetails.hinglishRating.split(' ')[0]}</p>
                    </div>
                    <div>
                      <p className="text-xs text-zinc-500 uppercase tracking-wider">Latency</p>
                      <p className="text-base font-semibold text-zinc-200">{activeModelDetails.latency}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* MODEL CATALOG GRID */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-zinc-100 text-lg">STT Model Catalog</h3>
                    <p className="text-xs text-zinc-400">Download other specialized speech recognition models with 1-click download button</p>
                  </div>
                  <span className="text-xs text-zinc-500 font-mono">{MODEL_CATALOG.length} models available</span>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {MODEL_CATALOG.map(model => {
                    const isActive = activeModelId === model.id
                    const isDownloaded = downloadedModels.includes(model.id)
                    const progress = downloadProgress[model.id]

                    return (
                      <div
                        key={model.id}
                        className={`rounded-2xl border p-5 transition flex flex-col justify-between ${
                          isActive
                            ? 'bg-panel/90 shadow-md ring-1'
                            : 'border-line bg-panel/60 hover:bg-panel/90 hover:border-zinc-700'
                        }`}
                        style={isActive ? { borderColor: `${theme.accentColor}60` } : {}}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="font-semibold text-zinc-100 text-base">{model.name}</h4>
                            <span className="text-[11px] font-mono rounded-full bg-zinc-800 px-2.5 py-0.5 text-zinc-400">{model.size}</span>
                          </div>
                          <p className="text-xs text-zinc-400 leading-relaxed mb-4">{model.description}</p>
                        </div>

                        <div className="space-y-3">
                          <div className="grid grid-cols-2 gap-2 text-[11px] bg-zinc-900/60 p-2.5 rounded-xl text-zinc-400">
                            <div><span className="text-zinc-500">Params:</span> {model.params}</div>
                            <div><span className="text-zinc-500">Latency:</span> {model.latency}</div>
                            <div className="col-span-2"><span className="text-zinc-500">Hinglish:</span> <span style={{ color: theme.accentColor }}>{model.hinglishRating}</span></div>
                          </div>

                          {/* Download / Action Button */}
                          <div>
                            {isActive ? (
                              <div className="flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-semibold" style={{ color: theme.accentColor, borderColor: `${theme.accentColor}50`, backgroundColor: `${theme.accentColor}12` }}>
                                <CheckCircle2 className="h-4 w-4" /> Active STT Engine (Default)
                              </div>
                            ) : isDownloaded ? (
                              <button
                                onClick={() => handleSelectModel(model.id)}
                                className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-line bg-zinc-800 py-2 text-xs text-zinc-200 hover:border-zinc-500 hover:text-white transition font-medium"
                              >
                                Use Model
                              </button>
                            ) : progress !== undefined ? (
                              <div className="w-full rounded-xl bg-zinc-800 p-2 text-center text-xs">
                                <div className="flex justify-between text-[11px] text-zinc-400 mb-1">
                                  <span>Downloading Model...</span>
                                  <span>{progress}%</span>
                                </div>
                                <div className="h-1.5 w-full rounded-full bg-zinc-900 overflow-hidden">
                                  <div className="h-full transition-all duration-300" style={{ width: `${progress}%`, backgroundColor: theme.accentColor }} />
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => handleDownloadModel(model.id)}
                                className="w-full flex items-center justify-center gap-2 rounded-xl border border-line bg-zinc-900 py-2 text-xs text-zinc-300 hover:border-accent hover:text-white transition font-medium"
                              >
                                <Download className="h-3.5 w-3.5" /> Single Click Download
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 4: SETTINGS & THEME CUSTOMIZER ──────────────── */}
          {activeNav === 'Settings' && (
            <div className="mx-auto w-full max-w-4xl py-8 space-y-8">
              {/* ACCENT COLOR THEME CUSTOMIZER */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 shadow-xl">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                      <Palette className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-100 text-lg">Accent Theme Customizer</h3>
                      <p className="text-xs text-zinc-400">Select preset accent colors or pick any custom color from the graph picker</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-full border border-line px-3 py-1 text-xs">
                    <span className="h-3 w-3 rounded-full shadow-sm" style={{ backgroundColor: theme.accentColor }} />
                    <span className="font-mono text-zinc-300">{theme.accentColor}</span>
                  </div>
                </div>

                {/* Preset Color Palette Swatches */}
                <div className="mb-8">
                  <label className="block mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                    Preset Theme Swatches
                  </label>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-7">
                    {theme.presets.map(preset => {
                      const isSelected = theme.activePresetId === preset.id
                      return (
                        <button
                          key={preset.id}
                          onClick={() => theme.selectPreset(preset)}
                          className={`flex flex-col items-center gap-2 rounded-2xl border p-3 transition ${
                            isSelected ? 'bg-zinc-800/90 shadow-md ring-2' : 'border-line bg-zinc-900/50 hover:bg-zinc-800/50'
                          }`}
                          style={isSelected ? { borderColor: preset.color } : {}}
                        >
                          <div
                            className="relative grid h-8 w-8 place-items-center rounded-full shadow-inner"
                            style={{ backgroundColor: preset.color }}
                          >
                            {isSelected && <Check className="h-4 w-4 text-black stroke-[3]" />}
                          </div>
                          <span className="text-[11px] font-medium text-zinc-300 text-center">{preset.name.split(' ')[0]}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Custom Color Graph Picker */}
                <div className="rounded-2xl border border-line bg-zinc-900/60 p-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h4 className="text-sm font-medium text-zinc-200 mb-1">Custom Color Graph Picker</h4>
                      <p className="text-xs text-zinc-400">Manually pick any custom accent color from the color graph or enter hex value</p>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="relative h-10 w-14 overflow-hidden rounded-xl border border-line cursor-pointer shadow-inner">
                        <input
                          type="color"
                          value={theme.accentColor}
                          onChange={e => theme.setCustomColor(e.target.value)}
                          className="absolute -inset-2 h-16 w-20 cursor-pointer opacity-100"
                          title="Click to open full color graph picker"
                        />
                      </div>

                      <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2 text-sm">
                        <span className="text-zinc-500 font-mono">#</span>
                        <input
                          type="text"
                          value={theme.accentColor.replace('#', '')}
                          onChange={e => theme.setCustomColor(`#${e.target.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 6)}`)}
                          className="w-20 bg-transparent font-mono text-zinc-200 focus:outline-none"
                          maxLength={6}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* ENGINE & SPEECH SETTINGS */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center gap-3 mb-2">
                  <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                    <Sliders className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-zinc-100 text-lg">Voice Capture & Auto-Injection</h3>
                    <p className="text-xs text-zinc-400">Configure speech-to-text and live typing behaviors</p>
                  </div>
                </div>

                <div className="divide-y divide-line/50 text-sm">
                  <div className="py-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-zinc-200">Universal Auto-Inject Mode</p>
                      <p className="text-xs text-zinc-500">Automatically types speech into active app (Notepad, WhatsApp, Chrome, etc.)</p>
                    </div>
                    <button
                      onClick={() => setIsUniversalMode(prev => !prev)}
                      className={`h-6 w-11 rounded-full p-1 transition ${isUniversalMode ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                      style={isUniversalMode ? { backgroundColor: theme.accentColor } : {}}
                    >
                      <div className={`h-4 w-4 rounded-full bg-white transition ${isUniversalMode ? 'translate-x-5' : ''}`} />
                    </button>
                  </div>

                  <div className="py-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-zinc-200">
                        Global System-Wide Shortcut ({typeof navigator !== 'undefined' && /Mac|iPhone|iPod|iPad/.test(navigator.userAgent || '') ? '⌘ + ⌥ + R' : 'Ctrl + Alt + R'})
                      </p>
                      <p className="text-xs text-zinc-500">
                        Pressing {typeof navigator !== 'undefined' && /Mac|iPhone|iPod|iPad/.test(navigator.userAgent || '') ? '⌘ + ⌥ + R on macOS' : 'Ctrl + Alt + R on Windows'} turns mic ON or OFF instantly
                      </p>
                    </div>
                    <button
                      onClick={() => setIsGlobalHotkeyEnabled(prev => !prev)}
                      className={`h-6 w-11 rounded-full p-1 transition ${isGlobalHotkeyEnabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                      style={isGlobalHotkeyEnabled ? { backgroundColor: theme.accentColor } : {}}
                    >
                      <div className={`h-4 w-4 rounded-full bg-white transition ${isGlobalHotkeyEnabled ? 'translate-x-5' : ''}`} />
                    </button>
                  </div>

                  <div className="py-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-zinc-200">Hinglish Verbatim Roman Script</p>
                      <p className="text-xs text-zinc-500">Transcribes Hinglish spoken words without auto-translating to English</p>
                    </div>
                    <span className="text-xs text-zinc-400 bg-zinc-800 px-2.5 py-1 rounded-full">Active</span>
                  </div>
                </div>
              </div>

              {/* VOICE SNIPPETS & TEXT EXPANSION ENGINE */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                      <Zap className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-100 text-lg">Voice Snippets & Text Expansion Engine</h3>
                      <p className="text-xs text-zinc-400">Map spoken trigger phrases to auto-expanding text templates</p>
                    </div>
                  </div>
                  <span className="text-xs font-mono text-zinc-400 bg-zinc-800/80 px-3 py-1 rounded-full border border-line">
                    {snippets.filter(s => s.enabled).length} Active Triggers
                  </span>
                </div>

                {/* Add New Snippet Form */}
                <div className="rounded-2xl border border-line bg-zinc-900/60 p-4 space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Add Custom Voice Trigger</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      placeholder="Spoken Cue (e.g., 'my meeting link')"
                      value={newTriggerCue}
                      onChange={e => setNewTriggerCue(e.target.value)}
                      className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      placeholder="Expanded Text (e.g., 'https://calendly.com/...')"
                      value={newExpandedText}
                      onChange={e => setNewExpandedText(e.target.value)}
                      className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={handleAddSnippet}
                    disabled={!newTriggerCue.trim() || !newExpandedText.trim()}
                    className="flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold text-black transition disabled:opacity-40"
                    style={{ backgroundColor: theme.accentColor }}
                  >
                    <Plus className="h-4 w-4 stroke-[3]" /> Add Snippet
                  </button>
                </div>

                {/* Registered Snippets List */}
                <div className="space-y-3">
                  {snippets.map(snippet => (
                    <div
                      key={snippet.id}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-line/60 bg-zinc-900/40 p-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded">
                            "{snippet.triggerCue}"
                          </span>
                          <span className="text-xs text-zinc-500">→</span>
                        </div>
                        <p className="text-xs text-zinc-300 font-mono whitespace-pre-wrap">{snippet.expandedText}</p>
                      </div>

                      <div className="flex items-center gap-3 self-end sm:self-center">
                        <button
                          onClick={() => handleToggleSnippet(snippet.id)}
                          className={`h-6 w-11 rounded-full p-1 transition ${snippet.enabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                          style={snippet.enabled ? { backgroundColor: theme.accentColor } : {}}
                        >
                          <div className={`h-4 w-4 rounded-full bg-white transition ${snippet.enabled ? 'translate-x-5' : ''}`} />
                        </button>
                        <button
                          onClick={() => handleDeleteSnippet(snippet.id)}
                          className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-rose-400 transition"
                          title="Delete snippet"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* PERSONALIZED CUSTOM DICTIONARY MANAGER */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                      <BookOpen className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-100 text-lg">Personalized Custom Dictionary & Vocabulary</h3>
                      <p className="text-xs text-zinc-400">Add custom jargon, names, and acronyms to bias STT & LLM auto-correction</p>
                    </div>
                  </div>
                  <span className="text-xs font-mono text-zinc-400 bg-zinc-800/80 px-3 py-1 rounded-full border border-line">
                    {customWords.filter(w => w.enabled).length} Custom Terms
                  </span>
                </div>

                {/* Add New Custom Word Form */}
                <div className="rounded-2xl border border-line bg-zinc-900/60 p-4 space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Add Preferred Term / Brand Name</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      placeholder="Target Word (e.g., 'Kritix')"
                      value={newWord}
                      onChange={e => setNewWord(e.target.value)}
                      className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      placeholder="Misspellings / Sound-alikes (comma separated, e.g. 'critics, critic')"
                      value={newPhoneticVariants}
                      onChange={e => setNewPhoneticVariants(e.target.value)}
                      className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={handleAddCustomWord}
                    disabled={!newWord.trim()}
                    className="flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold text-black transition disabled:opacity-40"
                    style={{ backgroundColor: theme.accentColor }}
                  >
                    <Plus className="h-4 w-4 stroke-[3]" /> Add Word
                  </button>
                </div>

                {/* Registered Custom Words List */}
                <div className="space-y-3">
                  {customWords.map(item => (
                    <div
                      key={item.id}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-line/60 bg-zinc-900/40 p-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-zinc-100">{item.word}</span>
                          {item.phoneticVariants.length > 0 && (
                            <span className="text-xs text-zinc-500">
                              (Auto-corrects from: {item.phoneticVariants.join(', ')})
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 self-end sm:self-center">
                        <button
                          onClick={() => handleToggleCustomWord(item.id)}
                          className={`h-6 w-11 rounded-full p-1 transition ${item.enabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                          style={item.enabled ? { backgroundColor: theme.accentColor } : {}}
                        >
                          <div className={`h-4 w-4 rounded-full bg-white transition ${item.enabled ? 'translate-x-5' : ''}`} />
                        </button>
                        <button
                          onClick={() => handleDeleteCustomWord(item.id)}
                          className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-800 hover:text-rose-400 transition"
                          title="Delete word"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* LIVE TRANSLATION ENGINE (100+ LANGUAGES) */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                      <Languages className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-100 text-lg">Live Voice Translation Engine</h3>
                      <p className="text-xs text-zinc-400">Speak in any language and auto-translate output into your target language</p>
                    </div>
                  </div>
                  <button
                    onClick={handleToggleTranslation}
                    className={`h-6 w-11 rounded-full p-1 transition ${isTranslationEnabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                    style={isTranslationEnabled ? { backgroundColor: theme.accentColor } : {}}
                  >
                    <div className={`h-4 w-4 rounded-full bg-white transition ${isTranslationEnabled ? 'translate-x-5' : ''}`} />
                  </button>
                </div>

                <div className="space-y-3">
                  <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Target Output Language</label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                    {SUPPORTED_LANGUAGES.map(lang => (
                      <button
                        key={lang.code}
                        onClick={() => handleSelectTargetLanguage(lang.code)}
                        className={`flex items-center justify-between rounded-xl border px-3.5 py-2.5 text-xs font-medium transition ${
                          targetLanguage === lang.code
                            ? 'border-cyan-500 bg-cyan-500/10 text-cyan-400'
                            : 'border-line bg-zinc-900/40 text-zinc-300 hover:border-zinc-700'
                        }`}
                        style={targetLanguage === lang.code ? { borderColor: theme.accentColor, color: theme.accentColor } : {}}
                      >
                        <span>{lang.name}</span>
                        <span className="text-[10px] text-zinc-500 font-mono">{lang.nativeName}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          <footer className="flex flex-wrap items-center justify-between gap-4 border-t border-line/70 pt-5 text-xs text-zinc-600">
            <span>Streaming STT · Universal Voice Injection · Floating Mic</span>
            <span>SQLite persistence · Tauri bridge</span>
          </footer>
        </section>
      </div>
    </main>
  )
}

export default App
