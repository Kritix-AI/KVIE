import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { getCurrentWindow, PhysicalPosition, PhysicalSize, currentMonitor } from '@tauri-apps/api/window'
import {
  Mic,
  Square,
  Zap,
  ClipboardCheck,
  Trash2,
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
  ChevronLeft,
  ChevronRight,
  GripVertical,
  Sparkles,
  Languages,
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
  isDesktop: boolean
  onToggleListening: () => void
  onToggleUniversalMode: () => void
  onToggleCommandMode?: () => void
  onToggleTranslation?: () => void
  onInjectCurrentText: () => void
  onClearText: () => void
  interimTranscript?: string
  recentTranscript?: string
  statusMessage?: string | null
  isStandalone?: boolean
}

type DockEdge = 'right' | 'left' | 'top' | 'bottom' | null

export const FloatingMicWidget: React.FC<FloatingMicWidgetProps> = ({
  isListening,
  isSupported,
  isUniversalMode,
  isCommandMode,
  isTranslationEnabled = false,
  targetLanguageName = 'English',
  isDesktop,
  onToggleListening,
  onToggleUniversalMode,
  onToggleCommandMode,
  onToggleTranslation,
  onInjectCurrentText,
  onClearText,
  interimTranscript,
  recentTranscript,
  statusMessage,
  isStandalone = false,
}) => {
  const [position, setPosition] = useState({ x: window.innerWidth - 340, y: window.innerHeight - 130 })
  const [isDragging, setIsDragging] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [dockEdge, setDockEdge] = useState<DockEdge>(null)

  const dragStartRef = useRef({ x: 0, y: 0 })
  const initialPosRef = useRef({ x: 0, y: 0 })

  const handleMouseDown = (e: React.MouseEvent) => {
    if (isDesktop) {
      void tauriBridge.startWindowDrag()
      return
    }
    setIsDragging(true)
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    initialPosRef.current = { ...position }
  }

  // Dynamic window resizing & edge positioning for desktop mode
  useEffect(() => {
    if (!isDesktop) return
    const syncWindowSizeAndPosition = async () => {
      try {
        const appWindow = getCurrentWindow()
        const monitor = await currentMonitor()
        if (!monitor) return
        const scale = monitor.scaleFactor || 1.0
        const screenWidth = monitor.size.width
        const screenHeight = monitor.size.height

        const displayText = interimTranscript || recentTranscript

        // Tight logical dimensions fitting all buttons cleanly without scrolling
        let targetWidth = 460
        let targetHeight = 70

        if (dockEdge && isCollapsed) {
          targetWidth = 110
          targetHeight = 44
        } else if (isCollapsed) {
          targetWidth = 140
          targetHeight = 65
        }

        const physicalWidth = Math.round(targetWidth * scale)
        const physicalHeight = Math.round(targetHeight * scale)

        // Dynamically resize window to match tight card bounds (no excess empty height/width)
        await appWindow.setSize(new PhysicalSize(physicalWidth, physicalHeight))

        if (dockEdge === 'right') {
          const targetX = screenWidth - physicalWidth
          const targetY = Math.round((screenHeight / 2) - (physicalHeight / 2))
          await appWindow.setPosition(new PhysicalPosition(targetX, targetY))
        }
      } catch {
        // browser fallback
      }
    }
    void syncWindowSizeAndPosition()
  }, [dockEdge, isCollapsed, isDesktop, interimTranscript, recentTranscript])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return
      const dx = e.clientX - dragStartRef.current.x
      const dy = e.clientY - dragStartRef.current.y
      const newX = initialPosRef.current.x + dx
      const newY = initialPosRef.current.y + dy

      const edgeThreshold = 50
      if (newX >= window.innerWidth - 300) {
        setDockEdge('right')
      } else if (newX <= edgeThreshold) {
        setDockEdge('left')
      } else {
        setDockEdge(null)
      }

      setPosition({ x: newX, y: newY })
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging])

  const displayText = interimTranscript || recentTranscript

  // If docked to edge and collapsed into drawer tab
  if (dockEdge && isCollapsed) {
    return (
      <div
        className={`edge-tab-handle dock-${dockEdge}`}
        onClick={() => setIsCollapsed(false)}
        title="Click to pull out Voice Mic Widget from screen edge"
        data-tauri-drag-region
      >
        <span className="edge-arrow-icon">
          {dockEdge === 'right' ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </span>
        <Mic className={`h-4 w-4 ${isListening ? 'text-rose-400 animate-pulse' : 'text-accent'}`} />
        <span className="text-xs text-zinc-300 font-medium">Mic</span>
      </div>
    )
  }

  return (
    <div
      className="floating-mic-container"
      style={isStandalone ? {} : { left: `${position.x}px`, top: `${position.y}px` }}
    >




      <div
        className={`floating-mic-card ${isUniversalMode ? 'universal-active' : ''} ${
          isListening ? 'listening' : ''
        }`}
      >
        <div
          data-tauri-drag-region
          className="floating-drag-handle"
          onMouseDown={handleMouseDown}
          title="Drag floating mic anywhere on laptop screen"
        >
          <GripVertical className="h-4 w-4" />
        </div>

        <button
          className={`floating-mic-btn ${isListening ? 'active' : ''}`}
          onClick={onToggleListening}
          disabled={!isSupported}
          title={
            !isSupported
              ? 'Speech recognition unavailable'
              : isListening
              ? 'Stop voice capture'
              : 'Start continuous voice capture'
          }
          aria-label={isListening ? 'Stop recording' : 'Start recording'}
        >
          {isListening && <div className="inner-color-beat" />}
          {isListening ? <Square className="h-4 w-4 fill-current relative z-10 text-white" /> : <Mic className="h-5 w-5 relative z-10" style={{ color: isListening ? '#ffffff' : 'var(--accent-color)' }} />}
        </button>

        {!isCollapsed && (
          <>
            <button
              className={`floating-action-btn ${isUniversalMode ? 'active-mode' : ''}`}
              onClick={onToggleUniversalMode}
              title={
                isUniversalMode
                  ? 'Universal Voice Typing ON (Auto-injects speech into WhatsApp, Notepad, Chrome, etc.)'
                  : 'Universal Voice Typing OFF (Captures to workspace only)'
              }
            >
              <Zap className="h-3.5 w-3.5" />
              {isUniversalMode ? 'Universal Auto-Inject' : 'Local Draft'}
            </button>

            {onToggleCommandMode && (
              <button
                className={`floating-action-btn ${isCommandMode ? 'active-command-mode' : ''}`}
                onClick={onToggleCommandMode}
                title={
                  isCommandMode
                    ? 'Voice Command Mode ON (Executes spoken instructions like "Make formal", "Summarize")'
                    : 'Voice Command Mode OFF (Standard Voice Dictation)'
                }
              >
                <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                {isCommandMode ? 'Command' : 'Dictate'}
              </button>
            )}

            {onToggleTranslation && (
              <button
                className={`floating-action-btn ${isTranslationEnabled ? 'active-command-mode' : ''}`}
                onClick={onToggleTranslation}
                title={
                  isTranslationEnabled
                    ? `Live Translation ON -> ${targetLanguageName} (Translates voice in real-time)`
                    : 'Live Translation OFF (Captures speech in original language)'
                }
              >
                <Languages className="h-3.5 w-3.5 text-cyan-400" />
                {isTranslationEnabled ? `-> ${targetLanguageName}` : 'Translate'}
              </button>
            )}

            <button
              className="floating-action-btn"
              onClick={onClearText}
              title="Clear text buffer"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}

        {isCollapsed ? (
          <button
            className="floating-action-btn"
            onClick={() => setIsCollapsed(false)}
            title="Expand full control bar"
          >
            <Maximize2 className="h-3.5 w-3.5" /> Expand
          </button>
        ) : (
          <button
            className="floating-action-btn"
            onClick={() => setIsCollapsed(true)}
            title="Collapse to compact mic view"
          >
            <Minimize2 className="h-3.5 w-3.5" /> Collapse
          </button>
        )}
      </div>
    </div>
  )
}

export default FloatingMicWidget
