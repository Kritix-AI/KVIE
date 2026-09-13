import React, { useEffect, useRef, useState } from 'react'
import {
  Mic,
  Square,
  X,
  Settings,
  Zap,
  Sparkles,
  Languages,
  ChevronUp,
  Trash2,
  Vote,
} from 'lucide-react'
import { tauriBridge } from '../lib/tauriBridge'
import './FloatingMicWidget.css'

interface FloatingMicWidgetProps {
  isListening: boolean
  isSupported: boolean
  isUniversalMode: boolean
  isCommandMode?: boolean
  isTranslationEnabled?: boolean
  targetLanguageName?: string
  isConsensusMode?: boolean
  consensusCount?: number
  onToggleListening: () => void
  onToggleUniversalMode: () => void
  onToggleCommandMode?: () => void
  onToggleTranslation?: () => void
  onClearText: () => void
  onToggleConsensus?: () => void
  onConsensusComplete?: () => void
  onClose?: () => void
  interimTranscript?: string
  recentTranscript?: string
  statusMessage?: string | null
}

type Theme = 'light' | 'dark'

export const FloatingMicWidget: React.FC<FloatingMicWidgetProps> = ({
  isListening,
  isSupported,
  isUniversalMode,
  isCommandMode,
  isTranslationEnabled = false,
  targetLanguageName = 'English',
  isConsensusMode = false,
  consensusCount = 0,
  onToggleListening,
  onToggleUniversalMode,
  onToggleCommandMode,
  onToggleTranslation,
  onClearText,
  onToggleConsensus,
  onConsensusComplete,
  onClose,
  interimTranscript,
  recentTranscript,
  statusMessage,
}) => {
  const [expanded, setExpanded] = useState(false)
  const [theme, setTheme] = useState<Theme>('dark')
  const [tooltipId, setTooltipId] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Detect system theme
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    setTheme(mq.matches ? 'light' : 'dark')
    const handler = (e: MediaQueryListEvent) => setTheme(e.matches ? 'light' : 'dark')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const isDark = theme === 'dark'
  const pillClasses = [
    'pill-container',
    isDark ? 'pill-dark' : 'pill-light',
    isListening ? 'pill-listening' : '',
    expanded ? 'pill-expanded' : '',
  ].filter(Boolean).join(' ')

  return (
    <div ref={containerRef} className={pillClasses}>
      {/* Close */}
      <button
        className="pill-btn pill-btn-close"
        onClick={onClose}
        onMouseEnter={() => setTooltipId('close')}
        onMouseLeave={() => setTooltipId(null)}
      >
        <X size={14} strokeWidth={2.4} />
        {tooltipId === 'close' && (
          <span className="pill-tip pill-tip-bottom">Close</span>
        )}
      </button>

      {/* Mic (primary) */}
      <button
        className={`pill-btn pill-btn-mic ${isListening ? 'pill-btn-mic-active' : ''}`}
        onClick={onToggleListening}
        disabled={!isSupported}
        onMouseEnter={() => setTooltipId('mic')}
        onMouseLeave={() => setTooltipId(null)}
      >
        {isListening ? (
          <div className="mic-ring-wrapper">
            <div className="mic-ring" />
            <Square size={16} fill="currentColor" strokeWidth={0} />
          </div>
        ) : (
          <Mic size={18} strokeWidth={1.8} />
        )}
        {tooltipId === 'mic' && (
          <span className="pill-tip pill-tip-bottom">
            {isListening ? 'Stop Recording' : 'Start Recording'}
          </span>
        )}
      </button>

      {/* Divider (appears when expanded) */}
      <div className={`pill-divider ${expanded ? 'pill-divider-show' : ''}`} />

      {/* Expand toggle */}
      <button
        className={`pill-btn pill-btn-expand ${expanded ? 'pill-btn-expand-active' : ''}`}
        onClick={() => setExpanded(v => !v)}
        onMouseEnter={() => setTooltipId('expand')}
        onMouseLeave={() => setTooltipId(null)}
      >
        {expanded ? <ChevronUp size={16} strokeWidth={2.2} /> : <Settings size={14} strokeWidth={2.2} />}
        {tooltipId === 'expand' && (
          <span className="pill-tip pill-tip-bottom">
            {expanded ? 'Less Options' : 'More Options'}
          </span>
        )}
      </button>

      {/* Extra mode buttons */}
      <div className={`pill-extras ${expanded ? 'pill-extras-open' : ''}`}>
        <ExtraBtn
          icon={<Zap size={13} strokeWidth={2} />}
          active={isUniversalMode}
          activeColor="#22d3ee"
          onClick={onToggleUniversalMode}
          tooltip={isUniversalMode ? 'Local Draft' : 'Universal Auto-Inject'}
          tooltipId={tooltipId}
          setTooltipId={setTooltipId}
        />
        {onToggleCommandMode && (
          <ExtraBtn
            icon={<Sparkles size={13} strokeWidth={2} />}
            active={!!isCommandMode}
            activeColor="#a855f7"
            onClick={onToggleCommandMode}
            tooltip={isCommandMode ? 'Dictate Mode' : 'Command Mode'}
            tooltipId={tooltipId}
            setTooltipId={setTooltipId}
          />
        )}
        {onToggleTranslation && (
          <ExtraBtn
            icon={<Languages size={13} strokeWidth={2} />}
            active={isTranslationEnabled}
            activeColor="#06b6d4"
            onClick={onToggleTranslation}
            tooltip={
              isTranslationEnabled
                ? `Translation ON -> ${targetLanguageName}`
                : 'Live Translation'
            }
            tooltipId={tooltipId}
            setTooltipId={setTooltipId}
          />
        )}
        {onToggleConsensus && !isConsensusMode && (
          <ExtraBtn
            icon={<Vote size={13} strokeWidth={2} />}
            active={isConsensusMode}
            activeColor="#f97316"
            onClick={onToggleConsensus}
            tooltip="Consensus Mode"
            tooltipId={tooltipId}
            setTooltipId={setTooltipId}
          />
        )}
        {isConsensusMode && onConsensusComplete && (
          <ExtraBtn
            icon={<Vote size={13} strokeWidth={2} />}
            active={true}
            activeColor="#f97316"
            onClick={onConsensusComplete}
            tooltip={`Finish (${consensusCount} captured)`}
            tooltipId={tooltipId}
            setTooltipId={setTooltipId}
          />
        )}
        <ExtraBtn
          icon={<Trash2 size={13} strokeWidth={2} />}
          active={false}
          onClick={onClearText}
          tooltip="Clear Text"
          tooltipId={tooltipId}
          setTooltipId={setTooltipId}
        />
      </div>
    </div>
  )
}

interface ExtraBtnProps {
  icon: React.ReactNode
  active: boolean
  activeColor: string
  onClick: () => void
  tooltip: string
  tooltipId: string | null
  setTooltipId: (id: string | null) => void
}

const ExtraBtn: React.FC<ExtraBtnProps> = ({
  icon,
  active,
  activeColor,
  onClick,
  tooltip,
  tooltipId,
  setTooltipId,
}) => {
  const tipId = `extra-${tooltip}`
  return (
    <button
      className={`pill-btn pill-btn-extra ${active ? 'pill-btn-extra-active' : ''}`}
      onClick={onClick}
      onMouseEnter={() => setTooltipId(tipId)}
      onMouseLeave={() => setTooltipId(null)}
      style={
        active
          ? ({
              '--extra-color': activeColor,
              color: activeColor,
              borderColor: activeColor + '55',
            } as React.CSSProperties)
          : undefined
      }
    >
      {icon}
      {tooltipId === tipId && (
        <span className="pill-tip pill-tip-bottom">{tooltip}</span>
      )}
    </button>
  )
}

export default FloatingMicWidget
