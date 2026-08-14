import React from 'react'
import './MusicPlayer.css'

const MusicPlayer: React.FC = () => {
  return (
    <div className="music-player glass">
      {/* Album Art */}
      <div className="album-art">
        <span>🎵</span>
      </div>

      {/* Track Info */}
      <div className="track-info">
        <h4 className="track-title">Shape of You</h4>
        <p className="track-artist">Ed Sheeran</p>

        {/* Progress Bar */}
        <div className="progress-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: '40%' }} />
          </div>
          <div className="time-display">
            <span>03:54</span>
            <span>04:00</span>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="player-controls">
        <button className="control-btn">⏮</button>
        <button className="control-btn primary">⏸</button>
        <button className="control-btn">⏭</button>
      </div>
    </div>
  )
}

export default MusicPlayer