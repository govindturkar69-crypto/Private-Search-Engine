import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Header } from '../Header'

describe('Header Component', () => {
  it('renders branding, document count, and ready status', () => {
    render(
      <Header
        totalDocs={1250}
        indexReady={true}
        theme="dark"
        onToggleTheme={vi.fn()}
      />
    )

    expect(screen.getByText('🔍 Private Search')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('1,250 docs')).toBeInTheDocument()
  })

  it('renders initializing status badge when indexReady is false', () => {
    render(
      <Header
        totalDocs={0}
        indexReady={false}
        theme="dark"
        onToggleTheme={vi.fn()}
      />
    )

    expect(screen.getByText('Initializing')).toBeInTheDocument()
  })

  it('calls onToggleTheme when theme toggle button is clicked', () => {
    const onToggleTheme = vi.fn()
    render(
      <Header
        totalDocs={100}
        indexReady={true}
        theme="dark"
        onToggleTheme={onToggleTheme}
      />
    )

    const toggleBtn = screen.getByRole('button', { name: /Switch to light mode/i })
    fireEvent.click(toggleBtn)
    expect(onToggleTheme).toHaveBeenCalledTimes(1)
  })
})

