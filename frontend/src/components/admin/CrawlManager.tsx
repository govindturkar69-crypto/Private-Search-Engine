import React, { useEffect, useRef, useState } from 'react'
import { adminClient } from '../../api/adminClient'
import type { CrawlPriority, CrawlResponse, CrawlStatus } from '../../types'

export const CrawlManager: React.FC = () => {
  const [crawlState, setCrawlState] = useState<CrawlResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Form states
  const [seedsText, setSeedsText] = useState<string>('https://example.com')
  const [maxDocuments, setMaxDocuments] = useState<number>(500)
  const [maxDepth, setMaxDepth] = useState<number>(2)
  const [priority, setPriority] = useState<CrawlPriority>('normal')

  const pollTimerRef = useRef<number | null>(null)

  const fetchStatus = async () => {
    try {
      const data = await adminClient.getCrawlerStatus()
      setCrawlState(data)
      setError(null)
      return data
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch crawler status'
      setError(msg)
      return null
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus().then((current) => {
      if (current?.status === 'running' || current?.status === 'paused') {
        startPolling()
      }
    })

    return () => stopPolling()
  }, [])

  const startPolling = () => {
    stopPolling()
    pollTimerRef.current = window.setInterval(async () => {
      const res = await fetchStatus()
      if (res && res.status !== 'running' && res.status !== 'paused') {
        stopPolling()
      }
    }, 2000)
  }

  const stopPolling = () => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    const rawSeeds = seedsText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    if (rawSeeds.length === 0) {
      setError('Please provide at least 1 seed URL.')
      return
    }

    if (rawSeeds.length > 10) {
      setError('Maximum 10 seed URLs allowed per crawl.')
      return
    }

    if (maxDocuments < 1 || maxDocuments > 10000) {
      setError('Max documents must be between 1 and 10,000.')
      return
    }

    if (maxDepth < 1 || maxDepth > 5) {
      setError('Max depth must be between 1 and 5.')
      return
    }

    setActionLoading(true)
    try {
      const res = await adminClient.startCrawler({
        seed_urls: rawSeeds,
        max_documents: maxDocuments,
        max_depth: maxDepth,
        priority,
      })
      setCrawlState(res)
      startPolling()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start crawl')
    } finally {
      setActionLoading(false)
    }
  }

  const handlePause = async () => {
    setActionLoading(true)
    try {
      const res = await adminClient.pauseCrawler()
      setCrawlState(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to pause crawl')
    } finally {
      setActionLoading(false)
    }
  }

  const handleResume = async () => {
    setActionLoading(true)
    try {
      const res = await adminClient.resumeCrawler()
      setCrawlState(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to resume crawl')
    } finally {
      setActionLoading(false)
    }
  }

  const handleStop = async () => {
    setActionLoading(true)
    try {
      const res = await adminClient.stopCrawler()
      setCrawlState(res)
      stopPolling()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to stop crawl')
    } finally {
      setActionLoading(false)
    }
  }

  const status: CrawlStatus = crawlState?.status || 'idle'
  const isRunning = status === 'running'
  const isPaused = status === 'paused'
  const canStart = !isRunning && !isPaused

  const getStatusBadgeClass = (s: CrawlStatus) => {
    switch (s) {
      case 'running':
        return 'badge-running'
      case 'paused':
        return 'badge-paused'
      case 'stopped':
        return 'badge-stopped'
      case 'error':
        return 'badge-error'
      default:
        return 'badge-idle'
    }
  }

  return (
    <div className="admin-section crawl-manager">
      <div className="section-header">
        <div>
          <h2>Web Crawler Orchestration</h2>
          <p className="section-subtitle">
            Configure seed targets and monitor live background crawling jobs
          </p>
        </div>
        <div className="status-indicator-box">
          <span className="status-label">Status:</span>
          <span className={`status-badge ${getStatusBadgeClass(status)}`}>
            {status.toUpperCase()}
          </span>
        </div>
      </div>

      {error && (
        <div className="admin-alert alert-error" role="alert">
          <span className="alert-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="admin-loading">Loading crawler telemetry...</div>
      ) : (
        <>
          {/* Telemetry Progress Overview */}
          <div className="telemetry-card">
            <div className="telemetry-header">
              <span className="job-id">Job ID: {crawlState?.crawl_id || 'None'}</span>
              {crawlState?.start_time && (
                <span className="job-time">
                  Started: {new Date(crawlState.start_time).toLocaleTimeString()}
                </span>
              )}
            </div>

            <div className="progress-bar-container">
              <div
                className="progress-bar-fill"
                style={{ width: `${crawlState?.progress_percent || 0}%` }}
              />
            </div>
            <div className="progress-meta">
              <span>{crawlState?.progress_percent || 0}% Complete</span>
              {crawlState?.current_url && (
                <span className="active-url" title={crawlState.current_url}>
                  Crawling: {crawlState.current_url}
                </span>
              )}
            </div>

            <div className="metrics-grid">
              <div className="metric-box">
                <span className="metric-value">{crawlState?.documents_crawled || 0}</span>
                <span className="metric-title">Crawled</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{crawlState?.documents_indexed || 0}</span>
                <span className="metric-title">Indexed</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{crawlState?.errors || 0}</span>
                <span className="metric-title">Errors</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{crawlState?.urls_queued || 0}</span>
                <span className="metric-title">Queue Size</span>
              </div>
            </div>

            <div className="control-actions">
              {isRunning && (
                <button
                  type="button"
                  className="btn btn-warning"
                  onClick={handlePause}
                  disabled={actionLoading}
                >
                  Pause Crawl
                </button>
              )}
              {isPaused && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleResume}
                  disabled={actionLoading}
                >
                  Resume Crawl
                </button>
              )}
              {(isRunning || isPaused) && (
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleStop}
                  disabled={actionLoading}
                >
                  Stop Crawl
                </button>
              )}
            </div>
          </div>

          {/* New Crawl Initiation Form */}
          <div className="config-card">
            <h3>Initiate New Crawl Job</h3>
            <form onSubmit={handleStart} className="crawl-form">
              <div className="form-group">
                <label htmlFor="seedUrls">
                  Seed URLs (one per line or comma-separated, max 10):
                </label>
                <textarea
                  id="seedUrls"
                  className="form-textarea"
                  rows={3}
                  value={seedsText}
                  onChange={(e) => setSeedsText(e.target.value)}
                  disabled={!canStart || actionLoading}
                  placeholder="https://example.com&#10;https://docs.example.org"
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="maxDocs">Max Documents (1–10,000):</label>
                  <input
                    id="maxDocs"
                    type="number"
                    className="form-input"
                    min={1}
                    max={10000}
                    value={maxDocuments}
                    onChange={(e) => setMaxDocuments(Number(e.target.value))}
                    disabled={!canStart || actionLoading}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="maxDepth">Max Link Depth (1–5):</label>
                  <input
                    id="maxDepth"
                    type="number"
                    className="form-input"
                    min={1}
                    max={5}
                    value={maxDepth}
                    onChange={(e) => setMaxDepth(Number(e.target.value))}
                    disabled={!canStart || actionLoading}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="priority">Crawl Priority:</label>
                  <select
                    id="priority"
                    className="form-select"
                    value={priority}
                    onChange={(e) => setPriority(e.target.value as CrawlPriority)}
                    disabled={!canStart || actionLoading}
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="btn btn-primary btn-start"
                disabled={!canStart || actionLoading}
              >
                {actionLoading ? 'Starting...' : 'Launch Crawler'}
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  )
}

