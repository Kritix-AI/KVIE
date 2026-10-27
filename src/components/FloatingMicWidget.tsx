import React, { useEffect, useRef, useState } from 'react'
import {
  Mic,
  Square,
  X,
  Sparkles,
  Check,
} from 'lucide-react'
import { tauriBridge } from '../lib/tauriBridge'
import './FloatingMicWidget.css'

export interface FloatingMicWidgetProps {
  isListening: boolean
  isSupported: boolean
  isUniversalMode: boolean
  isCommandMode?: boolean
  isTranslationEnabled?: boolean
  targetLanguageName?: string
  isConsensusMode?: boolean
  consensusCount?: number
  audioLevel?: number
  isProcessing?: boolean
  isSuccess?: boolean
  successMessage?: string | null
  onToggleListening: () => void
  onCancelListening?: () => void
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
  isContinuousListening?: boolean
}

const BAR_COLORS = [
  '#00d8f6', // Bar 0 - Cyan
  '#00b8f8', // Bar 1 - Sky Cyan
  '#0096fa', // Bar 2 - Electric Blue
  '#3b82f6', // Bar 3 - Deep Blue
  '#6366f1', // Bar 4 - Indigo (Center)
  '#8b5cf6', // Bar 5 - Purple
  '#a855f7', // Bar 6 - Magenta Purple
  '#c084fc', // Bar 7 - Lavender
  '#e879f9', // Bar 8 - Neon Pink
]

const LEFT_DOT_COLORS = ['#00f0ff', '#00d2ff', '#00b4ff']
const RIGHT_DOT_COLORS = ['#e879f9', '#f472b6', '#fb7185']

const NOTCH_W = 270
const NOTCH_BASE_H = 32
const LIP_W = 8
const FLARE_W = 25

// Smooth flared S-curve matching user's design profile
const NOTCH_STROKE = [
  `M 0 0.5`,
  `L ${LIP_W} 0.5`,
  `C ${LIP_W + 0.55 * FLARE_W} 0.5, ${LIP_W + FLARE_W - 0.5 * FLARE_W} ${NOTCH_BASE_H}, ${LIP_W + FLARE_W} ${NOTCH_BASE_H}`,
  `L ${NOTCH_W - LIP_W - FLARE_W} ${NOTCH_BASE_H}`,
  `C ${NOTCH_W - LIP_W - FLARE_W + 0.5 * FLARE_W} ${NOTCH_BASE_H}, ${NOTCH_W - LIP_W - 0.55 * FLARE_W} 0.5, ${NOTCH_W - LIP_W} 0.5`,
  `L ${NOTCH_W} 0.5`,
].join(' ')
const NOTCH_FILL = `${NOTCH_STROKE} L ${NOTCH_W} 0 L 0 0 Z`

