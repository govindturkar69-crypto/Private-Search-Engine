import React from 'react'
import type { SearchResult as SearchResultType } from '../types'
import { renderSafeSnippet } from '../utils/highlight'
import '../styles/SearchResult.css'

interface SearchResultProps {
  result: SearchResultType
  query?: string
}

export const SearchResult: React.FC<SearchResultProps> = ({ result, query }) => {
  let hostname = result.url
  try {
    hostname = new URL(result.url).hostname
  } catch {
    // Keep raw URL if not valid absolute URL
  }

  return (
    <article className="search-result">
      <div className="result-header">
        <div className="result-url-wrapper">
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="result-url"
            aria-label={`Visit ${result.url}`}
          >
            {hostname}
          </a>
        </div>
        <span
          className="result-relevance"
          aria-label={`Relevance: ${result.relevance} percent`}
        >
          {result.relevance}% match
        </span>
      </div>

      <h2 className="result-title">
        <a href={result.url} target="_blank" rel="noopener noreferrer">
          {result.title || result.url}
        </a>
      </h2>

      {result.description && (
        <p className="result-description">{result.description}</p>
      )}

      {result.snippet && (
        <div className="result-snippet" aria-label="Result excerpt">
          {renderSafeSnippet(result.snippet, query)}
        </div>
      )}

      <div className="result-meta">
        <span className="result-score">BM25 Score: {result.score.toFixed(3)}</span>
      </div>
    </article>
  )
}

