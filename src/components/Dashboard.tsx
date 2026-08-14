import React from 'react'
import MusicPlayer from './MusicPlayer'
import './Dashboard.css'

interface DashboardProps {
  onAction: (action: string) => void
  transcript: string
  interimTranscript: string
  isListening: boolean
  isSupported: boolean
  error: string | null
  clearTranscript: () => void
}

const tiles = [
  { icon: '💬', title: 'Send a Message', subtitle: 'WhatsApp, Telegram, Instagram' },
  { icon: '🎧', title: 'Play Music', subtitle: 'Select a song to play' },
  { icon: '🔧', title: 'Control System', subtitle: 'Volume, Brightness, Power' },
  { icon: '📝', title: 'Create a Note', subtitle: 'Add a new note' }
]

const quickActions = [
  { icon: '▶', label: 'Open YouTube', action: 'youtube', color: '#ff0000' },
  { icon: '⏰', label: 'Set Reminder', action: 'reminder', color: '#f59e0b' },
  { icon: '⏻', label: 'Turn Off PC', action: 'shutdown', color: '#ef4444' },
  { icon: '🔒', label: 'Lock Screen', action: 'lock', color: '#6366f1' }
]

const Dashboard: React.FC<DashboardProps> = ({ onAction, transcript, interimTranscript, isListening, isSupported, error, clearTranscript }) => {
  const handleQuickAction = async (action: string) => {
    if (window.electronAPI?.system) {
      switch (action) {
        case 'youtube':
          await window.electronAPI.system.openYouTube()
          break
        case 'reminder':
          await window.electronAPI.system.openReminder()
          break
        case 'shutdown':
          if (confirm('Are you sure you want to shutdown your PC?')) {
            await window.electronAPI.system.shutdown()
          }
          break
        case 'lock':
          await window.electronAPI.system.lock()
          break
      }
    }
    onAction(action)
  }

  return (
    <div className="dashboard">
      <section className="voice-workspace glass">
        <div className="voice-workspace-header">
          <div>
            <p className="eyebrow">VOICE WORKSPACE</p>
            <h2>Talk naturally. See it instantly.</h2>
            <p className="voice-description">Your words will appear here in real time while the microphone is active.</p>
          </div>
          <div className={`listening-status ${isListening ? 'active' : ''}`}>
            <span className="status-dot" />
            {isListening ? 'Listening continuously' : 'Ready when you are'}
          </div>
        </div>
        <div className="transcript-box" aria-live="polite">
          {transcript || interimTranscript ? <p>{transcript}<span className="interim-text">{interimTranscript}</span></p> : <p className="transcript-placeholder">Press the microphone below and start speaking...</p>}
        </div>
        <div className="voice-workspace-footer">
          <span>{isSupported ? 'Browser speech recognition connected' : 'Speech recognition is not supported in this window'}</span>
          {(transcript || interimTranscript) && <button onClick={clearTranscript}>Clear transcript</button>}
        </div>
        {error && <p className="voice-error">{error}</p>}
      </section>

      {/* Dashboard Tiles */}
      <div className="tiles-row">
        {tiles.map((tile, i) => (
          <div key={i} className="dashboard-tile glass" onClick={() => onAction(tile.title)}>
            <span className="tile-icon">{tile.icon}</span>
            <h3 className="tile-title">{tile.title}</h3>
            <p className="tile-subtitle">{tile.subtitle}</p>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="section">
        <h2 className="section-title">Quick Actions</h2>
        <div className="quick-actions">
          {quickActions.map((action, i) => (
            <button
              key={i}
              className="quick-btn"
              style={{ '--accent-color': action.color } as React.CSSProperties}
              onClick={() => handleQuickAction(action.action)}
            >
              <span className="quick-icon">{action.icon}</span>
              <span>{action.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Music Player */}
      <MusicPlayer />
    </div>
  )
}

export default Dashboard
