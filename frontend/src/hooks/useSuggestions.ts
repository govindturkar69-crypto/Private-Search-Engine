import { useState, useCallback, useRef, useEffect } from 'react'
import { apiClient } from '../api/client'

interface UseSuggestionsReturn {
  suggestions: string[]
  loading: boolean
  isOpen: boolean
  selectedIndex: number
  getSuggestions: (prefix: string) => void
  clearSuggestions: () => void
  closeSuggestions: () => void
  openSuggestions: () => void
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>
  navigateUp: () => void
  navigateDown: () => void
}

export function useSuggestions(): UseSuggestionsReturn {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState<number>(-1)

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const clearSuggestions = useCallback(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current)
      debounceTimer.current = null
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setSuggestions([])
    setIsOpen(false)
    setSelectedIndex(-1)
    setLoading(false)
  }, [])

  const closeSuggestions = useCallback(() => {
    setIsOpen(false)
    setSelectedIndex(-1)
  }, [])

  const openSuggestions = useCallback(() => {
    if (suggestions.length > 0) {
      setIsOpen(true)
    }
  }, [suggestions.length])

  const navigateDown = useCallback(() => {
    setSuggestions((curr) => {
      if (curr.length === 0) return curr
      setSelectedIndex((prev) => (prev + 1 < curr.length ? prev + 1 : 0))
      return curr
    })
  }, [])

  const navigateUp = useCallback(() => {
    setSuggestions((curr) => {
      if (curr.length === 0) return curr
      setSelectedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : curr.length - 1))
      return curr
    })
  }, [])

  const getSuggestions = useCallback((prefix: string) => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current)
    }

    const trimmed = prefix.trim()
    // Minimum 2 characters required
    if (trimmed.length < 2) {
      clearSuggestions()
      return
    }

    debounceTimer.current = setTimeout(async () => {
      // Abort any existing in-flight suggestions request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      const controller = new AbortController()
      abortControllerRef.current = controller

      setLoading(true)
      try {
        const response = await apiClient.getSuggestions(trimmed, 5, controller.signal)
        setSuggestions(response.suggestions)
        setIsOpen(response.suggestions.length > 0)
        setSelectedIndex(-1)
      } catch (err: unknown) {
        // Only ignore cancellation
        if (err instanceof Error && err.name === 'CanceledError') {
          return
        }
        if (typeof err === 'object' && err !== null && 'status' in err && (err as { status: number }).status === 0) {
          return
        }
        setSuggestions([])
        setIsOpen(false)
      } finally {
        setLoading(false)
      }
    }, 300)
  }, [clearSuggestions])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [])

  return {
    suggestions,
    loading,
    isOpen,
    selectedIndex,
    getSuggestions,
    clearSuggestions,
    closeSuggestions,
    openSuggestions,
    setSelectedIndex,
    navigateUp,
    navigateDown,
  }
}

