import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminClient } from '../api/adminClient'
import { ConfigManager } from '../components/admin/ConfigManager'
import { CrawlManager } from '../components/admin/CrawlManager'
import { LogViewer } from '../components/admin/LogViewer'
import { StatisticsPanel } from '../components/admin/StatisticsPanel'
import { SystemMetrics } from '../components/admin/SystemMetrics'
import '../styles/AdminDashboard.css'

type AdminTab = 'crawler' | 'index' | 'system' | 'logs' | 'config'

export const AdminDashboard: React.FC = () => {
  const [authenticated, setAuthenticated] = useState<boolean>(false)
  const [checkingAuth, setCheckingAuth] = useState<boolean>(true)
  const [tokenInput, setTokenInput] = useState<string>('')
  const [authError, setAuthError] = useState<string | null>(null)
  const [submittingToken, setSubmittingToken] = useState<boolean>(false)
  const [activeTab, setActiveTab] = useState<AdminTab>('crawler')

  // Verify existing session token on mount
  useEffect(() => {
    const existingToken = adminClient.getAuthToken()
    if (!existingToken) {
      setCheckingAuth(false)
      return
    }

    adminClient
      .checkHealth()
      .then(() => {
        setAuthenticated(true)
      })
      .catch(() => {
        adminClient.clearAuthToken()
        setAuthenticated(false)
      })
      .finally(() => {
        setCheckingAuth(false)
      })
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = tokenInput.trim()
    if (!trimmed) {
      setAuthError('Please enter an admin token.')
      return
    }

    setSubmittingToken(true)
    setAuthError(null)

    adminClient.setAuthToken(trimmed)
    try {
      await adminClient.checkHealth()
      setAuthenticated(true)
      setTokenInput('')
    } catch (err: unknown) {
      adminClient.clearAuthToken()
      setAuthenticated(false)
      setAuthError(
        err instanceof Error ? err.message : 'Invalid admin token. Access denied.'
      )
    } finally {
      setSubmittingToken(false)
    }
  }

  const handleLogout = () => {
    adminClient.clearAuthToken()
    setAuthenticated(false)
    setAuthError(null)
  }

  if (checkingAuth) {
    return (
      <div className="admin-container admin-centered">
        <div className="admin-loading-card">
          <div className="spinner" />
          <p>Verifying admin authorization...</p>
        </div>
      </div>
    )
  }

  // Authentication Gate
  if (!authenticated) {
    return (
      <div className="admin-container admin-centered">
        <div className="admin-login-card">
          <div className="login-header">
            <span className="login-badge">Restricted Access</span>
            <h2>Admin Authentication</h2>
            <p>Enter your engine administrator token to access system operations.</p>
          </div>

          {authError && (
            <div className="admin-alert alert-error" role="alert">
              <span className="alert-icon">⚠️</span>
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="login-form">
            <div className="form-group">
              <label htmlFor="adminToken">Admin Token</label>
              <input
                id="adminToken"
                type="password"
                className="form-input"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Enter secret token..."
                autoFocus
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={submittingToken}
            >
              {submittingToken ? 'Verifying...' : 'Authenticate'}
            </button>
          </form>

          <div className="login-footer">
            <Link to="/" className="back-link">
              ← Return to Search
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // Authenticated Admin Dashboard Layout
  return (
    <div className="admin-layout">
      {/* Top Admin Navigation Bar */}
      <header className="admin-navbar">
        <div className="admin-nav-left">
          <Link to="/" className="admin-logo">
            Private Search Engine
          </Link>
          <span className="admin-badge">Admin Portal</span>
        </div>
        <div className="admin-nav-right">
          <Link to="/" className="nav-action-link">
            ← Search Engine
          </Link>
          <button
            type="button"
            className="btn btn-sm btn-logout"
            onClick={handleLogout}
          >
            Logout
          </button>
        </div>
      </header>

      {/* Main Admin Content */}
      <main className="admin-main">
        {/* Navigation Tabs */}
        <nav className="admin-tabs" aria-label="Admin Navigation Tabs">
          <button
            type="button"
            className={`admin-tab-btn ${activeTab === 'crawler' ? 'active' : ''}`}
            onClick={() => setActiveTab('crawler')}
          >
            🕷️ Crawler
          </button>
          <button
            type="button"
            className={`admin-tab-btn ${activeTab === 'index' ? 'active' : ''}`}
            onClick={() => setActiveTab('index')}
          >
            📊 Index & Stats
          </button>
          <button
            type="button"
            className={`admin-tab-btn ${activeTab === 'system' ? 'active' : ''}`}
            onClick={() => setActiveTab('system')}
          >
            ⚡ System Resources
          </button>
          <button
            type="button"
            className={`admin-tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            📜 Logs
          </button>
          <button
            type="button"
            className={`admin-tab-btn ${activeTab === 'config' ? 'active' : ''}`}
            onClick={() => setActiveTab('config')}
          >
            ⚙️ Configuration
          </button>
        </nav>

        {/* Tab Content Display */}
        <div className="admin-tab-content">
          {activeTab === 'crawler' && <CrawlManager />}
          {activeTab === 'index' && <StatisticsPanel />}
          {activeTab === 'system' && <SystemMetrics />}
          {activeTab === 'logs' && <LogViewer />}
          {activeTab === 'config' && <ConfigManager />}
        </div>
      </main>
    </div>
  )
}

