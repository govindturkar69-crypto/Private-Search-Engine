import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResultsList } from '../ResultsList'
import type { SearchResult } from '../../types'

describe('ResultsList Component', () => {
  const mockResults: SearchResult[] = [
    {
      doc_id: 1,
      url: 'https://example.com/one',
      title: 'Result One',
      description: 'First document description',
      snippet: 'Excerpt for document **one**',
      score: 3.5,
      relevance: 100,
    },
    {
      doc_id: 2,
      url: 'https://example.com/two',
      title: 'Result Two',
      description: 'Second document description',
      snippet: 'Excerpt for document **two**',
      score: 2.1,
      relevance: 60,
    },
  ]

  it('renders loading state with spinner and query indicator', () => {
    render(
      <ResultsList
        results={[]}
        loading={true}
        error={null}
        totalAvailable={0}
        executionTime={0}
        query="fastapi"
      />
    )

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText(/Searching index for “fastapi”/)).toBeInTheDocument()
  })

  it('renders error state with alert role and message', () => {
    render(
      <ResultsList
        results={[]}
        loading={false}
        error="Unable to connect to search service."
        totalAvailable={0}
        executionTime={0}
        query="python"
      />
    )

    const alert = screen.getByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(screen.getByText('Unable to connect to search service.')).toBeInTheDocument()
  })

  it('renders retry-after badge if rate limited', () => {
    render(
      <ResultsList
        results={[]}
        loading={false}
        error="Rate limit exceeded."
        retryAfter={45}
        totalAvailable={0}
        executionTime={0}
        query="python"
      />
    )

    expect(screen.getByText('Retry available in 45s')).toBeInTheDocument()
  })

  it('renders empty results message when no documents match', () => {
    render(
      <ResultsList
        results={[]}
        loading={false}
        error={null}
        totalAvailable={0}
        executionTime={10}
        query="nonexistentqueryxyz"
      />
    )

    expect(screen.getByRole('region', { name: 'No results' })).toBeInTheDocument()
    expect(screen.getByText(/No results found for “nonexistentqueryxyz”/)).toBeInTheDocument()
  })

  it('renders populated results list with summary stats', () => {
    render(
      <ResultsList
        results={mockResults}
        loading={false}
        error={null}
        totalAvailable={2}
        executionTime={12.45}
        query="test"
      />
    )

    expect(screen.getByText(/Found/)).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('12.45ms')).toBeInTheDocument()
    expect(screen.getByText('Result One')).toBeInTheDocument()
    expect(screen.getByText('Result Two')).toBeInTheDocument()
  })
})

