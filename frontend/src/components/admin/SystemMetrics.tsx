import React, { useEffect, useRef, useState } from 'react'
import { adminClient } from '../../api/adminClient'
import type { SystemMetrics as SystemMetricsType } from '../../types'

export const SystemMetrics: React.FC = () => {
  const [metrics, setMetrics] = useState<SystemMetricsType | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true)

  const timerRef = useRef<number | null>(null)

  const fetchMetrics = async () => {
    try {
      const data = await adminClient.getSystemMetrics()
      setMetrics(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to sample system metrics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMetrics()
  }, [])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = window.setInterval(fetchMetrics, 5000)
    } else if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current)
      }
    }
  }, [autoRefresh])

  const getUsageColor = (percent: number): string => {
    if (percent >= 90) return 'var(--danger-color, #ef4444)'
    if (percent >= 75) return 'var(--warning-color, #f59e0b)'
    return 'var(--primary-color, #3b82f6)'
  }

  return (
    <div className="admin-section system-metrics-panel">
      <div className="section-header">
        <div>
          <h2>System Performance & Resources</h2>
          <p className="section-subtitle">
            Measured host machine utilization sampled via non-blocking telemetry
          </p>
        </div>
        <div className="section-header-actions">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh (5s)</span>
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchMetrics}
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

      {loading && !metrics ? (
        <div className="admin-loading">Sampling host performance...</div>
      ) : (
        <div className="resource-gauges-grid">
          {/* CPU Gauge */}
          <div className="resource-card">
            <div className="resource-card-header">
              <span className="resource-title">CPU Utilization</span>
              <span className="resource-percentage">
                {metrics?.cpu_percent.toFixed(1) ?? '0.0'}%
              </span>
            </div>
            <div className="gauge-track">
              <div
                className="gauge-fill"
                style={{
                  width: `${Math.min(metrics?.cpu_percent ?? 0, 100)}%`,
                  backgroundColor: getUsageColor(metrics?.cpu_percent ?? 0),
                }}
              />
            </div>
            <span className="resource-meta">Host CPU cores utilization</span>
          </div>

          {/* Memory Gauge */}
          <div className="resource-card">
            <div className="resource-card-header">
              <span className="resource-title">Memory Utilization</span>
              <span className="resource-percentage">
                {metrics?.memory_percent.toFixed(1) ?? '0.0'}%
              </span>
            </div>
            <div className="gauge-track">
              <div
                className="gauge-fill"
                style={{
                  width: `${Math.min(metrics?.memory_percent ?? 0, 100)}%`,
                  backgroundColor: getUsageColor(metrics?.memory_percent ?? 0),
                }}
              />
            </div>
            <span className="resource-meta">
              {metrics?.memory_used_mb.toLocaleString() ?? 0} MB used of{' '}
              {metrics?.memory_total_mb.toLocaleString() ?? 0} MB total
            </span>
          </div>

          {/* Disk Gauge */}
          <div className="resource-card">
            <div className="resource-card-header">
              <span className="resource-title">Disk Storage</span>
              <span className="resource-percentage">
                {metrics?.disk_percent.toFixed(1) ?? '0.0'}%
              </span>
            </div>
            <div className="gauge-track">
              <div
                className="gauge-fill"
                style={{
                  width: `${Math.min(metrics?.disk_percent ?? 0, 100)}%`,
                  backgroundColor: getUsageColor(metrics?.disk_percent ?? 0),
                }}
              />
            </div>
            <span className="resource-meta">
              {metrics?.disk_used_gb.toFixed(2) ?? '0.00'} GB used of{' '}
              {metrics?.disk_total_gb.toFixed(2) ?? '0.00'} GB total
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

