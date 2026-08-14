import React, { useState } from 'react'
import './AdminPanel.css'

interface AdminPanelProps {
  onClose: () => void
  username: string
}

type Tab = 'users' | 'settings' | 'logs'

const AdminPanel: React.FC<AdminPanelProps> = ({ onClose, username }) => {
  const [activeTab, setActiveTab] = useState<Tab>('users')

  return (
    <div className="admin-overlay" onClick={onClose}>
      <div className="admin-panel glass" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="admin-header">
          <div className="admin-title">
            <span className="admin-icon">🎨</span>
            <span>Admin Panel</span>
          </div>
          <div className="admin-actions">
            <button className="admin-action-btn">⚙️</button>
            <button className="admin-close-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="admin-tabs">
          <button
            className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            User Management
          </button>
          <button
            className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            App Settings
          </button>
          <button
            className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            System Logs
          </button>
        </div>

        {/* Tab Content */}
        <div className="admin-content">
          {activeTab === 'users' && (
            <div className="users-tab">
              <div className="users-list">
                <div className="user-item active">
                  <span className="user-status">✓</span>
                  <span className="user-name">{username}</span>
                  <span className="user-role">Standard User</span>
                </div>
                <div className="user-item active">
                  <span className="user-status">✓</span>
                  <span className="user-name">Maria</span>
                  <span className="user-role">Power User</span>
                </div>
                <div className="user-item">
                  <span className="user-status">○</span>
                  <span className="user-name">John</span>
                  <span className="user-role">Developer</span>
                </div>
              </div>
              <button className="add-user-btn">
                <span>Add New User</span>
                <span>→</span>
              </button>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="settings-tab">
              <label className="setting-item">
                <input type="checkbox" defaultChecked />
                <span>Start with Windows</span>
              </label>
              <label className="setting-item">
                <input type="checkbox" defaultChecked />
                <span>Minimize to tray</span>
              </label>
              <label className="setting-item">
                <input type="checkbox" defaultChecked />
                <span>Voice wake word enabled</span>
              </label>
              <label className="setting-item">
                <input type="checkbox" />
                <span>Auto-start recording</span>
              </label>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="logs-tab">
              <div className="logs-container">
                <p>[{new Date().toLocaleTimeString()}] System initialized</p>
                <p>[{new Date().toLocaleTimeString()}] Welcome, {username}</p>
                <p>[{new Date().toLocaleTimeString()}] AI models loaded</p>
                <p>[{new Date().toLocaleTimeString()}] Backend connected</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AdminPanel