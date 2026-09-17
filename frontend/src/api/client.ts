import axios, { AxiosError, AxiosInstance } from 'axios'
import type {
  HealthResponse,
  SearchRequest,
  SearchResponse,
  StatsResponse,
  SuggestResponse,
} from '../types'

export class SearchAPIError extends Error {
  status?: number
  retryAfter?: number
  requestId?: string

  constructor(message: string, status?: number, retryAfter?: number, requestId?: string) {
    super(message)
    this.name = 'SearchAPIError'
    this.status = status
    this.retryAfter = retryAfter
    this.requestId = requestId
  }
}

export class SearchAPIClient {
  private client: AxiosInstance

  constructor(baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1') {
    this.client = axios.create({
      baseURL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }

  private handleAxiosError(error: unknown, fallbackMessage: string): never {
    if (axios.isCancel(error)) {
      throw new SearchAPIError('Request was cancelled', 0)
    }

    if (error instanceof AxiosError) {
      const status = error.response?.status
      const data = error.response?.data
      const requestId = error.response?.headers?.['x-request-id'] || data?.request_id

      let message = fallbackMessage

      if (status === 422) {
        if (typeof data?.error === 'string') {
          message = data.error
        } else if (Array.isArray(data?.details) && data.details[0]?.msg) {
          message = data.details[0].msg
        } else {
          message = 'Invalid search query. Queries must be between 1 and 500 characters.'
        }
      } else if (status === 429) {
        const retryAfterHeader = error.response?.headers?.['retry-after']
        const retryAfterSec = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined
        message = retryAfterSec
          ? `Rate limit exceeded. Please wait ${retryAfterSec} seconds before searching again.`
          : 'Rate limit exceeded. Please wait a moment before searching again.'
        throw new SearchAPIError(message, status, retryAfterSec, requestId)
      } else if (status === 503) {
        message = data?.error || 'Search index service is currently initializing or unavailable.'
      } else if (status === 500) {
        message = 'An unexpected server error occurred. Please try again later.'
      } else if (!error.response) {
        message = 'Unable to connect to search service. Please check your network connection.'
      } else if (typeof data?.error === 'string') {
        message = data.error
      }

      throw new SearchAPIError(message, status, undefined, requestId)
    }

    throw new SearchAPIError(
      error instanceof Error ? error.message : fallbackMessage
    )
  }

  async search(request: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
    try {
      const response = await this.client.post<SearchResponse>('/search', request, { signal })
      return response.data
    } catch (error) {
      this.handleAxiosError(error, 'Search failed. Please try again.')
    }
  }

  async getSuggestions(prefix: string, limit = 5, signal?: AbortSignal): Promise<SuggestResponse> {
    try {
      const response = await this.client.get<SuggestResponse>('/suggest', {
        params: { prefix, limit },
        signal,
      })
      return response.data
    } catch (error) {
      this.handleAxiosError(error, 'Suggestions failed.')
    }
  }

  async getStats(signal?: AbortSignal): Promise<StatsResponse> {
    try {
      const response = await this.client.get<StatsResponse>('/stats', { signal })
      return response.data
    } catch (error) {
      this.handleAxiosError(error, 'Failed to fetch index statistics.')
    }
  }

  async getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    try {
      const response = await this.client.get<HealthResponse>('/health', { signal })
      return response.data
    } catch (error) {
      this.handleAxiosError(error, 'Health check failed.')
    }
  }
}

export const apiClient = new SearchAPIClient()

