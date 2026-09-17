import React, { useState, useEffect, useRef } from 'react'
import { Suggestions } from './Suggestions'
import { useSuggestions } from '../hooks/useSuggestions'
import '../styles/SearchBar.css'

interface SearchBarProps {
  initialQuery?: string
  onSearch: (query: string) => void
  loading: boolean
}

export const SearchBar: React.FC<SearchBarProps> = ({
  initialQuery = '',
  onSearch,
  loading,
}) => {
  const [query, setQuery] = useState(initialQuery)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    suggestions,
    isOpen,
    selectedIndex,
    getSuggestions,
    clearSuggestions,
    closeSuggestions,
    openSuggestions,
    navigateUp,
    navigateDown,
  } = useSuggestions()

  // Sync state if initialQuery changes (e.g., URL query change or back button)
  useEffect(() => {
    setQuery(initialQuery)
  }, [initialQuery])

  // Outside click handler to close suggestions
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        closeSuggestions()
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [closeSuggestions])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setQuery(val)
    getSuggestions(val)
  }

  const handleClear = () => {
    setQuery('')
    clearSuggestions()
    inputRef.current?.focus()
  }

  const submitQuery = (targetQuery: string) => {
    closeSuggestions()
    const trimmed = targetQuery.trim()
    if (trimmed) {
      onSearch(trimmed)
    }
  }

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedIndex >= 0 && suggestions[selectedIndex]) {
      const selected = suggestions[selectedIndex]
      setQuery(selected)
      submitQuery(selected)
    } else {
      submitQuery(query)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (isOpen && suggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        navigateDown()
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        navigateUp()
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        closeSuggestions()
        return
      }
      if (e.key === 'Enter' && selectedIndex >= 0 && suggestions[selectedIndex]) {
        e.preventDefault()
        const selected = suggestions[selectedIndex]
        setQuery(selected)
        submitQuery(selected)
        return
      }
    }
  }

  const handleSuggestionSelect = (suggestion: string) => {
    setQuery(suggestion)
    submitQuery(suggestion)
  }

  return (
    <div className="search-bar-container" ref={containerRef}>
      <form onSubmit={handleFormSubmit} className="search-form" role="search">
        <div className="search-input-wrapper">
          <span className="search-icon" aria-hidden="true">
            🔍
          </span>
          <input
            ref={inputRef}
            type="text"
            className="search-input"
            placeholder="Search the index (e.g. python +fast -legacy)"
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (query.trim().length >= 2 && suggestions.length > 0) {
                openSuggestions()
              }
            }}
            disabled={loading}
            autoComplete="off"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={isOpen && suggestions.length > 0}
            aria-controls="suggestions-listbox"
            aria-activedescendant={
              selectedIndex >= 0 ? `suggestion-item-${selectedIndex}` : undefined
            }
            aria-label="Search query"
          />
          <div className="search-actions">
            {query && !loading && (
              <button
                type="button"
                className="clear-button"
                onClick={handleClear}
                aria-label="Clear search input"
              >
                ✕
              </button>
            )}
            <button
              type="submit"
              className="search-submit-btn"
              disabled={loading || !query.trim()}
              aria-label="Submit search"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </div>

        {isOpen && (
          <Suggestions
            id="suggestions-listbox"
            suggestions={suggestions}
            selectedIndex={selectedIndex}
            onSelect={handleSuggestionSelect}
          />
        )}
      </form>
    </div>
  )
}

