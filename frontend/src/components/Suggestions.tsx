import React from 'react'
import '../styles/Suggestions.css'

interface SuggestionsProps {
  suggestions: string[]
  selectedIndex: number
  onSelect: (suggestion: string) => void
  id?: string
}

export const Suggestions: React.FC<SuggestionsProps> = ({
  suggestions,
  selectedIndex,
  onSelect,
  id = 'suggestions-listbox',
}) => {
  if (suggestions.length === 0) return null

  return (
    <div className="suggestions-dropdown">
      <ul
        id={id}
        className="suggestions-list"
        role="listbox"
        aria-label="Search suggestions"
      >
        {suggestions.map((suggestion, index) => {
          const isSelected = selectedIndex === index
          return (
            <li
              key={index}
              id={`suggestion-item-${index}`}
              role="option"
              aria-selected={isSelected}
            >
              <button
                type="button"
                className={`suggestion-item ${isSelected ? 'active' : ''}`}
                onMouseDown={(e) => {
                  // Prevent input blur before click finishes
                  e.preventDefault()
                  onSelect(suggestion)
                }}
              >
                <span className="suggestion-icon" aria-hidden="true">
                  🔍
                </span>
                <span>{suggestion}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

