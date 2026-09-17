import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSearch } from '../hooks/useSearch'
import { useSuggestions } from '../hooks/useSuggestions'
import { apiClient } from '../api/client'

vi.mock('../api/client', () => ({
  apiClient: {
    search: vi.fn(),
    getSuggestions: vi.fn(),
  },
  SearchAPIError: class extends Error {
    status?: number
    constructor(msg: string, status?: number) {
      super(msg)
      this.status = status
    }
  },
}))

describe('Stale Request Cancellation', () => {
  it('cancels stale in-flight search request when a new search starts', async () => {
    let firstSignal: AbortSignal | undefined
    let secondSignal: AbortSignal | undefined

    vi.mocked(apiClient.search).mockImplementation(
      (req, signal) =>
        new Promise((resolve) => {
          if (req.query === 'first') {
            firstSignal = signal
            // Delay resolution
            setTimeout(() => {
              resolve({
                query: 'first',
                results: [],
                count: 0,
                total_available: 0,
                limit: 10,
                offset: 0,
                execution_time_ms: 10,
              })
            }, 100)
          } else {
            secondSignal = signal
            resolve({
              query: 'second',
              results: [
                {
                  doc_id: 2,
                  url: 'https://example.com/2',
                  title: 'Second Result',
                  description: 'Desc',
                  snippet: 'Snippet',
                  score: 1.0,
                  relevance: 100,
                },
              ],
              count: 1,
              total_available: 1,
              limit: 10,
              offset: 0,
              execution_time_ms: 5,
            })
          }
        })
    )

    const { result } = renderHook(() => useSearch())

    // Trigger first search
    act(() => {
      result.current.search('first', 10, 0)
    })
    expect(firstSignal).toBeDefined()
    expect(firstSignal?.aborted).toBe(false)

    // Trigger second search immediately before first resolves
    await act(async () => {
      await result.current.search('second', 10, 0)
    })

    // Verify first request was aborted
    expect(firstSignal?.aborted).toBe(true)
    expect(secondSignal?.aborted).toBe(false)
    expect(result.current.results.length).toBe(1)
    expect(result.current.results[0].title).toBe('Second Result')
  })

  it('cancels stale in-flight suggestions request when a newer prefix is typed', async () => {
    vi.useFakeTimers()
    let firstSignal: AbortSignal | undefined

    vi.mocked(apiClient.getSuggestions).mockImplementation((prefix, _limit, signal) => {
      if (prefix === 'py') {
        firstSignal = signal
      }
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({ prefix, suggestions: [`${prefix}-result`] })
        }, 50)
      })
    })

    const { result } = renderHook(() => useSuggestions())

    // Request 1: "py"
    await act(async () => {
      result.current.getSuggestions('py')
      vi.advanceTimersByTime(300)
    })

    expect(firstSignal).toBeDefined()
    expect(firstSignal?.aborted).toBe(false)

    // Request 2: "python" while Request 1 is in-flight
    await act(async () => {
      result.current.getSuggestions('python')
      vi.advanceTimersByTime(350)
    })

    // Verify older request was aborted
    expect(firstSignal?.aborted).toBe(true)

    vi.useRealTimers()
  })
})

