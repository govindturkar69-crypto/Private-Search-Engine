import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'
import { AdminAPIClient } from '../api/adminClient'

vi.mock('axios', () => {
  const mockInstance = {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: {
      request: {
        use: vi.fn(),
      },
    },
  }
  return {
    default: {
      create: vi.fn(() => mockInstance),
      isCancel: vi.fn(),
    },
    AxiosError: class extends Error {
      response?: {
        status: number
        data?: unknown
        headers?: Record<string, string>
      }
      constructor(
        message?: string,
        _code?: string,
        _config?: unknown,
        _request?: unknown,
        response?: { status: number; data?: unknown; headers?: Record<string, string> }
      ) {
        super(message)
        this.name = 'AxiosError'
        this.response = response
      }
    },
  }
})

describe('AdminAPIClient', () => {
  let client: AdminAPIClient
  let mockAxiosInstance: any

  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    mockAxiosInstance = {
      get: vi.fn(),
      post: vi.fn(),
      interceptors: {
        request: {
          use: vi.fn(),
        },
      },
    }
    vi.mocked(axios.create).mockReturnValue(mockAxiosInstance)
    client = new AdminAPIClient('/api/v1')
  })

  it('manages token in sessionStorage correctly', () => {
    expect(client.getAuthToken()).toBeNull()

    client.setAuthToken('my-secret-token')
    expect(client.getAuthToken()).toBe('my-secret-token')

    client.clearAuthToken()
    expect(client.getAuthToken()).toBeNull()
  })

  it('checks health successfully', async () => {
    mockAxiosInstance.get.mockResolvedValueOnce({
      data: {
        status: 'ok',
        admin_ready: true,
        crawler_ready: true,
        index_ready: true,
        timestamp: '2026-09-15T12:00:00Z',
      },
    })

    const res = await client.checkHealth()
    expect(res.status).toBe('ok')
    expect(res.admin_ready).toBe(true)
    expect(mockAxiosInstance.get).toHaveBeenCalledWith('/health', { signal: undefined })
  })

  it('starts crawler with valid payload', async () => {
    mockAxiosInstance.post.mockResolvedValueOnce({
      data: {
        crawl_id: 'crawl-123',
        status: 'running',
        documents_crawled: 0,
        documents_indexed: 0,
        errors: 0,
        urls_queued: 1,
        progress_percent: 0,
      },
    })

    const payload = { seed_urls: ['https://example.com'], max_documents: 100 }
    const res = await client.startCrawler(payload)
    expect(res.status).toBe('running')
    expect(mockAxiosInstance.post).toHaveBeenCalledWith('/crawler/start', payload, { signal: undefined })
  })

  it('fetches index and system metrics', async () => {
    mockAxiosInstance.get
      .mockResolvedValueOnce({
        data: {
          total_documents: 10,
          total_terms: 100,
          total_postings: 200,
          avg_postings_per_term: 2.0,
          index_size_mb: 1.5,
          last_updated: '2026-09-15T12:00:00Z',
          health_status: 'healthy',
        },
      })
      .mockResolvedValueOnce({
        data: {
          cpu_percent: 15.0,
          memory_percent: 50.0,
          disk_percent: 60.0,
          memory_used_mb: 4000,
          memory_total_mb: 8000,
          disk_used_gb: 120,
          disk_total_gb: 250,
        },
      })

    const indexRes = await client.getIndexMetrics()
    expect(indexRes.total_documents).toBe(10)

    const sysRes = await client.getSystemMetrics()
    expect(sysRes.cpu_percent).toBe(15.0)
  })

  it('clears index successfully', async () => {
    mockAxiosInstance.post.mockResolvedValueOnce({
      data: { message: 'Inverted index cleared successfully.' },
    })

    const res = await client.clearIndex()
    expect(res.message).toContain('cleared successfully')
  })
})

