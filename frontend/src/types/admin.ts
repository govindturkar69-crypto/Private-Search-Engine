export type CrawlStatus = 'idle' | 'running' | 'paused' | 'stopped' | 'error'
export type CrawlPriority = 'low' | 'normal' | 'high'

export interface CrawlRequest {
  seed_urls: string[]
  max_documents?: number
  max_depth?: number
  priority?: CrawlPriority
}

export interface CrawlResponse {
  crawl_id: string
  status: CrawlStatus
  start_time?: string | null
  documents_crawled: number
  documents_indexed: number
  errors: number
  urls_queued: number
  current_url?: string | null
  progress_percent: number
}

export interface IndexMetrics {
  total_documents: number
  total_terms: number
  total_postings: number
  avg_postings_per_term: number
  index_size_mb: number
  last_updated: string
  health_status: string
}

export interface SystemMetrics {
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  memory_used_mb: number
  memory_total_mb: number
  disk_used_gb: number
  disk_total_gb: number
}

export interface LogEntry {
  timestamp: string
  level: string
  module: string
  message: string
}

export interface ConfigUpdateRequest {
  key: string
  value: unknown
  description?: string
}

export interface RuntimeConfigResponse {
  settings: Record<string, unknown>
  notice: string
}

export interface AdminHealthResponse {
  status: string
  admin_ready: boolean
  crawler_ready: boolean
  index_ready: boolean
  timestamp: string
}

