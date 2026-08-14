import React, { useEffect, useRef, useState } from 'react'
import './VoiceControlBar.css'

interface VoiceControlBarProps {
  isListening: boolean
  isSupported: boolean
  onStart: () => void
  onStop: () => void
}

const VoiceControlBar: React.FC<VoiceControlBarProps> = ({ isListening, isSupported, onStart, onStop }) => {
  const [levels, setLevels] = useState<number[]>(Array(15).fill(20))
  const animationRef = useRef<number>()

  useEffect(() => {
    if (!isListening) { setLevels(Array(15).fill(20)); return }
    const animate = () => {
      setLevels(previous => previous.map(() => Math.random() * 70 + 25))
      animationRef.current = requestAnimationFrame(animate)
    }
    animate()
    return () => { if (animationRef.current) cancelAnimationFrame(animationRef.current) }
  }, [isListening])

  return (
    <div className="voice-bar">
      <div className="voice-visualizer" aria-label={isListening ? 'Voice input active' : 'Voice input inactive'}>
        {levels.map((level, index) => <div key={index} className="voice-bar-item" style={{ height: `${(level / 100) * 40}px` }} />)}
      </div>
      <div className="voice-spacer" />
      <span className="voice-mode-label">{isListening ? 'Listening...' : 'Voice input'}</span>
      <button
        className={`mic-btn ${isListening ? 'listening' : ''}`}
        aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
        title={isSupported ? (isListening ? 'Stop listening' : 'Start continuous voice input') : 'Speech recognition is not supported'}
        disabled={!isSupported}
        onClick={isListening ? onStop : onStart}
      >
        {isListening ? '■' : '🎙'}
      </button>
      <div className="voice-spacer" />
    </div>
  )
}

export default VoiceControlBar
