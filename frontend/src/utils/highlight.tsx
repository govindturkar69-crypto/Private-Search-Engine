import React from 'react'

/**
 * Escapes regex special characters in a string.
 */
function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Safely renders a snippet with query terms or markdown bold markers highlighted
 * as React elements without using dangerouslySetInnerHTML.
 */
export function renderSafeSnippet(snippet: string, query = ''): React.ReactNode {
  if (!snippet) return null

  // 1. Check if backend provided markdown-style bold tags: **term**
  if (snippet.includes('**')) {
    const parts = snippet.split(/\*\*(.*?)\*\*/)
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return (
          <mark key={index} className="highlight-term">
            {part}
          </mark>
        )
      }
      return <React.Fragment key={index}>{part}</React.Fragment>
    })
  }

  // 2. Fallback: Highlight matching query terms if snippet has no markdown bold markers
  if (!query.trim()) {
    return snippet
  }

  // Extract query keywords (strip operators like +, -, quotes, field:)
  const terms = query
    .replace(/[+":-]/g, ' ')
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 1)

  if (terms.length === 0) {
    return snippet
  }

  // Sort descending by length to avoid partial replacements
  terms.sort((a, b) => b.length - a.length)
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi')
  const parts = snippet.split(pattern)

  return parts.map((part, index) => {
    if (terms.some((t) => t.toLowerCase() === part.toLowerCase())) {
      return (
        <mark key={index} className="highlight-term">
          {part}
        </mark>
      )
    }
    return <React.Fragment key={index}>{part}</React.Fragment>
  })
}

