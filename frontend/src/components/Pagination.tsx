import React from 'react'
import '../styles/Pagination.css'

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  disabled: boolean
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  disabled,
}) => {
  if (totalPages <= 1) return null

  const pages: React.ReactNode[] = []
  const start = Math.max(1, currentPage - 2)
  const end = Math.min(totalPages, currentPage + 2)

  if (start > 1) {
    pages.push(
      <button
        key="page-1"
        type="button"
        className={`pagination-btn ${currentPage === 1 ? 'active' : ''}`}
        onClick={() => onPageChange(1)}
        disabled={disabled}
        aria-label="Go to page 1"
        aria-current={currentPage === 1 ? 'page' : undefined}
      >
        1
      </button>
    )
    if (start > 2) {
      pages.push(
        <span key="dots-start" className="pagination-ellipsis" aria-hidden="true">
          …
        </span>
      )
    }
  }

  for (let i = start; i <= end; i++) {
    pages.push(
      <button
        key={`page-${i}`}
        type="button"
        className={`pagination-btn ${i === currentPage ? 'active' : ''}`}
        onClick={() => onPageChange(i)}
        disabled={disabled}
        aria-label={`Go to page ${i}`}
        aria-current={i === currentPage ? 'page' : undefined}
      >
        {i}
      </button>
    )
  }

  if (end < totalPages) {
    if (end < totalPages - 1) {
      pages.push(
        <span key="dots-end" className="pagination-ellipsis" aria-hidden="true">
          …
        </span>
      )
    }
    pages.push(
      <button
        key={`page-${totalPages}`}
        type="button"
        className={`pagination-btn ${currentPage === totalPages ? 'active' : ''}`}
        onClick={() => onPageChange(totalPages)}
        disabled={disabled}
        aria-label={`Go to page ${totalPages}`}
        aria-current={currentPage === totalPages ? 'page' : undefined}
      >
        {totalPages}
      </button>
    )
  }

  return (
    <nav className="pagination" role="navigation" aria-label="Pagination">
      <button
        type="button"
        className="pagination-btn"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={disabled || currentPage === 1}
        aria-label="Previous page"
      >
        ← Prev
      </button>
      {pages}
      <button
        type="button"
        className="pagination-btn"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={disabled || currentPage === totalPages}
        aria-label="Next page"
      >
        Next →
      </button>
    </nav>
  )
}

