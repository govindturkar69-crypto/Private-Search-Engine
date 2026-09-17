import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SearchContent } from '../App'
import { apiClient } from '../api/client'
import type { SearchResponse } from '../types'

vi.mock('../api/client', () => ({
  apiClient: {
    getHealth: vi.fn(),
    getStats: vi.fn(),
    search: vi.fn(),
    getSuggestions: vi.fn(),
  },
  SearchAPIError: class extends Error {
    status?: number
    retryAfter?: number
    constructor(msg: string, status?: number, retryAfter?: number) {
      super(msg)
      this.status = status
      this.retryAfter = retryAfter
    }
  },
}))

describe('App & URL Synchronization', () => {
  const mockSearchResponse: SearchResponse = {
    query: 'python',
    results: [
      {
        doc_id: 1,
        url: 'https://www.python.org',
        title: 'Welcome to Python.org',
        description: 'The official home of the Python Programming Language.',
        snippet: 'Official home of **Python**',
        score: 5.0,
        relevance: 100,
      },
    ],
    count: 1,
    total_available: 25,
    limit: 10,
    offset: 0,
    execution_time_ms: 8.5,
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(apiClient.getHealth).mockResolvedValue({
      status: 'healthy',
      version: '1.0.0',
      timestamp: '2026-09-15T00:00:00Z',
      index_ready: true,
    })

    vi.mocked(apiClient.getStats).mockResolvedValue({
      total_documents: 1420,
      total_terms: 5000,
      total_postings: 50000,
      avg_postings_per_term: 10,
      index_size_mb: 4.5,
    })

    vi.mocked(apiClient.search).mockResolvedValue(mockSearchResponse)
  })

  it('loads health and stats on mount and displays in header', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SearchContent />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Ready')).toBeInTheDocument()
      expect(screen.getByText('1,420 docs')).toBeInTheDocument()
    })
  })

  it('reads ?q=python&page=2 from URL on mount and requests with offset=10', async () => {
    render(
      <MemoryRouter initialEntries={['/?q=python&page=2']}>
        <SearchContent />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(apiClient.search).toHaveBeenCalledWith(
        { query: 'python', limit: 10, offset: 10 },
        expect.any(AbortSignal)
      )
    })

    expect(screen.getByText('Welcome to Python.org')).toBeInTheDocument()
  })

  it('submitting a search updates search state and renders results', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SearchContent />
      </MemoryRouter>
    )

    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'python' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => {
      expect(apiClient.search).toHaveBeenCalledWith(
        { query: 'python', limit: 10, offset: 0 },
        expect.any(AbortSignal)
      )
    })

    expect(await screen.findByText('Welcome to Python.org')).toBeInTheDocument()
  })

  it('renders pagination and handles page navigation', async () => {
    render(
      <MemoryRouter initialEntries={['/?q=python&page=1']}>
        <SearchContent />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument()
    })

    // Click page 2 button
    const page2Btn = screen.getByRole('button', { name: 'Go to page 2' })
    fireEvent.click(page2Btn)

    await waitFor(() => {
      expect(apiClient.search).toHaveBeenCalledWith(
        { query: 'python', limit: 10, offset: 10 },
        expect.any(AbortSignal)
      )
    })
  })
})

