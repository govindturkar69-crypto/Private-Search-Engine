import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SearchResult } from '../SearchResult'
import type { SearchResult as SearchResultType } from '../../types'

describe('SearchResult Component', () => {
  const mockResult: SearchResultType = {
    doc_id: 42,
    url: 'https://docs.python.org/3/tutorial/index.html',
    title: 'The Python Tutorial',
    description: 'Python is an easy to learn, powerful programming language.',
    snippet: 'This tutorial introduces the reader informally to the **Python** language and **programming** system.',
    score: 4.821,
    relevance: 95,
  }

  it('renders title, domain, description, and relevance badge', () => {
    render(<SearchResult result={mockResult} query="python" />)

    expect(screen.getByText('docs.python.org')).toBeInTheDocument()
    expect(screen.getByText('The Python Tutorial')).toBeInTheDocument()
    expect(screen.getByText(/easy to learn/)).toBeInTheDocument()
    expect(screen.getByText('95% match')).toBeInTheDocument()
    expect(screen.getByText(/BM25 Score: 4.821/)).toBeInTheDocument()
  })

  it('safely highlights snippet terms using React mark elements without dangerouslySetInnerHTML', () => {
    const { container } = render(<SearchResult result={mockResult} query="python" />)

    const marks = container.querySelectorAll('mark.highlight-term')
    expect(marks.length).toBe(2)
    expect(marks[0].textContent).toBe('Python')
    expect(marks[1].textContent).toBe('programming')
  })

  it('handles fallback snippet query term highlighting when no markdown bolding exists', () => {
    const resultWithoutBold: SearchResultType = {
      ...mockResult,
      snippet: 'Fast asynchronous crawler for web indexing',
    }

    const { container } = render(
      <SearchResult result={resultWithoutBold} query="crawler indexing" />
    )

    const marks = container.querySelectorAll('mark.highlight-term')
    expect(marks.length).toBe(2)
    expect(marks[0].textContent).toBe('crawler')
    expect(marks[1].textContent).toBe('indexing')
  })

  it('handles malformed URL gracefully', () => {
    const malformedResult: SearchResultType = {
      ...mockResult,
      url: 'not-a-valid-url',
    }

    render(<SearchResult result={malformedResult} />)
    expect(screen.getByText('not-a-valid-url')).toBeInTheDocument()
  })

  it('safely renders malicious XSS payloads as pure text without executing or injecting DOM elements', () => {
    const xssResult: SearchResultType = {
      doc_id: 99,
      url: 'https://attacker.test/exploit',
      title: '<script>alert("xss-title")</script>',
      description: '<img src=x onerror="alert(\'xss-desc\')">',
      snippet: 'Prefix <img src=x onerror=alert(1)> and <svg/onload=alert(2)> suffix',
      score: 1.0,
      relevance: 50,
    }

    const { container } = render(<SearchResult result={xssResult} query="alert" />)

    // Verify raw tags are visible as plain text in the document
    expect(screen.getByText('<script>alert("xss-title")</script>')).toBeInTheDocument()
    expect(screen.getByText('<img src=x onerror="alert(\'xss-desc\')">')).toBeInTheDocument()

    // Verify that NO executable <img>, <script>, or <svg> elements exist in the DOM
    expect(container.querySelectorAll('script').length).toBe(0)
    expect(container.querySelectorAll('img[onerror]').length).toBe(0)
    expect(container.querySelectorAll('svg[onload]').length).toBe(0)
  })
})

