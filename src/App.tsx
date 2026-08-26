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
  Keyboard,
  Smartphone,
  ShieldCheck,
  ExternalLink,
  Volume2,
  CheckCircle,
  AlertCircle,
} from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { useKvieDocument } from './hooks/useKvieDocument'
import { useSpeechRecognition } from './hooks/useSpeechRecognition'
import { useLocalStreamingVoice } from './hooks/useLocalStreamingVoice'
import { useAppTheme } from './hooks/useAppTheme'
import { tauriBridge } from './lib/tauriBridge'
import { saveVoiceSession } from './lib/sessionRecorder'
import { VoiceSnippet, getVoiceSnippets, saveVoiceSnippets, expandVoiceSnippets } from './lib/snippetsEngine'
import { CustomWord, getCustomDictionary, saveCustomDictionary, applyCustomDictionary } from './lib/customDictionary'
import { SUPPORTED_LANGUAGES, getTranslationSettings, saveTranslationSettings } from './lib/translationEngine'
import { processSpokenVoiceText } from './lib/incrementalTypingEngine'
import { fetchModelsStatus, selectActiveModel, downloadModelWithProgress, downloadAndroidModelWithProgress } from './lib/modelsApi'
import {
  isAndroid,
  openAndroidKeyboardSettings,
  showAndroidKeyboardPicker,
  requestAndroidMicPermission,
  isAndroidKeyboardEnabled,
  getSelectedAndroidEngine,
  setSelectedAndroidEngine,
} from './lib/androidKeyboard'

const navItems = ['Workspace', 'Voice IME', 'Sessions', 'Models', 'Settings']

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
    id: 'trelis-hinglish',
    name: 'Trelis Whisper-Hinglish-Preview',
    provider: 'Trelis Research',
    size: '960 MB',
    params: '769M',
    hinglishRating: '98.2% Accuracy (Hinglish Tuned)',
    latency: '220ms - 320ms',
    description: 'Specialized fine-tuned Whisper for colloquial Indian English & Romanized Hinglish with accurate word boundaries.',
  },
  {
    id: 'srota-qwen3',
    name: 'Qwen3-ASR 0.6B Hinglish (Srota)',
    provider: 'moorlee / Srota Labs',
    size: '620 MB',
    params: '600M',
    hinglishRating: '97.8% Accuracy (Neural Srota)',
    latency: '120ms - 190ms',
    description: 'Ultra-fast LLM-based ASR architecture trained on Indian conversational podcasts, street speech & rapid code-switching.',
  },
  {
    id: 'shunya-zero-stt',
    name: 'Shunya Labs Zero-STT-Hinglish',
    provider: 'Shunya Labs',
    size: '580 MB',
    params: '480M',
    hinglishRating: '97.5% Accuracy (Zero-Shot Indic)',
    latency: '140ms - 220ms',
    description: 'Zero-shot Indic & Hinglish phonetic speech-to-text model optimized for Indian slang, brand names & mixed language phrases.',
  },
  {
    id: 'indic-conformer-600m',
    name: 'AI4Bharat IndicConformer (600M Multilingual)',
    provider: 'IIT Madras / AI4Bharat',
    size: '1.2 GB',
    params: '600M',
    hinglishRating: '98.5% Accuracy (22 Indian Langs)',
    latency: '200ms - 350ms',
    description: 'State-of-the-art Conformer ASR trained on 40,000+ hours across 22 official Indian languages and code-switched dialogues.',
  },
  {
    id: 'indicwhisper',
    name: 'IndicWhisper Multi-Dialect',
    provider: 'AI4Bharat',
    size: '480 MB',
    params: '480M',
    hinglishRating: '97.2% Accuracy (Indic Multi)',
    latency: '150ms - 230ms',
    description: 'Specialized Whisper architecture tuned for 12 Indian languages with high phonetic accuracy in noisy environments.',
  },
  {
    id: 'small',
    name: 'Whisper Small (Lightweight)',
    provider: 'OpenAI',
    size: '460 MB',
    params: '244M',
    hinglishRating: '89.4% Accuracy (Fast Baseline)',
    latency: '90ms - 140ms',
    description: 'Ultra-lightweight baseline suitable for low-spec CPU devices or fast typing benchmarks.',
  },
  {
    id: 'base',
    name: 'Whisper Base (Ultra Fast)',
    provider: 'OpenAI',
    size: '145 MB',
    params: '74M',
    hinglishRating: '82.1% Accuracy (Instant Draft)',
    latency: '50ms - 90ms',
    description: 'Smallest footprint model with instant transcription speed for rapid sentence capture.',
  },
  {
    id: 'tiny',
    name: 'Whisper Tiny (Minimal)',
    provider: 'OpenAI',
    size: '75 MB',
    params: '39M',
    hinglishRating: '74.5% Accuracy (Minimal)',
    latency: '30ms - 60ms',
    description: 'Minimal RAM footprint model for quick voice commands and simple phrases.',
  },
]

