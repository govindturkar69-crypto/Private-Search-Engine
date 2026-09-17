import React from 'react'
import { SearchResult } from './SearchResult'
import type { SearchResult as SearchResultType } from '../types'
import '../styles/ResultsList.css'

interface ResultsListProps {
  results: SearchResultType[]
  loading: boolean
  error: string | null
  retryAfter?: number
  totalAvailable: number
  executionTime: number
  query: string
}

export const ResultsList: React.FC<ResultsListProps> = ({
  results,
  loading,
  error,
  retryAfter,
  totalAvailable,
  executionTime,
  query,
}) => {
  if (loading) {
    return (
      <div className="results-loading" role="status" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Searching index for &ldquo;{query}&rdquo;...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="results-error" role="alert">
        <div className="error-title">
          <span aria-hidden="true">⚠️</span>
          <span>Search Error</span>
        </div>
        <p className="error-message">{error}</p>
        {retryAfter !== undefined && (
          <div className="retry-after-badge">
            Retry available in {retryAfter}s
          </div>
        )}
      </div>
    )
  }

  if (results.length === 0 && query.trim()) {
    return (
      <div className="results-empty" role="region" aria-label="No results">
        <h3>No results found for &ldquo;{query}&rdquo;</h3>
        <p>Try different keywords, checking spelling, or removing search filters.</p>
      </div>
    )
  }

  if (results.length === 0) {
    return null
  }

  return (
    <section className="results-container" aria-label="Search results">
      <div className="results-info" aria-live="polite">
        <p>
          Found <strong>{totalAvailable.toLocaleString()}</strong> results in{' '}
          <strong>{executionTime.toFixed(2)}ms</strong>
        </p>
      </div>
      <div className="results-list">
        {results.map((result) => (
          <SearchResult key={result.doc_id} result={result} query={query} />
        ))}
      </div>
    </section>
  )
}

