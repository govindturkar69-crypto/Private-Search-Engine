import { useState, useCallback, useRef, useEffect } from 'react'
import { apiClient, SearchAPIError } from '../api/client'
import type { SearchResponse, SearchResult } from '../types'

interface UseSearchReturn {
  results: SearchResult[]
  loading: boolean
  error: string | null
  retryAfter?: number
  totalAvailable: number
  executionTime: number
  search: (query: string, limit: number, offset: number) => Promise<void>
  clearSearch: () => void
}

export function useSearch(): UseSearchReturn {
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryAfter, setRetryAfter] = useState<number | undefined>(undefined)
  const [totalAvailable, setTotalAvailable] = useState(0)
  const [executionTime, setExecutionTime] = useState(0)

  const abortControllerRef = useRef<AbortController | null>(null)

  const clearSearch = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setResults([])
    setError(null)
    setRetryAfter(undefined)
    setTotalAvailable(0)
    setExecutionTime(0)
    setLoading(false)
  }, [])

  const search = useCallback(
    async (query: string, limit: number, offset: number) => {
      const trimmed = query.trim()
      if (!trimmed) {
        clearSearch()
        return
      }

      // Cancel any existing in-flight search
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      const controller = new AbortController()
      abortControllerRef.current = controller

      setLoading(true)
      setError(null)
      setRetryAfter(undefined)

      try {
        const response: SearchResponse = await apiClient.search(
          { query: trimmed, limit, offset },
          controller.signal
        )

        setResults(response.results)
        setTotalAvailable(response.total_available)
        setExecutionTime(response.execution_time_ms)
      } catch (err: unknown) {
        // If aborted, do nothing (don't overwrite state)
        if (err instanceof Error && err.name === 'CanceledError') {
          return
        }
        if (err instanceof SearchAPIError && err.status === 0) {
          return
        }

        if (err instanceof SearchAPIError) {
          setError(err.message)
          setRetryAfter(err.retryAfter)
        } else {
          setError(err instanceof Error ? err.message : 'Search request failed')
        }
        setResults([])
        setTotalAvailable(0)
      } finally {
        // Only turn off loading if this was the current controller
        if (abortControllerRef.current === controller) {
          setLoading(false)
        }
      }
    },
    [clearSearch]
  )

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [])

  return {
    results,
    loading,
    error,
    retryAfter,
    totalAvailable,
    executionTime,
    search,
    clearSearch,
  }
}

