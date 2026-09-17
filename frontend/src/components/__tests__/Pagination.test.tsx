import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Pagination } from '../Pagination'

describe('Pagination Component', () => {
  it('renders nothing when totalPages is 1 or less', () => {
    const { container } = render(
      <Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} disabled={false} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders pagination buttons and marks active page with aria-current="page"', () => {
    render(
      <Pagination currentPage={2} totalPages={5} onPageChange={vi.fn()} disabled={false} />
    )

    const page2Btn = screen.getByRole('button', { name: 'Go to page 2' })
    expect(page2Btn).toHaveAttribute('aria-current', 'page')
    expect(page2Btn).toHaveClass('active')

    const page1Btn = screen.getByRole('button', { name: 'Go to page 1' })
    expect(page1Btn).not.toHaveAttribute('aria-current')
  })

  it('navigates previous and next pages', () => {
    const onPageChange = vi.fn()
    render(
      <Pagination currentPage={2} totalPages={3} onPageChange={onPageChange} disabled={false} />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(onPageChange).toHaveBeenCalledWith(1)

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('disables previous button on page 1', () => {
    render(
      <Pagination currentPage={1} totalPages={4} onPageChange={vi.fn()} disabled={false} />
    )
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).not.toBeDisabled()
  })

  it('disables next button on last page', () => {
    render(
      <Pagination currentPage={4} totalPages={4} onPageChange={vi.fn()} disabled={false} />
    )
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
  })

  it('disables all buttons when disabled prop is true', () => {
    render(
      <Pagination currentPage={2} totalPages={4} onPageChange={vi.fn()} disabled={true} />
    )
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Go to page 2' })).toBeDisabled()
  })
})

