import React, { useEffect, useState } from 'react'
import { adminClient } from '../../api/adminClient'
import type { RuntimeConfigResponse } from '../../types'

export const ConfigManager: React.FC = () => {
  const [config, setConfig] = useState<RuntimeConfigResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Local state for allowlisted fields
  const [logLevel, setLogLevel] = useState<string>('INFO')
  const [rateLimit, setRateLimit] = useState<number>(100)
  const [maxDepth, setMaxDepth] = useState<number>(2)
  const [politenessDelay, setPolitenessDelay] = useState<number>(1.0)

  const fetchConfig = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminClient.getRuntimeConfig()
      setConfig(data)
      if (data.settings) {
        if (typeof data.settings.log_level === 'string') {
          setLogLevel(data.settings.log_level)
        }
        if (typeof data.settings.rate_limit_per_minute === 'number') {
          setRateLimit(data.settings.rate_limit_per_minute)
        }
        if (typeof data.settings.crawler_max_depth === 'number') {
          setMaxDepth(data.settings.crawler_max_depth)
        }
        if (typeof data.settings.crawler_politeness_delay === 'number') {
          setPolitenessDelay(data.settings.crawler_politeness_delay)
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch runtime configuration.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleUpdate = async (key: string, value: unknown) => {
    setSavingKey(key)
    setError(null)
    setSuccess(null)

    try {
      const updated = await adminClient.updateRuntimeConfig(key, value)
      setConfig(updated)
      setSuccess(`Updated '${key}' successfully (runtime in-memory).`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to update '${key}'.`)
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <div className="admin-section config-manager-panel">
      <div className="section-header">
        <div>
          <h2>Runtime Configuration</h2>
          <p className="section-subtitle">
            Adjust allowlisted engine operational parameters without restarting
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={fetchConfig}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : '↻ Reload'}
        </button>
      </div>

      {/* Runtime In-Memory Persistence Warning Notice */}
      <div className="admin-alert alert-notice" role="status">
        <span className="alert-icon">ℹ️</span>
        <div>
          <strong>Notice:</strong>{' '}
          {config?.notice || 'Runtime-only settings. Changes reset when the server restarts.'}
        </div>
      </div>

      {error && (
        <div className="admin-alert alert-error" role="alert">
          <span className="alert-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="admin-alert alert-success" role="alert">
          <span className="alert-icon">✓</span>
          <span>{success}</span>
        </div>
      )}

      {loading && !config ? (
        <div className="admin-loading">Loading configuration...</div>
      ) : (
        <div className="config-settings-grid">
          {/* Log Level */}
          <div className="config-item-card">
            <div className="config-item-info">
              <h4>Application Log Level</h4>
              <p>Root and module logging threshold for console and app.log.</p>
            </div>
            <div className="config-item-control">
              <select
                className="form-select"
                value={logLevel}
                onChange={(e) => setLogLevel(e.target.value)}
                disabled={savingKey !== null}
              >
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleUpdate('log_level', logLevel)}
                disabled={savingKey !== null}
              >
                {savingKey === 'log_level' ? 'Saving...' : 'Apply'}
              </button>
            </div>
          </div>

          {/* Rate Limit */}
          <div className="config-item-card">
            <div className="config-item-info">
              <h4>API Rate Limit (Req/Min)</h4>
              <p>Maximum requests allowed per client IP per minute (1–10,000).</p>
            </div>
            <div className="config-item-control">
              <input
                type="number"
                className="form-input"
                min={1}
                max={10000}
                value={rateLimit}
                onChange={(e) => setRateLimit(Number(e.target.value))}
                disabled={savingKey !== null}
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleUpdate('rate_limit_per_minute', rateLimit)}
                disabled={savingKey !== null}
              >
                {savingKey === 'rate_limit_per_minute' ? 'Saving...' : 'Apply'}
              </button>
            </div>
          </div>

          {/* Crawler Max Depth */}
          <div className="config-item-card">
            <div className="config-item-info">
              <h4>Crawler Default Max Depth</h4>
              <p>Default link traversal depth for background crawlers (1–5).</p>
            </div>
            <div className="config-item-control">
              <input
                type="number"
                className="form-input"
                min={1}
                max={5}
                value={maxDepth}
                onChange={(e) => setMaxDepth(Number(e.target.value))}
                disabled={savingKey !== null}
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleUpdate('crawler_max_depth', maxDepth)}
                disabled={savingKey !== null}
              >
                {savingKey === 'crawler_max_depth' ? 'Saving...' : 'Apply'}
              </button>
            </div>
          </div>

          {/* Politeness Delay */}
          <div className="config-item-card">
            <div className="config-item-info">
              <h4>Crawler Politeness Delay (Seconds)</h4>
              <p>Per-domain crawl spacing delay (0.1–30.0 seconds).</p>
            </div>
            <div className="config-item-control">
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="30.0"
                className="form-input"
                value={politenessDelay}
                onChange={(e) => setPolitenessDelay(Number(e.target.value))}
                disabled={savingKey !== null}
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() =>
                  handleUpdate('crawler_politeness_delay', politenessDelay)
                }
                disabled={savingKey !== null}
              >
                {savingKey === 'crawler_politeness_delay' ? 'Saving...' : 'Apply'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

