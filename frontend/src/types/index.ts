export interface SearchResult {
  doc_id: number
  url: string
  title: string
  description: string
  snippet: string
  score: number
  relevance: number
  metadata?: Record<string, unknown>
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  count: number
  total_available: number
  limit: number
  offset: number
  execution_time_ms: number
}

export interface SearchRequest {
  query: string
  limit?: number
  offset?: number
}

export interface SuggestResponse {
  prefix: string
  suggestions: string[]
}

export interface StatsResponse {
  total_documents: number
  total_terms: number
  total_postings: number
  avg_postings_per_term: number
  index_size_mb: number
}

export interface HealthResponse {
  status: string
  version: string
  timestamp: string
  index_ready: boolean
}

export interface ErrorResponse {
  error: string
  code: number
  timestamp: string
  request_id?: string
  details?: unknown
}

export type Theme = 'dark' | 'light'

export * from './admin'