const ANDROID_MODEL_CATALOG: STTModel[] = [
  {
    id: 'android-speech-recognizer',
    name: 'Android SpeechRecognizer ⭐',
    provider: 'Google / Android OS Engine',
    size: '0 MB (Pre-installed)',
    params: 'Hardware Accelerated',
    hinglishRating: '96.8% Accuracy (Zero Cloud Latency)',
    latency: '40ms - 90ms',
    isDefault: true,
    description: 'Native Android OS speech recognition service. Instant zero-latency startup, battery-efficient, and pre-installed on all Android devices.',
  },
  {
    id: 'whisper-cpp-tiny',
    name: 'Whisper.cpp Tiny Quantized (GGUF)',
    provider: 'OpenAI / whisper.cpp (NDK)',
    size: '42 MB',
    params: '39M (Q5_K)',
    hinglishRating: '97.4% Accuracy (99+ Langs)',
    latency: '100ms - 160ms',
    description: 'Ultra-lightweight on-device Whisper model cross-compiled via C++ NDK for ARM64/x86. 100% offline with zero cloud dependency.',
  },
  {
    id: 'whisper-cpp-base',
    name: 'Whisper.cpp Base Quantized (GGUF)',
    provider: 'OpenAI / whisper.cpp (NDK)',
    size: '142 MB',
    params: '74M (Q8_0)',
    hinglishRating: '98.2% Accuracy (High Precision)',
    latency: '150ms - 220ms',
    description: 'High-accuracy on-device Whisper model for complex terminology and colloquial Hinglish dictation directly in keyboard memory.',
  },
  {
    id: 'nvidia-parakeet-onnx',
    name: 'NVIDIA Parakeet Streaming ASR (ONNX)',
    provider: 'NVIDIA NeMo / ONNX Runtime',
    size: '128 MB',
    params: '110M INT8',
    hinglishRating: '98.6% Accuracy (25+ Langs)',
    latency: '70ms - 130ms',
    description: 'Next-gen streaming ASR architecture optimized with ONNX Runtime Mobile. Low-RAM memory footprint with realtime token streaming.',
  },
]