export const FloatingMicWidget: React.FC<FloatingMicWidgetProps> = ({
  isListening,
  isSupported,
  isUniversalMode: _isUniversalMode,
  isCommandMode: _isCommandMode,
  isTranslationEnabled: _isTranslationEnabled = false,
  targetLanguageName: _targetLanguageName = 'English',
  isConsensusMode: _isConsensusMode = false,
  consensusCount: _consensusCount = 0,
  audioLevel = 0,
  isProcessing = false,
  isSuccess = false,
  successMessage,
  onToggleListening,
  onCancelListening,
  onToggleUniversalMode: _onToggleUniversalMode,
  onToggleCommandMode: _onToggleCommandMode,
  onToggleTranslation: _onToggleTranslation,
  onClearText,
  onToggleConsensus: _onToggleConsensus,
  onConsensusComplete: _onConsensusComplete,
  onClose: _onClose,
  interimTranscript,
  recentTranscript,
  statusMessage,
  isContinuousListening = false,
}) => {
  const [isHovered, setIsHovered] = useState(false)
  const [isManuallyCollapsed, setIsManuallyCollapsed] = useState(false)
  const [tooltipId, setTooltipId] = useState<string | null>(null)

  const textPreviewRef = useRef<HTMLDivElement>(null)
  const smoothedLevelRef = useRef(0)
  const [animatedHeights, setAnimatedHeights] = useState<number[]>([2.2, 3.2, 4.5, 6.5, 9.0, 6.5, 4.5, 3.2, 2.2])
  const [dotPulse, setDotPulse] = useState(1)

  // Auto-scroll transcript preview
  useEffect(() => {
    if (textPreviewRef.current) {
      textPreviewRef.current.scrollLeft = textPreviewRef.current.scrollWidth
    }
  }, [interimTranscript, recentTranscript])

  // ── 60fps Amplitude Waveform Engine ────────────────────────────────────────
  useEffect(() => {
    let animId: number
    let phase = 0

    const renderWave = () => {
      phase += 0.08
      const targetLevel = isListening ? Math.max(0.12, Math.min(1.0, audioLevel)) : 0.05
      const current = smoothedLevelRef.current
      const attack = 0.35
      const decay = 0.09
      const next = current + (targetLevel - current) * (targetLevel > current ? attack : decay)
      smoothedLevelRef.current = next

      const heights = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => {
        const dist = Math.abs(i - 4)
        const bell = Math.exp(-(dist * dist) / 5.0)
        if (isListening) {
          const harmonic = Math.sin(phase * 1.8 + i * 0.75) * (1.5 * bell)
          const baseHeight = 2.2 + next * 7.5 * bell + harmonic
          return Math.min(10.5, Math.max(2.0, Math.round(baseHeight * 10) / 10))
        } else {
          const idleWave = Math.sin(phase * 0.7 + i * 0.5) * 0.7
          return Math.max(1.8, Math.round((2.2 + idleWave * bell) * 10) / 10)
        }
      })

      setAnimatedHeights(heights)
      setDotPulse(isListening ? 1.0 + next * 0.28 : 1.0)
      animId = requestAnimationFrame(renderWave)
    }

    animId = requestAnimationFrame(renderWave)
    return () => cancelAnimationFrame(animId)
  }, [isListening, audioLevel])

  useEffect(() => {
    if (isListening || isProcessing || isSuccess) {
      setIsManuallyCollapsed(false)
    }
  }, [isListening, isProcessing, isSuccess])

  const isExpanded = (!isManuallyCollapsed && isHovered) || isListening || isProcessing || isSuccess
  const activeTranscript = interimTranscript || recentTranscript || ''

  // Compact dimensions
  const W = NOTCH_W
  const H = isExpanded ? NOTCH_BASE_H : 7

  const handleCenterClick = () => {
    void tauriBridge.centerTopNotch()
  }

  const handleCrossClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isListening && onCancelListening) {
      onCancelListening()
    } else {
      onClearText()
    }
  }

  return (
    <div
      className={`notch-dock ${isExpanded ? 'notch-expanded-state' : 'notch-collapsed-state'}`}
      style={{ width: `${W}px`, height: `${H}px` }}
      onMouseEnter={() => {
        setIsHovered(true)
        setIsManuallyCollapsed(false)
      }}
      onMouseLeave={() => {
        setIsHovered(false)
      }}
    >
      {/* ── Vector SVG Backdrop with Smooth Curved Wings & Glowing Neon Contour ── */}
      <svg
        className="notch-svg-backdrop"
        viewBox={`0 0 ${W} ${NOTCH_BASE_H}`}
        preserveAspectRatio="none"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="notchNeonGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00f0ff" />
            <stop offset="25%" stopColor="#00a8ff" />
            <stop offset="55%" stopColor="#8b5cf6" />
            <stop offset="80%" stopColor="#c084fc" />
            <stop offset="100%" stopColor="#f472b6" />
          </linearGradient>

          <filter id="notchNeonGlow" x="-20%" y="-20%" width="140%" height="160%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Frosted Dark Glass Body Fill */}
        <path d={NOTCH_FILL} fill="rgba(9, 11, 22, 0.88)" />

        {/* Ambient Glow underlay */}
        <path
          d={NOTCH_STROKE}
          stroke="url(#notchNeonGradient)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.4"
          filter="url(#notchNeonGlow)"
          vectorEffect="non-scaling-stroke"
        />

        {/* Crisp Radiant Neon Contour Stroke */}
        <path
          d={NOTCH_STROKE}
          stroke="url(#notchNeonGradient)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      {/* ── Interactive Content Layer (Smooth Symmetric Transition) ── */}
      <div className="notch-content-container" style={{ width: `${W}px`, height: `${H}px` }}>
        {/* Collapsed State Row: Subtle Breathing Center Indicator */}
        <div
          className={`notch-collapsed-row ${!isExpanded ? 'notch-fade-visible' : 'notch-fade-hidden'}`}
          onClick={() => setIsManuallyCollapsed(false)}
        >
          <div className="notch-collapsed-glow-dot" />
        </div>

        {/* Expanded State Row: Compact Control Bar */}
        <div className={`notch-control-row ${isExpanded ? 'notch-fade-visible' : 'notch-fade-hidden'}`}>
          {/* Left: Compact Circular Mic Button */}
          <div className="notch-mic-unit">
            <button
              className={`notch-btn-mic ${isListening ? 'notch-btn-mic-live' : ''} ${isProcessing ? 'notch-btn-mic-proc' : ''} ${isSuccess ? 'notch-btn-mic-ok' : ''}`}
              onClick={onToggleListening}
              disabled={!isSupported || isProcessing}
              onMouseEnter={() => setTooltipId('mic')}
              onMouseLeave={() => setTooltipId(null)}
              aria-label={isListening ? 'Stop Recording' : 'Start Recording'}
            >
              {isListening ? (
                <Square size={8} fill="currentColor" strokeWidth={0} />
              ) : isProcessing ? (
                <Sparkles size={11} strokeWidth={2.2} className="notch-anim-spin" />
              ) : isSuccess ? (
                <Check size={11} strokeWidth={2.6} className="notch-anim-check" />
              ) : (
                <Mic size={11} strokeWidth={2.2} />
              )}
            </button>

            {tooltipId === 'mic' && !isListening && !isProcessing && (
              <span className="notch-hint-tooltip">` hold · 2×tap continuous</span>
            )}
          </div>

          {/* Center: Amplitude Waveform Cluster + Speech Preview */}
          {/* No native `title` attribute — on a transparent always-on-top
              window the OS tooltip renders as an opaque white box. */}
          <div
            className="notch-visualizer-unit"
            onDoubleClick={handleCenterClick}
          >
            {/* Waveform: 3 Dots + 9 Capsule Bars + 3 Dots */}
            <div className="notch-waveform-row" aria-hidden="true">
              {/* Left 3 Dots */}
              <div className="notch-dots-box">
                {LEFT_DOT_COLORS.map((color, i) => (
                  <span
                    key={`ldot-${i}`}
                    className="notch-wave-dot"
                    style={{
                      backgroundColor: color,
                      boxShadow: `0 0 4px ${color}`,
                      transform: `scale(${dotPulse})`,
                      opacity: 0.5 + i * 0.22,
                    }}
                  />
                ))}
              </div>

              {/* 9 Center Capsule Bars */}
              <div className="notch-bars-box">
                {animatedHeights.map((h, i) => (
                  <span
                    key={`bar-${i}`}
                    className="notch-wave-bar"
                    style={{
                      height: `${h}px`,
                      backgroundColor: BAR_COLORS[i],
                      boxShadow: `0 0 5px ${BAR_COLORS[i]}`,
                    }}
                  />
                ))}
              </div>

              {/* Right 3 Dots */}
              <div className="notch-dots-box">
                {RIGHT_DOT_COLORS.map((color, i) => (
                  <span
                    key={`rdot-${i}`}
                    className="notch-wave-dot"
                    style={{
                      backgroundColor: color,
                      boxShadow: `0 0 4px ${color}`,
                      transform: `scale(${dotPulse})`,
                      opacity: 0.94 - i * 0.22,
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Live Transcript Stream or Status */}
            <div ref={textPreviewRef} className="notch-text-stream">
              {isProcessing ? (
                <span className="notch-msg-text notch-msg-polishing">
                  {statusMessage || 'Polishing…'}
                </span>
              ) : isSuccess ? (
                <span className="notch-msg-text notch-msg-success">
                  {successMessage || 'Injected!'}
                </span>
              ) : isListening && activeTranscript ? (
                <span className="notch-stream-preview">{activeTranscript}</span>
              ) : isListening ? (
                <span className="notch-msg-text">
                  {isContinuousListening ? 'Continuous listening' : (statusMessage || 'Push to talk')}
                </span>
              ) : (
                <span className="notch-msg-text notch-msg-idle">
                  {statusMessage || '` Hold or 2x tap'}
                </span>
              )}
            </div>
          </div>

          {/* Right: Actions Cluster (Only Cross 'X' Button) */}
          <div className="notch-actions-unit">
            <button
              className="notch-btn-icon notch-btn-close"
              onClick={handleCrossClick}
              aria-label={isListening ? 'Stop Listening' : 'Clear'}
            >
              <X size={11} strokeWidth={2.4} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default FloatingMicWidget
