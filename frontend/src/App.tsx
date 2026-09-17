import React, { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import { Header } from './components/Header'
import { SearchBar } from './components/SearchBar'
import { ResultsList } from './components/ResultsList'
import { Pagination } from './components/Pagination'
import { AdminDashboard } from './pages/AdminDashboard'
import { useSearch } from './hooks/useSearch'
import { useTheme } from './hooks/useTheme'
import { apiClient } from './api/client'
import type { HealthResponse, StatsResponse } from './types'
import './styles/App.css'

const PAGE_SIZE = 10

export const SearchContent: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { theme, toggleTheme } = useTheme()

  const [totalDocs, setTotalDocs] = useState(0)
  const [indexReady, setIndexReady] = useState(false)

  const urlQuery = searchParams.get('q') || ''
  const urlPageRaw = parseInt(searchParams.get('page') || '1', 10)
  const currentPage = isNaN(urlPageRaw) || urlPageRaw < 1 ? 1 : urlPageRaw

  const {
    results,
    loading,
    error,
    retryAfter,
    totalAvailable,
    executionTime,
    search,
    clearSearch,
  } = useSearch()

  // 1. Initial Health and Statistics load
  useEffect(() => {
    let isMounted = true
    const abortController = new AbortController()

    apiClient
      .getHealth(abortController.signal)
      .then((health: HealthResponse) => {
        if (isMounted) setIndexReady(health.index_ready)
      })
      .catch(() => {
        if (isMounted) setIndexReady(false)
      })

    apiClient
      .getStats(abortController.signal)
      .then((stats: StatsResponse) => {
        if (isMounted) setTotalDocs(stats.total_documents)
      })
      .catch(() => {
        // Keep default 0
      })

    return () => {
      isMounted = false
      abortController.abort()
    }
  }, [])

  // 2. Synchronize search execution with URL parameters
  useEffect(() => {
    if (urlQuery.trim()) {
      const offset = (currentPage - 1) * PAGE_SIZE
      search(urlQuery, PAGE_SIZE, offset)
    } else {
      clearSearch()
    }
  }, [urlQuery, currentPage, search, clearSearch])

  // 3. User submits a new query from SearchBar
  const handleSearchSubmit = useCallback(
    (newQuery: string) => {
      const trimmed = newQuery.trim()
      if (trimmed) {
        // Submitting new query always resets to page 1
        setSearchParams({ q: trimmed, page: '1' })
      } else {
        setSearchParams({})
      }
    },
    [setSearchParams]
  )

  // 4. User navigates pagination
  const handlePageChange = useCallback(
    (newPage: number) => {
      if (!urlQuery.trim()) return
      setSearchParams({ q: urlQuery, page: String(newPage) })
      if (typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    },
    [urlQuery, setSearchParams]
  )

  const totalPages = Math.max(1, Math.ceil(totalAvailable / PAGE_SIZE))

  return (
    <div className="app">
      <Header
        totalDocs={totalDocs}
        indexReady={indexReady}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      <main className="main-content">
        <SearchBar
          initialQuery={urlQuery}
          onSearch={handleSearchSubmit}
          loading={loading}
        />

        <ResultsList
          results={results}
          loading={loading}
          error={error}
          retryAfter={retryAfter}
          totalAvailable={totalAvailable}
          executionTime={executionTime}
          query={urlQuery}
        />

        {!loading && results.length > 0 && totalPages > 1 && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={handlePageChange}
            disabled={loading}
          />
        )}
      </main>
      <footer className="footer" role="contentinfo">
        <p>🔒 Private Search Engine • Self-hosted • Privacy-first • Zero tracking</p>
      </footer>
    </div>
  )
}

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="*" element={<SearchContent />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

