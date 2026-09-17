import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios, { AxiosError } from 'axios'
import { SearchAPIClient, SearchAPIError } from '../api/client'
import type { SearchResponse } from '../types'

vi.mock('axios', () => {
  const mockInstance = {
    post: vi.fn(),
    get: vi.fn(),
  }
  return {
    default: {
      create: vi.fn(() => mockInstance),
      isCancel: vi.fn((err) => err?.name === 'CanceledError'),
    },
    AxiosError: class extends Error {
      response?: {
        status: number
        data?: unknown
        headers?: Record<string, string>
      }
      constructor(message?: string, _code?: string, _config?: unknown, _request?: unknown, response?: { status: number; data?: unknown; headers?: Record<string, string> }) {
        super(message)
        this.name = 'AxiosError'
        this.response = response
      }
    },
  }
})

describe('SearchAPIClient', () => {
  let client: SearchAPIClient
  let mockInstance: { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    vi.clearAllMocks()
    mockInstance = {
      post: vi.fn(),
      get: vi.fn(),
    }
    vi.mocked(axios.create).mockReturnValue(mockInstance as any)
    client = new SearchAPIClient('/api/v1')
  })

  it('performs search request successfully', async () => {
    const mockResponse: SearchResponse = {
      query: 'python',
      results: [
        {
          doc_id: 1,
          url: 'https://python.org',
          title: 'Python',
          description: 'Python programming language',
          snippet: 'Python is a high-level **language**',
          score: 3.14,
          relevance: 100,
        },
      ],
      count: 1,
      total_available: 1,
      limit: 10,
      offset: 0,
      execution_time_ms: 15.2,
    }

    mockInstance.post.mockResolvedValueOnce({ data: mockResponse })

    const result = await client.search({ query: 'python', limit: 10, offset: 0 })
    expect(result).toEqual(mockResponse)
    expect(mockInstance.post).toHaveBeenCalledWith(
      '/search',
      { query: 'python', limit: 10, offset: 0 },
      { signal: undefined }
    )
  })

  it('maps 422 validation error message from backend', async () => {
    const error = new AxiosError('Unprocessable Entity', '422', undefined, undefined, {
      status: 422,
      data: { error: 'Query length exceeds maximum of 500 characters' },
    } as any)
    mockInstance.post.mockRejectedValueOnce(error)

    await expect(client.search({ query: 'x'.repeat(501) })).rejects.toThrow(
      'Query length exceeds maximum of 500 characters'
    )
  })

  it('maps 429 rate limit error and extracts Retry-After header', async () => {
    const error = new AxiosError('Too Many Requests', '429', undefined, undefined, {
      status: 429,
      data: { error: 'Rate limit exceeded' },
      headers: { 'retry-after': '30', 'x-request-id': 'req-987' },
    } as any)
    mockInstance.post.mockRejectedValueOnce(error)

    try {
      await client.search({ query: 'python' })
      expect.fail('Should have thrown SearchAPIError')
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(SearchAPIError)
      const apiErr = err as SearchAPIError
      expect(apiErr.status).toBe(429)
      expect(apiErr.retryAfter).toBe(30)
      expect(apiErr.message).toContain('Please wait 30 seconds')
    }
  })

  it('maps 503 service unavailable error', async () => {
    const error = new AxiosError('Service Unavailable', '503', undefined, undefined, {
      status: 503,
      data: { error: 'Search engine is currently unavailable' },
    } as any)
    mockInstance.post.mockRejectedValueOnce(error)

    await expect(client.search({ query: 'python' })).rejects.toThrow(
      'Search engine is currently unavailable'
    )
  })

  it('maps 500 internal server error to sanitized message', async () => {
    const error = new AxiosError('Internal Server Error', '500', undefined, undefined, {
      status: 500,
      data: { error: 'Internal server error' },
    } as any)
    mockInstance.post.mockRejectedValueOnce(error)

    await expect(client.search({ query: 'python' })).rejects.toThrow(
      'An unexpected server error occurred. Please try again later.'
    )
  })

  it('maps network errors when no response is received', async () => {
    const error = new AxiosError('Network Error', 'ERR_NETWORK')
    mockInstance.post.mockRejectedValueOnce(error)

    await expect(client.search({ query: 'python' })).rejects.toThrow(
      'Unable to connect to search service. Please check your network connection.'
    )
  })

  it('fetches suggestions with prefix and limit', async () => {
    const mockSuggestions = { prefix: 'fast', suggestions: ['fastapi', 'fasttext'] }
    mockInstance.get.mockResolvedValueOnce({ data: mockSuggestions })

    const result = await client.getSuggestions('fast', 5)
    expect(result).toEqual(mockSuggestions)
    expect(mockInstance.get).toHaveBeenCalledWith('/suggest', {
      params: { prefix: 'fast', limit: 5 },
      signal: undefined,
    })
  })

  it('fetches health check readiness', async () => {
    const mockHealth = {
      status: 'healthy',
      version: '1.0.0',
      timestamp: '2026-09-15T00:00:00Z',
      index_ready: true,
    }
    mockInstance.get.mockResolvedValueOnce({ data: mockHealth })

    const result = await client.getHealth()
    expect(result).toEqual(mockHealth)
    expect(mockInstance.get).toHaveBeenCalledWith('/health', { signal: undefined })
  })
})
