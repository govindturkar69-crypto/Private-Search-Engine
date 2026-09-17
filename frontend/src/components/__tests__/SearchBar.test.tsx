import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { SearchBar } from '../SearchBar'
import { apiClient } from '../../api/client'

vi.mock('../../api/client', () => ({
  apiClient: {
    getSuggestions: vi.fn(),
  },
}))

describe('SearchBar Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders search input with combobox ARIA roles', () => {
    render(<SearchBar onSearch={vi.fn()} loading={false} />)

    const input = screen.getByRole('combobox', { name: 'Search query' })
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-autocomplete', 'list')
    expect(input).toHaveAttribute('aria-expanded', 'false')
  })

  it('calls onSearch when form is submitted with non-empty query', () => {
    const onSearch = vi.fn()
    render(<SearchBar onSearch={onSearch} loading={false} />)

    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'python crawler' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    expect(onSearch).toHaveBeenCalledWith('python crawler')
  })

  it('does not call onSearch when form is submitted with whitespace-only query', () => {
    const onSearch = vi.fn()
    render(<SearchBar onSearch={onSearch} loading={false} />)

    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: '    ' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    expect(onSearch).not.toHaveBeenCalled()
  })

  it('disables input and submit button when loading is true', () => {
    render(<SearchBar onSearch={vi.fn()} loading={true} />)

    expect(screen.getByRole('combobox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Submit search' })).toBeDisabled()
    expect(screen.getByText('Searching...')).toBeInTheDocument()
  })

  it('clears query and closes suggestions when clear button is clicked', () => {
    render(<SearchBar initialQuery="testing" onSearch={vi.fn()} loading={false} />)

    const clearBtn = screen.getByRole('button', { name: 'Clear search input' })
    expect(clearBtn).toBeInTheDocument()

    fireEvent.click(clearBtn)
    expect(screen.getByRole('combobox')).toHaveValue('')
  })

  it('debounces autocomplete suggestions by 300ms with min 2 characters', async () => {
    vi.mocked(apiClient.getSuggestions).mockResolvedValue({
      prefix: 'py',
      suggestions: ['python', 'pytest', 'pydantic'],
    })

    render(<SearchBar onSearch={vi.fn()} loading={false} />)
    const input = screen.getByRole('combobox')

    // 1 char -> should not call
    fireEvent.change(input, { target: { value: 'p' } })
    act(() => {
      vi.advanceTimersByTime(350)
    })
    expect(apiClient.getSuggestions).not.toHaveBeenCalled()

    // 2 chars -> should call after 300ms
    fireEvent.change(input, { target: { value: 'py' } })
    expect(apiClient.getSuggestions).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    expect(apiClient.getSuggestions).toHaveBeenCalledWith('py', 5, expect.any(AbortSignal))
  })

  it('supports Arrow Down, Arrow Up, and Enter keyboard selection of suggestions', async () => {
    vi.mocked(apiClient.getSuggestions).mockResolvedValue({
      prefix: 'py',
      suggestions: ['python', 'pytest'],
    })

    const onSearch = vi.fn()
    render(<SearchBar onSearch={onSearch} loading={false} />)
    const input = screen.getByRole('combobox')

    fireEvent.change(input, { target: { value: 'py' } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    // Arrow Down to first suggestion ('python')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', 'suggestion-item-0')

    // Arrow Down to second suggestion ('pytest')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', 'suggestion-item-1')

    // Press Enter to select
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSearch).toHaveBeenCalledWith('pytest')
    expect(input).toHaveValue('pytest')
  })

  it('closes suggestions dropdown on Escape key', async () => {
    vi.mocked(apiClient.getSuggestions).mockResolvedValue({
      prefix: 'py',
      suggestions: ['python'],
    })

    render(<SearchBar onSearch={vi.fn()} loading={false} />)
    const input = screen.getByRole('combobox')

    fireEvent.change(input, { target: { value: 'py' } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.getByRole('listbox')).toBeInTheDocument()

    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('closes suggestions dropdown on outside click', async () => {
    vi.mocked(apiClient.getSuggestions).mockResolvedValue({
      prefix: 'py',
      suggestions: ['python'],
    })

    render(
      <div>
        <div data-testid="outside">Outside area</div>
        <SearchBar onSearch={vi.fn()} loading={false} />
      </div>
    )

    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'py' } })
    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.getByRole('listbox')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
