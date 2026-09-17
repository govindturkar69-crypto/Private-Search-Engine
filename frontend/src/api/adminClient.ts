import axios, { AxiosError, AxiosInstance } from 'axios'
import type {
  AdminHealthResponse,
  CrawlRequest,
  CrawlResponse,
  IndexMetrics,
  LogEntry,
  RuntimeConfigResponse,
  SystemMetrics,
} from '../types'

const TOKEN_STORAGE_KEY = 'admin_token'

export class AdminAPIError extends Error {
  status?: number
  requestId?: string

  constructor(message: string, status?: number, requestId?: string) {
    super(message)
    this.name = 'AdminAPIError'
    this.status = status
    this.requestId = requestId
  }
}

export class AdminAPIClient {
  private client: AxiosInstance

  constructor(baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1') {
    this.client = axios.create({
      baseURL: `${baseURL.replace(/\/$/, '')}/admin`,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Attach admin token only to admin client calls
    this.client.interceptors.request.use((config) => {
      const token = this.getAuthToken()
      if (token) {
        config.headers['X-Admin-Token'] = token
      }
      return config
    })
  }

  getAuthToken(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_STORAGE_KEY)
    } catch {
      return null
    }
  }

  setAuthToken(token: string): void {
    try {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, token.trim())
    } catch {
      // Ignored if storage unavailable
    }
  }

  clearAuthToken(): void {
    try {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    } catch {
      // Ignored
    }
  }

  private handleAxiosError(error: unknown, fallbackMessage: string): never {
    if (axios.isCancel(error)) {
      throw new AdminAPIError('Request was cancelled', 0)
    }

    if (error instanceof AxiosError) {
      const status = error.response?.status
      const data = error.response?.data
      const requestId = error.response?.headers?.['x-request-id'] || data?.request_id

      let message = fallbackMessage

      if (status === 401) {
        message = data?.error || 'Admin authentication required. Please log in with your admin token.'
      } else if (status === 403) {
        message = data?.error || 'Invalid admin token. Access denied.'
      } else if (status === 409) {
        message = data?.error || 'Conflict: Crawler is in an invalid state for this operation.'
      } else if (status === 422) {
        if (typeof data?.error === 'string') {
          message = data.error
        } else if (Array.isArray(data?.details) && data.details[0]?.msg) {
          message = data.details[0].msg
        } else {
          message = 'Validation error. Please check your inputs.'
        }
      } else if (status === 500) {
        message = data?.error || 'Server error occurred during admin operation.'
      } else if (!error.response) {
        message = 'Unable to reach backend server. Please verify the service is running.'
      } else if (typeof data?.error === 'string') {
        message = data.error
      }

      throw new AdminAPIError(message, status, requestId)
    }

    throw new AdminAPIError(
      error instanceof Error ? error.message : fallbackMessage
    )
  }

  async checkHealth(signal?: AbortSignal): Promise<AdminHealthResponse> {
    try {
      const res = await this.client.get<AdminHealthResponse>('/health', { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to connect to admin subsystem.')
    }
  }

  async startCrawler(payload: CrawlRequest, signal?: AbortSignal): Promise<CrawlResponse> {
    try {
      const res = await this.client.post<CrawlResponse>('/crawler/start', payload, { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to start crawler job.')
    }
  }

  async pauseCrawler(signal?: AbortSignal): Promise<CrawlResponse> {
    try {
      const res = await this.client.post<CrawlResponse>('/crawler/pause', {}, { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to pause crawler.')
    }
  }

  async resumeCrawler(signal?: AbortSignal): Promise<CrawlResponse> {
    try {
      const res = await this.client.post<CrawlResponse>('/crawler/resume', {}, { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to resume crawler.')
    }
  }

  async stopCrawler(signal?: AbortSignal): Promise<CrawlResponse> {
    try {
      const res = await this.client.post<CrawlResponse>('/crawler/stop', {}, { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to stop crawler.')
    }
  }

  async getCrawlerStatus(signal?: AbortSignal): Promise<CrawlResponse> {
    try {
      const res = await this.client.get<CrawlResponse>('/crawler/status', { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to fetch crawler status.')
    }
  }

  async getIndexMetrics(signal?: AbortSignal): Promise<IndexMetrics> {
    try {
      const res = await this.client.get<IndexMetrics>('/metrics/index', { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to fetch index metrics.')
    }
  }

  async getSystemMetrics(signal?: AbortSignal): Promise<SystemMetrics> {
    try {
      const res = await this.client.get<SystemMetrics>('/metrics/system', { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to fetch system metrics.')
    }
  }

  async clearIndex(signal?: AbortSignal): Promise<{ message: string }> {
    try {
      const res = await this.client.post<{ message: string }>('/index/clear', {}, { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to clear index.')
    }
  }

  async getLogs(lines = 100, level?: string, signal?: AbortSignal): Promise<LogEntry[]> {
    try {
      const params: Record<string, unknown> = { lines }
      if (level && level !== 'ALL') {
        params.level = level
      }
      const res = await this.client.get<LogEntry[]>('/logs', { params, signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to fetch system logs.')
    }
  }

  async getRuntimeConfig(signal?: AbortSignal): Promise<RuntimeConfigResponse> {
    try {
      const res = await this.client.get<RuntimeConfigResponse>('/config', { signal })
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to fetch runtime configuration.')
    }
  }

  async updateRuntimeConfig(key: string, value: unknown, signal?: AbortSignal): Promise<RuntimeConfigResponse> {
    try {
      const res = await this.client.post<RuntimeConfigResponse>(
        '/config',
        { key, value },
        { signal }
      )
      return res.data
    } catch (err) {
      this.handleAxiosError(err, 'Failed to update runtime configuration.')
    }
  }
}

export const adminClient = new AdminAPIClient()