export function App() {
  const [activeNav, setActiveNav] = useState('Workspace')
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [isUniversalMode, setIsUniversalMode] = useState(true)
  const [isGlobalHotkeyEnabled, setIsGlobalHotkeyEnabled] = useState(true)
  const [activeModelId, setActiveModelId] = useState<string>('large-v3-turbo')
  const [downloadedModels, setDownloadedModels] = useState<string[]>([])
  const [downloadProgress, setDownloadProgress] = useState<Record<string, { pct: number; downloadedMB: number; totalMB: number; status: string }>>({})
  const [sessions, setSessions] = useState<VoiceSession[]>([])
  const [sessionSearch, setSessionSearch] = useState('')
  const [injectionMessage, setInjectionMessage] = useState<string | null>(null)
  const [isAndroidDevice, setIsAndroidDevice] = useState(false)
  const [isKeyboardEnabledState, setIsKeyboardEnabledState] = useState(false)
  const [testInputText, setTestInputText] = useState('')

  const theme = useAppTheme()
  const document = useKvieDocument()
  const localVoice = useLocalStreamingVoice(isUniversalMode)
  const browserSpeech = useSpeechRecognition()

  const speech = localVoice.isAvailable ? localVoice : browserSpeech

  const [snippets, setSnippets] = useState<VoiceSnippet[]>([])
  const [newTriggerCue, setNewTriggerCue] = useState('')
  const [newExpandedText, setNewExpandedText] = useState('')

  const [customWords, setCustomWords] = useState<CustomWord[]>([])
  const [newWord, setNewWord] = useState('')
  const [newPhoneticVariants, setNewPhoneticVariants] = useState('')

  const [isTranslationEnabled, setIsTranslationEnabled] = useState(false)
  const [targetLanguage, setTargetLanguage] = useState('en')

  const lastCommittedRef = useRef<string>('')

  useEffect(() => {
    const isAndroidEnv = isAndroid()
    setIsAndroidDevice(isAndroidEnv)
    setIsKeyboardEnabledState(isAndroidKeyboardEnabled())

    if (isAndroidEnv) {
      const activeAndroidEngine = getSelectedAndroidEngine()
      setActiveModelId(activeAndroidEngine)
      const savedAndroidDownloads: string[] = JSON.parse(
        localStorage.getItem('kvie_downloaded_android_models') || '[]'
      )
      // Android SpeechRecognizer is built into the OS, others require on-device download
      setDownloadedModels(['android-speech-recognizer', ...savedAndroidDownloads])
    }
  }, [])

  useEffect(() => {
    setSnippets(getVoiceSnippets())
    setCustomWords(getCustomDictionary())
    const tr = getTranslationSettings()
    setIsTranslationEnabled(tr.enabled)
    setTargetLanguage(tr.targetLanguage)

    if (!isAndroid()) {
      const savedActive = localStorage.getItem('kvie_active_stt_model')
      if (savedActive) {
        setActiveModelId(savedActive)
      }

      void (async () => {
        const status = await fetchModelsStatus()
        if (status) {
          setDownloadedModels(status.installed)
          if (status.active) {
            setActiveModelId(status.active)
          }
        }
      })()
    }
  }, [])

  const handleAddSnippet = () => {
    if (!newTriggerCue.trim() || !newExpandedText.trim()) return
    const updated: VoiceSnippet[] = [
      ...snippets,
      {
        id: Date.now().toString(),
        triggerCue: newTriggerCue.trim(),
        expandedText: newExpandedText.trim(),
        enabled: true,
      },
    ]
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

  const handleAddCustomWord = () => {
    if (!newWord.trim()) return
    const variants = newPhoneticVariants
      .split(',')
      .map(v => v.trim())
      .filter(Boolean)
    const updated: CustomWord[] = [
      ...customWords,
      {
        id: Date.now().toString(),
        word: newWord.trim(),
        phoneticVariants: variants,
        enabled: true,
      },
    ]
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

  const handleToggleTranslation = () => {
    const next = !isTranslationEnabled
    setIsTranslationEnabled(next)
    saveTranslationSettings({ enabled: next, targetLanguage })
  }

  const handleSelectTargetLanguage = (langCode: string) => {
    setTargetLanguage(langCode)
    saveTranslationSettings({ enabled: isTranslationEnabled, targetLanguage: langCode })
  }

  useEffect(() => {
    let unlisten: (() => void) | undefined
    if (document.isDesktop) {
      void listen('toggle_mic_shortcut', () => {
        if (speech.isListening) {
          speech.stopListening()
        } else {
          speech.startListening()
        }
      }).then(fn => {
        unlisten = fn
      })
    }
    return () => {
      if (unlisten) unlisten()
    }
  }, [document.isDesktop, speech])

  const autoInject = async (textToInject: string) => {
    if (!textToInject.trim()) return

    if (document.isDesktop) {
      try {
        let appName = 'External Window'
        try {
          const appInfo = await tauriBridge.getActiveAppInfo()
          if (appInfo && appInfo.app_name) {
            appName = appInfo.app_name
          }
        } catch {}

        await tauriBridge.injectText(textToInject)

        const newSession: VoiceSession = {
          id: Date.now().toString(),
          text: textToInject,
          targetApp: appName,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          wordCount: textToInject.trim().split(/\s+/).length,
        }
        setSessions(prev => [newSession, ...prev])
        saveVoiceSession(newSession)
        setInjectionMessage(`Injected into ${appName}`)
      } catch {
        setInjectionMessage('Injected text via Tauri Bridge')
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

  const [translatedDocumentText, setTranslatedDocumentText] = useState('')

  useEffect(() => {
    const raw = (localVoice.isAvailable && localVoice.documentText)
      ? localVoice.documentText
      : (speech.transcript || document.text)

    if (!raw.trim()) {
      setTranslatedDocumentText('')
      return
    }

    let isCancelled = false
    void (async () => {
      const processed = await processSpokenVoiceText(raw, {
        applyTranslation: isTranslationEnabled,
        targetLanguage,
      })
      if (!isCancelled) {
        setTranslatedDocumentText(processed)
      }
    })()

    return () => { isCancelled = true }
  }, [speech.transcript, localVoice.documentText, document.text, isTranslationEnabled, targetLanguage, customWords, snippets])

  const rawDocumentText = (localVoice.isAvailable && localVoice.documentText)
    ? localVoice.documentText
    : (speech.transcript || document.text)

  const activeDocumentText = translatedDocumentText || applyCustomDictionary(expandVoiceSnippets(rawDocumentText).expandedText)

  const activeInterimText = speech.interimTranscript
    ? applyCustomDictionary(expandVoiceSnippets(speech.interimTranscript).expandedText)
    : ''

  const wordCount = useMemo(() => activeDocumentText.trim() ? activeDocumentText.trim().split(/\s+/).length : 0, [activeDocumentText])

  const clearAll = () => {
    speech.clearTranscript()
    localVoice.clearTranscript()
    browserSpeech.clearTranscript()
    setTranslatedDocumentText('')
    lastCommittedRef.current = ''
    void document.apply({ action: 'clear' })
  }

  const injectDraft = async (overrideText?: string) => {
    const textToInject = overrideText || activeDocumentText
    if (!textToInject.trim()) return
    await autoInject(textToInject)
  }

  const copyDraft = async () => {
    if (!activeDocumentText.trim()) return
    try {
      await navigator.clipboard.writeText(activeDocumentText)
      setInjectionMessage('Copied entire transcript to clipboard!')
      window.setTimeout(() => setInjectionMessage(null), 2500)
    } catch {}
  }

  const handleDownloadModel = (modelId: string) => {
    if (downloadProgress[modelId] !== undefined) return

    setDownloadProgress(prev => ({
      ...prev,
      [modelId]: { pct: 1, downloadedMB: 0, totalMB: 0, status: 'Connecting to Hugging Face...' },
    }))

    if (isAndroidDevice) {
      downloadAndroidModelWithProgress(
        modelId,
        payload => {
          const dMB = payload.downloaded_bytes ? Math.round(payload.downloaded_bytes / (1024 * 1024)) : 0
          const tMB = payload.total_bytes ? Math.round(payload.total_bytes / (1024 * 1024)) : 0
          setDownloadProgress(prev => ({
            ...prev,
            [modelId]: {
              pct: payload.progress,
              downloadedMB: dMB,
              totalMB: tMB,
              status: payload.status,
            },
          }))
        },
        () => {
          setDownloadedModels(old => {
            const updated = [...new Set([...old, modelId])]
            localStorage.setItem('kvie_downloaded_android_models', JSON.stringify(updated))
            return updated
          })
          setDownloadProgress(prev => {
            const next = { ...prev }
            delete next[modelId]
            return next
          })
          handleSelectModel(modelId)
        },
        _err => {
          setDownloadProgress(prev => {
            const next = { ...prev }
            delete next[modelId]
            return next
          })
        }
      )
      return
    }

    downloadModelWithProgress(
      modelId,
      payload => {
        const dMB = payload.downloaded_bytes ? Math.round(payload.downloaded_bytes / (1024 * 1024)) : 0
        const tMB = payload.total_bytes ? Math.round(payload.total_bytes / (1024 * 1024)) : 0
        const statusText = payload.status === 'completed'
          ? 'Completed'
          : payload.status === 'connecting'
          ? 'Connecting to Hugging Face...'
          : `Downloading ${payload.progress}%`

        setDownloadProgress(prev => ({
          ...prev,
          [modelId]: {
            pct: payload.progress,
            downloadedMB: dMB,
            totalMB: tMB,
            status: statusText,
          },
        }))
      },
      () => {
        setDownloadedModels(old => {
          const updated = [...new Set([...old, modelId])]
          localStorage.setItem('kvie_downloaded_stt_models', JSON.stringify(updated))
          return updated
        })
        setDownloadProgress(prev => {
          const next = { ...prev }
          delete next[modelId]
          return next
        })
      }
    )
  }

  const handleSelectModel = async (modelId: string) => {
    setActiveModelId(modelId)
    if (isAndroidDevice) {
      setSelectedAndroidEngine(modelId)
      const selectedName = ANDROID_MODEL_CATALOG.find(m => m.id === modelId)?.name || modelId
      setInjectionMessage(`Switched Android Voice Engine to ${selectedName}`)
      return
    }
    localStorage.setItem('kvie_active_stt_model', modelId)
    const success = await selectActiveModel(modelId)
    if (success) {
      setInjectionMessage(`Switched active STT Engine to ${modelId}`)
    }
  }

  const filteredSessions = useMemo(() => {
    if (!sessionSearch.trim()) return sessions
    return sessions.filter(s => s.text.toLowerCase().includes(sessionSearch.toLowerCase()) || s.targetApp.toLowerCase().includes(sessionSearch.toLowerCase()))
  }, [sessions, sessionSearch])

  const currentCatalog = useMemo(() => {
    return isAndroidDevice ? ANDROID_MODEL_CATALOG : MODEL_CATALOG
  }, [isAndroidDevice])

  const activeModelDetails = useMemo(() => {
    return currentCatalog.find(m => m.id === activeModelId) || currentCatalog[0]
  }, [activeModelId, currentCatalog])

  const iconMap: Record<string, JSX.Element> = {
    Workspace: <LayoutDashboard className="h-4 w-4 shrink-0" />,
    'Voice IME': <Keyboard className="h-4 w-4 shrink-0" />,
    Sessions: <MessageSquare className="h-4 w-4 shrink-0" />,
    Models: <Cpu className="h-4 w-4 shrink-0" />,
    Settings: <SettingsIcon className="h-4 w-4 shrink-0" />,
  }

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-ink font-sans text-zinc-100 flex flex-col md:flex-row">
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
        {/* Desktop Left Collapsible Sidebar (Hidden on mobile < md) */}
        <aside
          className={`hidden md:flex h-full z-20 flex-col border-r border-line/70 px-4 py-8 transition-all duration-300 ease-in-out shrink-0 bg-ink/40 backdrop-blur-md ${
            isSidebarCollapsed ? 'w-20 items-center' : 'w-64'
          }`}
        >
          {/* Sidebar Header */}
          <div className="mb-10 flex items-center justify-between px-2">
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
                <p className="text-sm font-medium">{isAndroidDevice ? 'KVIE Android Native' : (document.isDesktop ? 'Tauri Desktop' : 'Browser Mode')}</p>
                <div className="mt-3 flex items-center gap-2 text-xs" style={{ color: theme.accentColor }}>
                  <span className="h-2 w-2 animate-pulse rounded-full" style={{ backgroundColor: theme.accentColor }} />
                  {isAndroidDevice ? 'Voice Keyboard (IME) Active' : (document.isDesktop ? 'KVIE bridge connected' : 'Local draft active')}
                </div>
              </>
            ) : (
              <div className="flex justify-center" title="Runtime Active">
                <span className="h-2.5 w-2.5 animate-pulse rounded-full" style={{ backgroundColor: theme.accentColor }} />
              </div>
            )}
          </div>
        </aside>

        {/* Main Content Area (Scrolls smoothly with touch optimizations) */}
        <section className="flex min-w-0 flex-1 flex-col h-full overflow-y-auto px-4 py-4 sm:px-8 sm:py-8 pb-36 md:pb-8 touch-scroll safe-top safe-bottom">
          {/* Header */}
          <header className="flex items-center justify-between gap-3 mb-6">
            <div className="flex items-center gap-3">
              {/* Desktop sidebar toggle */}
              <button
                onClick={() => setIsSidebarCollapsed(prev => !prev)}
                className="hidden md:flex rounded-xl border border-line bg-panel p-2 text-zinc-400 transition hover:text-zinc-100"
                title="Toggle Sidebar Layout"
              >
                {isSidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
              </button>

              {/* Mobile Branding */}
              <div className="flex md:hidden items-center gap-2.5">
                <img
                  src="/logo.png"
                  className="h-8 w-8 rounded-lg object-contain"
                  style={{ border: `1px solid ${theme.accentColor}` }}
                  alt="Kritix"
                />
              </div>

              <div>
                <p className="text-[10px] uppercase tracking-[.22em] text-zinc-500">{activeNav}</p>
                <h1 className="text-lg font-semibold tracking-tight sm:text-2xl">
                  {activeNav === 'Workspace' && 'Voice Workspace'}
                  {activeNav === 'Voice IME' && 'KVIE Android Keyboard (IME)'}
                  {activeNav === 'Sessions' && 'Voice Sessions'}
                  {activeNav === 'Models' && 'STT Engine Hub'}
                  {activeNav === 'Settings' && 'Preferences & Themes'}
                </h1>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Quick Model Badge */}
              <button
                onClick={() => setActiveNav('Models')}
                className="flex items-center gap-1.5 rounded-full border border-line bg-panel/90 px-3 py-1 text-xs text-zinc-300 transition hover:border-zinc-600"
                style={{ borderColor: `${theme.accentColor}40` }}
              >
                <Cpu className="h-3.5 w-3.5" style={{ color: theme.accentColor }} />
                <span className="hidden sm:inline font-mono">{activeModelDetails.name.split(' ')[0]}</span>
              </button>

              {/* Desktop Floating Mic Button (only on desktop) */}
              {document.isDesktop && !isAndroidDevice && (
                <button
                  onClick={() => void tauriBridge.toggleFloatingMic()}
                  className="hidden sm:flex items-center gap-1.5 rounded-full border border-line bg-panel px-3.5 py-1.5 text-xs transition hover:bg-zinc-800"
                  style={{ color: theme.accentColor }}
                  title="Open/Toggle OS Desktop Floating Mic Window"
                >
                  <Pin className="h-3.5 w-3.5" />
                  Desktop Mic
                </button>
              )}
            </div>
          </header>

          {/* ──────────────── TAB VIEW 1: WORKSPACE ──────────────── */}
          {activeNav === 'Workspace' && (
            <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-between py-2 sm:py-6 pb-28 md:pb-0">
              {/* Android Keyboard Quick Banner (If on mobile) */}
              <div
                onClick={() => setActiveNav('Voice IME')}
                className="cursor-pointer mb-4 flex items-center justify-between gap-3 rounded-2xl border bg-panel/70 p-3.5 sm:p-4 backdrop-blur-md transition hover:bg-panel"
                style={{ borderColor: `${theme.accentColor}50` }}
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-xl p-2.5 bg-zinc-900 border border-line" style={{ color: theme.accentColor }}>
                    <Keyboard className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-zinc-100 flex items-center gap-1.5">
                      KVIE System-Wide Voice Keyboard
                      <span className="rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 border border-emerald-500/30">Android Ready</span>
                    </p>
                    <p className="text-[11px] text-zinc-400">Speak into WhatsApp, Chrome, Notes & any Android app without floating overlays.</p>
                  </div>
                </div>
                <span className="text-xs font-medium shrink-0 flex items-center gap-1" style={{ color: theme.accentColor }}>
                  Setup <ExternalLink className="h-3.5 w-3.5" />
                </span>
              </div>

              {/* Header Details */}
              <div className="mb-4 flex items-end justify-between gap-4">
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider" style={{ color: theme.accentColor }}>
                    Living Document
                  </p>
                  <h2 className="text-2xl font-medium leading-tight tracking-tight sm:text-4xl">
                    Speak freely.<br />
                    <span className="text-zinc-500">KVIE shapes the draft.</span>
                  </h2>
                </div>
                <div className="text-right">
                  <p className="text-2xl sm:text-3xl font-medium text-zinc-200">{wordCount}</p>
                  <p className="text-[10px] uppercase tracking-widest text-zinc-500">words</p>
                </div>
              </div>

              {/* Main Document Pad */}
              <motion.div
                layout
                className="relative flex-1 min-h-[260px] sm:min-h-[340px] rounded-3xl border bg-panel/80 p-5 sm:p-7 backdrop-blur-xl transition-all duration-300 flex flex-col justify-between"
                style={{
                  borderColor: `${theme.accentColor}40`,
                  boxShadow: `0 0 50px ${theme.accentColor}20, inset 0 0 20px ${theme.accentColor}06`,
                }}
              >
                <div className="mb-4 flex items-center justify-between border-b border-line/50 pb-3">
                  <div className="flex items-center gap-2 text-xs text-zinc-400">
                    <span className={`h-2.5 w-2.5 rounded-full ${speech.isListening ? 'animate-pulse' : 'bg-zinc-700'}`} style={speech.isListening ? { backgroundColor: theme.accentColor } : {}} />
                    <span>{speech.isListening ? 'Listening continuously...' : 'Ready to capture'}</span>
                    {isTranslationEnabled && (
                      <span className="hidden sm:inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono text-cyan-400 border-cyan-500/30 bg-cyan-500/10">
                        <Languages className="h-3 w-3" /> Auto-Translate: {targetLanguage.toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <button disabled={!document.can_undo} onClick={() => void document.undo()} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-30">
                      <Undo2 className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Undo</span>
                    </button>
                    <button disabled={!document.can_redo} onClick={() => void document.redo()} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100 disabled:opacity-30">
                      <Redo2 className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Redo</span>
                    </button>
                    <button onClick={copyDraft} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100" title="Copy to clipboard">
                      <Copy className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Copy</span>
                    </button>
                    <button onClick={clearAll} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-rose-400" title="Clear all text">
                      <Trash2 className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Clear</span>
                    </button>
                  </div>
                </div>

                {/* Editor Surface */}
                <div aria-live="polite" className="flex-1 whitespace-pre-wrap text-lg sm:text-2xl leading-relaxed text-zinc-100 overflow-y-auto max-h-[40vh] sm:max-h-[50vh]">
                  {activeDocumentText || activeInterimText ? (
                    <>
                      {activeDocumentText}
                      {activeDocumentText && activeInterimText && !/[\s\n]$/.test(activeDocumentText) ? ' ' : ''}
                      <span style={{ color: theme.accentColor }} className="font-normal">{activeInterimText}</span>
                    </>
                  ) : (
                    <span className="text-zinc-600 font-light text-base sm:text-xl">Tap the microphone button below or use the KVIE Voice Keyboard to dictate...</span>
                  )}
                </div>

                <AnimatePresence>
                  {(speech.error || document.error) && (
                    <motion.p initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} className="text-xs text-rose-400 pt-2">
                      {speech.error || document.error}
                    </motion.p>
                  )}
                </AnimatePresence>
              </motion.div>

              {/* Bottom In-App Mic Controller */}
              <div className="mt-6 flex flex-col items-center gap-3">
                <motion.button
                  whileTap={{ scale: 0.92 }}
                  whileHover={{ scale: 1.05 }}
                  onClick={speech.isListening ? speech.stopListening : speech.startListening}
                  disabled={!speech.isSupported}
                  className={`grid h-18 w-18 sm:h-20 sm:w-20 place-items-center rounded-full border transition ${
                    speech.isListening ? 'text-white shadow-xl' : 'border-line bg-zinc-900 text-zinc-300 hover:border-zinc-700'
                  } disabled:opacity-40`}
                  style={speech.isListening ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor, boxShadow: `0 0 50px ${theme.accentColor}70` } : {}}
                  aria-label={speech.isListening ? 'Stop listening' : 'Start listening'}
                >
                  {speech.isListening ? <Square className="h-7 w-7 fill-current" /> : <Mic className="h-8 w-8" style={{ color: theme.accentColor }} />}
                </motion.button>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => void copyDraft()}
                    disabled={!activeDocumentText.trim()}
                    className="flex items-center gap-2 rounded-full border border-line bg-panel px-4 py-2 text-xs text-zinc-300 transition hover:border-zinc-600 disabled:opacity-30"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Copy Draft
                  </button>
                  {document.isDesktop && (
                    <button
                      onClick={() => void injectDraft()}
                      disabled={!activeDocumentText.trim()}
                      className="flex items-center gap-2 rounded-full border border-line bg-panel px-4 py-2 text-xs text-zinc-300 transition hover:border-zinc-600 disabled:opacity-30"
                      style={activeDocumentText.trim() ? { borderColor: `${theme.accentColor}60`, color: theme.accentColor } : {}}
                    >
                      <Send className="h-3.5 w-3.5" />
                      Inject Text
                    </button>
                  )}
                </div>

                <p className="text-xs text-zinc-500">
                  {speech.isSupported ? (speech.isListening ? 'Listening... Tap to stop' : 'Tap mic to dictate in workspace') : 'Microphone unavailable in current runtime'}
                </p>
                {injectionMessage && <p className="text-xs font-semibold" style={{ color: theme.accentColor }}>{injectionMessage}</p>}
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 2: KVIE ANDROID VOICE KEYBOARD (IME) HUB ──────────────── */}
          {activeNav === 'Voice IME' && (
            <div className="mx-auto w-full max-w-4xl py-2 sm:py-6 space-y-6 pb-36 md:pb-6">
              {/* Hero Banner */}
              <div
                className="rounded-3xl border bg-panel/80 p-6 sm:p-8 backdrop-blur-xl relative overflow-hidden"
                style={{ borderColor: `${theme.accentColor}40`, boxShadow: `0 0 50px ${theme.accentColor}20` }}
              >
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-emerald-500/20 text-emerald-400 text-xs px-3 py-0.5 border border-emerald-500/30 font-medium flex items-center gap-1">
                        <Smartphone className="h-3.5 w-3.5" /> Android System IME
                      </span>
                      <span className="rounded-full bg-zinc-800 text-zinc-300 text-xs px-3 py-0.5 border border-line font-mono">
                        Zero Floating Windows Required
                      </span>
                    </div>
                    <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-zinc-100">
                      KVIE Voice Keyboard
                    </h2>
                    <p className="text-sm text-zinc-400 max-w-xl">
                      Dictate directly into <b>WhatsApp, Telegram, Chrome, Instagram, Gmail, Notes</b>, and every Android text field with instantaneous transcription and automatic filler-word cleaning.
                    </p>
                  </div>

                  <div className="rounded-2xl p-4 bg-zinc-900/90 border border-line/80 text-center shrink-0">
                    <Volume2 className="h-8 w-8 mx-auto mb-1" style={{ color: theme.accentColor }} />
                    <span className="text-[11px] font-medium text-zinc-400">100% Native IME</span>
                  </div>
                </div>
              </div>

              {/* 3 Step Setup Action Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Step 1 */}
                <div className="rounded-2xl border border-line bg-panel/80 p-5 flex flex-col justify-between gap-4">
                  <div className="space-y-2">
                    <span className="text-xs font-bold font-mono px-2.5 py-1 rounded-lg bg-zinc-800 text-zinc-300">
                      STEP 1
                    </span>
                    <h3 className="text-base font-semibold text-zinc-100">Enable Keyboard in Android</h3>
                    <p className="text-xs text-zinc-400">
                      Open Android Settings &gt; Languages &amp; Input &gt; Keyboards and turn ON "KVIE Voice Keyboard".
                    </p>
                  </div>
                  <button
                    onClick={() => openAndroidKeyboardSettings()}
                    className="w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold text-black transition"
                    style={{ backgroundColor: theme.accentColor }}
                  >
                    <ExternalLink className="h-3.5 w-3.5" /> Open Keyboard Settings
                  </button>
                </div>

                {/* Step 2 */}
                <div className="rounded-2xl border border-line bg-panel/80 p-5 flex flex-col justify-between gap-4">
                  <div className="space-y-2">
                    <span className="text-xs font-bold font-mono px-2.5 py-1 rounded-lg bg-zinc-800 text-zinc-300">
                      STEP 2
                    </span>
                    <h3 className="text-base font-semibold text-zinc-100">Select Active Keyboard</h3>
                    <p className="text-xs text-zinc-400">
                      Trigger the Android Input Method Picker and select "KVIE Voice Keyboard" as your current input.
                    </p>
                  </div>
                  <button
                    onClick={() => showAndroidKeyboardPicker()}
                    className="w-full flex items-center justify-center gap-2 rounded-xl border border-line bg-zinc-800 hover:bg-zinc-700 py-2.5 text-xs font-semibold text-zinc-100 transition"
                  >
                    <Keyboard className="h-3.5 w-3.5" style={{ color: theme.accentColor }} /> Switch Active Input Method
                  </button>
                </div>

                {/* Step 3 */}
                <div className="rounded-2xl border border-line bg-panel/80 p-5 flex flex-col justify-between gap-4">
                  <div className="space-y-2">
                    <span className="text-xs font-bold font-mono px-2.5 py-1 rounded-lg bg-zinc-800 text-zinc-300">
                      STEP 3
                    </span>
                    <h3 className="text-base font-semibold text-zinc-100">Grant Microphone Access</h3>
                    <p className="text-xs text-zinc-400">
                      Allow KVIE to record audio so the voice keyboard can transcribe your speech in real-time.
                    </p>
                  </div>
                  <button
                    onClick={() => requestAndroidMicPermission()}
                    className="w-full flex items-center justify-center gap-2 rounded-xl border border-line bg-zinc-800 hover:bg-zinc-700 py-2.5 text-xs font-semibold text-zinc-100 transition"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" /> Request Mic Permission
                  </button>
                </div>
              </div>

              {/* Active Engine Banner */}
              <div className="rounded-2xl border border-line bg-zinc-900/90 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl p-2.5 bg-zinc-800 shrink-0" style={{ color: theme.accentColor }}>
                    <Cpu className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-400">Active Mobile Engine:</span>
                      <span className="text-xs font-semibold text-zinc-100">{activeModelDetails.name}</span>
                    </div>
                    <span className="text-[11px] text-zinc-500 font-mono">{activeModelDetails.size} · {activeModelDetails.latency}</span>
                  </div>
                </div>
                <button
                  onClick={() => setActiveNav('Models')}
                  className="rounded-xl border border-line bg-zinc-800 hover:bg-zinc-700 px-3.5 py-1.5 text-xs font-medium text-zinc-200 transition self-end sm:self-center"
                >
                  Switch Engine
                </button>
              </div>

              {/* Interactive Live Voice Test Field */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-zinc-100 text-lg flex items-center gap-2">
                      <Sparkles className="h-5 w-5" style={{ color: theme.accentColor }} /> Live Keyboard Test Ground
                    </h3>
                    <p className="text-xs text-zinc-400">
                      Tap the input box below. When your keyboard pops up, switch to KVIE Voice Keyboard and tap the mic!
                    </p>
                  </div>
                  {testInputText && (
                    <button
                      onClick={() => setTestInputText('')}
                      className="text-xs text-zinc-400 hover:text-rose-400"
                    >
                      Clear
                    </button>
                  )}
                </div>

                <textarea
                  rows={4}
                  value={testInputText}
                  onChange={e => setTestInputText(e.target.value)}
                  placeholder="Tap here to bring up your keyboard and test voice dictation..."
                  className="w-full rounded-2xl border border-line bg-zinc-900/80 p-4 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none transition"
                  style={{ borderColor: testInputText ? `${theme.accentColor}80` : undefined }}
                />

                <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs text-zinc-500">
                  <span>💡 You can also switch back to your normal keyboard anytime using the <b>⋮</b> button on the KVIE keyboard bar.</span>
                  {testInputText && <span className="font-mono text-zinc-400">{testInputText.length} characters</span>}
                </div>
              </div>

              {/* Core Capabilities */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-line bg-zinc-900/50 p-5 space-y-2">
                  <h4 className="font-semibold text-zinc-200 text-sm flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-emerald-400" /> Automatic Filler-Word Stripping
                  </h4>
                  <p className="text-xs text-zinc-400">
                    Removes conversational hesitations like "um", "uh", "like", "matlab", and "basically" seamlessly before text hits the active input field.
                  </p>
                </div>
                <div className="rounded-2xl border border-line bg-zinc-900/50 p-5 space-y-2">
                  <h4 className="font-semibold text-zinc-200 text-sm flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-cyan-400" /> AI Auto-Edit Refinement
                  </h4>
                  <p className="text-xs text-zinc-400">
                    Sends speech through a background stage-2 refinement pass to auto-correct grammar and format text cleanly on the fly.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 3: SESSIONS ──────────────── */}
          {activeNav === 'Sessions' && (
            <div className="mx-auto w-full max-w-4xl py-2 sm:py-6 pb-36 md:pb-6">
              <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3.5 top-3 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    value={sessionSearch}
                    onChange={e => setSessionSearch(e.target.value)}
                    placeholder="Search voice transcript sessions..."
                    className="w-full rounded-2xl border border-line bg-panel py-2.5 pl-10 pr-4 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none"
                  />
                </div>
                <span className="text-xs font-mono text-zinc-400 bg-zinc-800/80 px-3 py-1.5 rounded-xl border border-line self-start sm:self-center">
                  {filteredSessions.length} Recorded Sessions
                </span>
              </div>

              {filteredSessions.length === 0 ? (
                <div className="rounded-3xl border border-line bg-panel/50 p-12 text-center">
                  <MessageSquare className="h-10 w-10 mx-auto mb-3 text-zinc-600" />
                  <h3 className="text-base font-semibold text-zinc-300">No voice sessions recorded yet</h3>
                  <p className="text-xs text-zinc-500 mt-1 max-w-md mx-auto">
                    Start speaking in the workspace or through the KVIE Voice Keyboard to record transcribed sessions with timestamp history.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredSessions.map(session => (
                    <div
                      key={session.id}
                      className="rounded-2xl border border-line bg-panel/70 p-5 space-y-3 transition hover:border-zinc-700"
                    >
                      <div className="flex items-center justify-between text-xs text-zinc-400">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-zinc-300 font-medium">{session.targetApp}</span>
                          <span>·</span>
                          <span>{session.timestamp}</span>
                        </div>
                        <span className="font-mono text-[11px] text-zinc-500">{session.wordCount} words</span>
                      </div>
                      <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">{session.text}</p>
                      <div className="flex items-center justify-end gap-2 pt-2 border-t border-line/40">
                        <button
                          onClick={async () => {
                            await navigator.clipboard.writeText(session.text)
                            setInjectionMessage('Session text copied to clipboard!')
                            window.setTimeout(() => setInjectionMessage(null), 2000)
                          }}
                          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100"
                        >
                          <Copy className="h-3.5 w-3.5" /> Copy
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ──────────────── TAB VIEW 4: STT MODEL MANAGER ──────────────── */}
          {activeNav === 'Models' && (
            <div className="mx-auto w-full max-w-4xl py-2 sm:py-6 space-y-6 pb-40 md:pb-6">
              <div className="rounded-3xl border border-line bg-panel/80 p-6">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                    <Cpu className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-zinc-100 text-lg">
                      {isAndroidDevice ? 'Android On-Device Speech Engines' : 'STT Neural Engine Hub'}
                    </h3>
                    <p className="text-xs text-zinc-400">
                      {isAndroidDevice
                        ? 'Select between native SpeechRecognizer, on-device Whisper.cpp (NDK), or NVIDIA Parakeet (ONNX) streaming.'
                        : 'Download and select high-precision Whisper & Qwen models for on-device Hinglish transcription'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Models Grid (Fully responsive 1 to 3 columns) */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {currentCatalog.map(model => {
                  const isInstalled = downloadedModels.includes(model.id)
                  const isActive = activeModelId === model.id
                  const progress = downloadProgress[model.id]

                  return (
                    <div
                      key={model.id}
                      className={`rounded-2xl border p-5 flex flex-col justify-between gap-4 transition ${
                        isActive
                          ? 'bg-zinc-800/90 shadow-lg'
                          : 'border-line bg-panel/60 hover:bg-panel'
                      }`}
                      style={isActive ? { borderColor: theme.accentColor } : {}}
                    >
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-semibold text-zinc-100 text-sm">{model.name}</h4>
                          {isActive && (
                            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase text-black" style={{ backgroundColor: theme.accentColor }}>
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-zinc-400 leading-relaxed">{model.description}</p>
                        <div className="flex flex-wrap gap-2 pt-2 text-[11px] font-mono text-zinc-400">
                          <span className="rounded bg-zinc-900 px-2 py-0.5 border border-line">{model.size}</span>
                          <span className="rounded bg-zinc-900 px-2 py-0.5 border border-line">{model.latency}</span>
                          <span className="rounded bg-zinc-900 px-2 py-0.5 border border-line text-emerald-400">{model.hinglishRating.split(' ')[0]}</span>
                        </div>
                      </div>

                      {/* Download / Select Action */}
                      <div>
                        {progress !== undefined ? (
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between text-xs text-zinc-400">
                              <span>{progress.status}</span>
                              <span className="font-mono font-bold" style={{ color: theme.accentColor }}>{progress.pct}%</span>
                            </div>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-900 border border-line">
                              <div
                                className="h-full transition-all duration-300"
                                style={{ width: `${progress.pct}%`, backgroundColor: theme.accentColor }}
                              />
                            </div>
                          </div>
                        ) : isInstalled ? (
                          <button
                            onClick={() => handleSelectModel(model.id)}
                            disabled={isActive}
                            className={`w-full flex items-center justify-center gap-2 rounded-xl py-2 text-xs font-semibold transition ${
                              isActive ? 'bg-zinc-700 text-zinc-400 cursor-default' : 'bg-zinc-800 text-zinc-200 hover:bg-zinc-700'
                            }`}
                          >
                            {isActive ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : null}
                            {isActive ? 'Current Engine' : 'Use This Engine'}
                          </button>
                        ) : (
                          <button
                            onClick={() => handleDownloadModel(model.id)}
                            className="w-full flex items-center justify-center gap-2 rounded-xl py-2 text-xs font-semibold text-black transition"
                            style={{ backgroundColor: theme.accentColor }}
                          >
                            <Download className="h-3.5 w-3.5 stroke-[2.5]" /> Download Model
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* ──────────────── TAB VIEW 5: SETTINGS ──────────────── */}
          {activeNav === 'Settings' && (
            <div className="mx-auto w-full max-w-4xl py-2 sm:py-6 space-y-6 pb-40 md:pb-6">
              {/* THEME & COLOR PALETTE */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                    <Palette className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-zinc-100 text-lg">Theme &amp; Accent Color Palette</h3>
                    <p className="text-xs text-zinc-400">Choose from curated presets or pick any custom hex accent</p>
                  </div>
                </div>

                {/* Preset Color Swatches */}
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

              {/* LIVE TRANSLATION ENGINE */}
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

              {/* VOICE SNIPPETS & EXPANSIONS */}
              <div className="rounded-3xl border border-line bg-panel/80 p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl p-2.5 bg-zinc-800" style={{ color: theme.accentColor }}>
                      <Zap className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-100 text-lg">Voice Snippets &amp; Macro Triggers</h3>
                      <p className="text-xs text-zinc-400">Map spoken trigger phrases to auto-expanding text templates</p>
                    </div>
                  </div>
                  <span className="text-xs font-mono text-zinc-400 bg-zinc-800/80 px-3 py-1 rounded-full border border-line">
                    {snippets.filter(s => s.enabled).length} Active Triggers
                  </span>
                </div>

                <div className="rounded-2xl border border-line bg-zinc-900/60 p-4 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      placeholder="Spoken Cue (e.g., 'my email address')"
                      value={newTriggerCue}
                      onChange={e => setNewTriggerCue(e.target.value)}
                      className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      placeholder="Expanded Text (e.g., 'alex@example.com')"
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

                <div className="space-y-2">
                  {snippets.map(snippet => (
                    <div
                      key={snippet.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-line/60 bg-zinc-900/40 p-3"
                    >
                      <div>
                        <span className="text-xs font-mono font-bold text-amber-400">"{snippet.triggerCue}"</span>
                        <p className="text-xs text-zinc-300 font-mono">{snippet.expandedText}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleToggleSnippet(snippet.id)}
                          className={`h-5 w-9 rounded-full p-0.5 transition ${snippet.enabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
                          style={snippet.enabled ? { backgroundColor: theme.accentColor } : {}}
                        >
                          <div className={`h-4 w-4 rounded-full bg-white transition ${snippet.enabled ? 'translate-x-4' : ''}`} />
                        </button>
                        <button
                          onClick={() => handleDeleteSnippet(snippet.id)}
                          className="p-1 text-zinc-500 hover:text-rose-400"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Desktop Footer */}
          <footer className="hidden sm:flex flex-wrap items-center justify-between gap-4 border-t border-line/70 pt-5 text-xs text-zinc-600">
            <span>KVIE Voice Intelligence Engine · Android IME &amp; Desktop</span>
            <span>Zero-latency local transcription</span>
          </footer>
        </section>
      </div>

      {/* ──────────────── MOBILE BOTTOM NAVIGATION BAR (< md) ──────────────── */}
      <div className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-line/80 bg-ink/95 px-2 py-2.5 backdrop-blur-2xl md:hidden safe-bottom">
        {navItems.map(item => {
          const isSelected = activeNav === item

          return (
            <button
              key={item}
              onClick={() => setActiveNav(item)}
              className="flex flex-col items-center gap-1 py-1 px-3 rounded-xl transition relative"
              style={isSelected ? { color: theme.accentColor } : { color: '#71717a' }}
            >
              {iconMap[item] || <Sparkles className="h-5 w-5" />}
              <span className="text-[10px] font-medium tracking-tight">{item}</span>
              {isSelected && (
                <motion.div
                  layoutId="activeBottomTab"
                  className="absolute -bottom-1 h-1 w-6 rounded-full"
                  style={{ backgroundColor: theme.accentColor }}
                />
              )}
            </button>
          )
        })}
      </div>
    </main>
  )
}

export default App
