import React, { useEffect, useState } from 'react'
import { adminClient } from '../../api/adminClient'
import type { IndexMetrics } from '../../types'

export const StatisticsPanel: React.FC = () => {
  const [metrics, setMetrics] = useState<IndexMetrics | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Clear confirmation modal state
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false)
  const [confirmInput, setConfirmInput] = useState<string>('')
  const [clearing, setClearing] = useState<boolean>(false)

  const fetchMetrics = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminClient.getIndexMetrics()
      setMetrics(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch index statistics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMetrics()
  }, [])

  const handleClearConfirm = async () => {
    if (confirmInput.trim().toUpperCase() !== 'CLEAR') {
      setError('You must type CLEAR to confirm inverted index deletion.')
      return
    }

    setClearing(true)
    setError(null)
    setSuccessMsg(null)

    try {
      const res = await adminClient.clearIndex()
      setSuccessMsg(res.message || 'Inverted index cleared successfully.')
      setShowConfirmModal(false)
      setConfirmInput('')
      await fetchMetrics()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to clear index.')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="admin-section statistics-panel">
      <div className="section-header">
        <div>
          <h2>Index Statistics & Storage</h2>
          <p className="section-subtitle">
            Overview of inverted index document, term, and storage totals
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={fetchMetrics}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : '↻ Refresh'}
        </button>
      </div>

      {error && (
        <div className="admin-alert alert-error" role="alert">
          <span className="alert-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div className="admin-alert alert-success" role="alert">
          <span className="alert-icon">✓</span>
          <span>{successMsg}</span>
        </div>
      )}

      {loading && !metrics ? (
        <div className="admin-loading">Loading index metrics...</div>
      ) : (
        <div className="stats-container">
          <div className="stats-cards-grid">
            <div className="stat-card">
              <span className="stat-label">Total Documents</span>
              <span className="stat-number">
                {metrics?.total_documents.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="stat-card">
              <span className="stat-label">Unique Terms</span>
              <span className="stat-number">
                {metrics?.total_terms.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="stat-card">
              <span className="stat-label">Total Postings</span>
              <span className="stat-number">
                {metrics?.total_postings.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="stat-card">
              <span className="stat-label">Avg Postings / Term</span>
              <span className="stat-number">
                {metrics?.avg_postings_per_term ?? 0}
              </span>
            </div>

            <div className="stat-card">
              <span className="stat-label">Index Storage Size</span>
              <span className="stat-number">
                {metrics?.index_size_mb.toFixed(2) ?? '0.00'} MB
              </span>
            </div>

            <div className="stat-card">
              <span className="stat-label">Index Health</span>
              <span className={`stat-badge badge-${metrics?.health_status || 'empty'}`}>
                {(metrics?.health_status || 'UNKNOWN').toUpperCase()}
              </span>
            </div>
          </div>

          <div className="index-footer-meta">
            <span>Last Updated: {metrics?.last_updated || 'Never'}</span>
          </div>

          {/* Danger Zone */}
          <div className="danger-zone-card">
            <div className="danger-zone-header">
              <h3>Maintenance & Danger Zone</h3>
              <p>Irreversible operations affecting all indexed documents.</p>
            </div>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                setShowConfirmModal(true)
                setConfirmInput('')
                setError(null)
              }}
            >
              Clear Entire Inverted Index
            </button>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="admin-modal-overlay" role="dialog" aria-modal="true">
          <div className="admin-modal">
            <h3>⚠️ Confirm Index Deletion</h3>
            <p>
              This operation will delete all indexed documents, term postings, and BM25
              weights from SQLite. This action <strong>cannot</strong> be undone.
            </p>
            <p>
              To confirm, type <strong>CLEAR</strong> below:
            </p>
            <input
              type="text"
              className="form-input modal-input"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              placeholder="Type CLEAR to confirm"
              autoFocus
            />
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowConfirmModal(false)}
                disabled={clearing}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleClearConfirm}
                disabled={clearing || confirmInput.trim().toUpperCase() !== 'CLEAR'}
              >
                {clearing ? 'Clearing...' : 'Permanently Clear Index'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

