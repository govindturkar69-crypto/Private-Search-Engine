import React, { useEffect, useRef, useState } from 'react'
import { adminClient } from '../../api/adminClient'
import type { LogEntry } from '../../types'

export const LogViewer: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [lines, setLines] = useState<number>(100)
  const [levelFilter, setLevelFilter] = useState<string>('ALL')
  const [autoRefresh, setAutoRefresh] = useState<boolean>(false)

  const timerRef = useRef<number | null>(null)
  const logContainerRef = useRef<HTMLDivElement | null>(null)

  const fetchLogs = async () => {
    try {
      const data = await adminClient.getLogs(lines, levelFilter)
      setLogs(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch application logs.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [lines, levelFilter])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = window.setInterval(fetchLogs, 3000)
    } else if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current)
      }
    }
  }, [autoRefresh, lines, levelFilter])

  const getLevelBadgeClass = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
      case 'CRITICAL':
        return 'log-badge-error'
      case 'WARNING':
      case 'WARN':
        return 'log-badge-warning'
      case 'DEBUG':
        return 'log-badge-debug'
      default:
        return 'log-badge-info'
    }
  }

  return (
    <div className="admin-section log-viewer-panel">
      <div className="section-header">
        <div>
          <h2>Application Logs</h2>
          <p className="section-subtitle">
            Bounded tail of server activity with automated credential and token redaction
          </p>
        </div>
        <div className="log-controls">
          <div className="control-item">
            <label htmlFor="logLines">Lines:</label>
            <select
              id="logLines"
              className="form-select form-select-sm"
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={250}>250</option>
              <option value={500}>500</option>
            </select>
          </div>

          <div className="control-item">
            <label htmlFor="logLevel">Level:</label>
            <select
              id="logLevel"
              className="form-select form-select-sm"
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
            >
              <option value="ALL">All Levels</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>

          <label className="toggle-label">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-tail (3s)</span>
          </label>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchLogs}
            disabled={loading}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="admin-alert alert-error" role="alert">
          <span className="alert-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      <div className="logs-terminal" ref={logContainerRef}>
        {loading && logs.length === 0 ? (
          <div className="terminal-placeholder">Loading log stream...</div>
        ) : logs.length === 0 ? (
          <div className="terminal-placeholder">No log entries found.</div>
        ) : (
          <div className="logs-list">
            {logs.map((entry, idx) => (
              <div key={`log-${idx}`} className="log-row">
                <span className="log-timestamp">{entry.timestamp}</span>
                <span className={`log-badge ${getLevelBadgeClass(entry.level)}`}>
                  {entry.level}
                </span>
                <span className="log-module">[{entry.module}]</span>
                <span className="log-message">{entry.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

