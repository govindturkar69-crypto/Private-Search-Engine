import React from 'react'
import type { Theme } from '../types'
import '../styles/Header.css'

interface HeaderProps {
  totalDocs: number
  indexReady: boolean
  theme: Theme
  onToggleTheme: () => void
}

export const Header: React.FC<HeaderProps> = ({
  totalDocs,
  indexReady,
  theme,
  onToggleTheme,
}) => {
  return (
    <header className="header" role="banner">
      <div className="header-container">
        <div className="header-brand">
          <div>
            <h1 className="header-title">🔍 Private Search</h1>
            <p className="header-subtitle">Self-hosted • Privacy-first • Instant results</p>
          </div>
        </div>
        <div className="header-actions">
          <span
            className={`status-badge ${indexReady ? 'ready' : 'loading'}`}
            role="status"
            aria-live="polite"
          >
            <span aria-hidden="true">{indexReady ? '●' : '○'}</span>
            {indexReady ? 'Ready' : 'Initializing'}
          </span>
          <span className="doc-count" aria-label={`${totalDocs} documents indexed`}>
            {totalDocs.toLocaleString()} docs
          </span>
          <a
            href="/admin"
            className="admin-link-btn"
            title="Open Admin Dashboard"
            aria-label="Open Admin Dashboard"
          >
            ⚙️ Admin
          </a>
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={onToggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
    </header>
  )
}

