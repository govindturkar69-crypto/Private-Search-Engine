import { useState, useCallback, useMemo } from 'react'

interface UsePaginationReturn {
  currentPage: number
  totalPages: number
  offset: number
  setPage: (page: number, shouldScroll?: boolean) => void
  reset: () => void
  setTotal: (total: number) => void
}

export function usePagination(itemsPerPage = 10, initialPage = 1): UsePaginationReturn {
  const [currentPage, setCurrentPage] = useState(initialPage)
  const [totalItems, setTotalItems] = useState(0)

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(totalItems / itemsPerPage))
  }, [totalItems, itemsPerPage])

  const setPage = useCallback(
    (page: number, shouldScroll = true) => {
      const validPage = Math.max(1, Math.min(page, totalPages))
      setCurrentPage(validPage)
      if (shouldScroll && typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    },
    [totalPages]
  )

  const reset = useCallback(() => {
    setCurrentPage(1)
  }, [])

  const setTotal = useCallback((total: number) => {
    setTotalItems(total)
  }, [])

  const offset = (currentPage - 1) * itemsPerPage

  return {
    currentPage,
    totalPages,
    offset,
    setPage,
    reset,
    setTotal,
  }
}

