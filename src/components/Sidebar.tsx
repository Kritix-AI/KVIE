import React, { useState } from 'react'
import './Sidebar.css'

interface SidebarProps {
  activeItem: string
  onNavChange: (item: string) => void
  onAdminClick: () => void
}

const navItems = [
  { icon: '📊', label: 'Dashboard' },
  { icon: '💬', label: 'Messages' },
  { icon: '🎵', label: 'Music' },
  { icon: '📝', label: 'Notes' },
  { icon: '⚙️', label: 'System Control' },
  { icon: '🔧', label: 'Settings' }
]

const Sidebar: React.FC<SidebarProps> = ({ activeItem, onNavChange, onAdminClick }) => {
  const [darkMode, setDarkMode] = useState(true)

  return (
    <div className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <span className="logo-icon">🎨</span>
        <span className="logo-text">AI Assistant</span>
      </div>

      {/* Mode Toggle */}
      <div className="mode-toggle glass-light">
        <span className={!darkMode ? 'active' : ''}>Light</span>
        <button
          className={`toggle-btn ${darkMode ? 'active' : ''}`}
          onClick={() => setDarkMode(!darkMode)}
        >
          <span className="toggle-knob" />
        </button>
        <span className={darkMode ? 'active' : ''}>Dark</span>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <button
            key={item.label}
            className={`nav-item ${activeItem === item.label ? 'active' : ''}`}
            onClick={() => onNavChange(item.label)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Admin Button */}
      <button className="admin-btn" onClick={onAdminClick}>
        <span>Admin Panel</span>
        <span>→</span>
      </button>
    </div>
  )
}

export default Sidebar