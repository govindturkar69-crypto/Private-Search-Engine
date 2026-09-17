import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { StatisticsPanel } from '../StatisticsPanel'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getIndexMetrics: vi.fn(),
    clearIndex: vi.fn(),
  },
}))

describe('StatisticsPanel Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(adminClient.getIndexMetrics).mockResolvedValue({
      total_documents: 1200,
      total_terms: 5000,
      total_postings: 15000,
      avg_postings_per_term: 3.0,
      index_size_mb: 4.5,
      last_updated: '2026-09-15 12:00:00',
      health_status: 'healthy',
    })
  })

  it('renders index statistics correctly', async () => {
    render(<StatisticsPanel />)

    await waitFor(() => {
      expect(screen.getByText('Index Statistics & Storage')).toBeInTheDocument()
      expect(screen.getByText('1,200')).toBeInTheDocument()
      expect(screen.getByText('5,000')).toBeInTheDocument()
      expect(screen.getByText('15,000')).toBeInTheDocument()
      expect(screen.getByText('4.50 MB')).toBeInTheDocument()
      expect(screen.getByText('HEALTHY')).toBeInTheDocument()
    })
  })

  it('opens confirmation modal and requires CLEAR to delete index', async () => {
    vi.mocked(adminClient.clearIndex).mockResolvedValueOnce({
      message: 'Inverted index cleared successfully.',
    })

    render(<StatisticsPanel />)

    const clearBtn = await screen.findByRole('button', {
      name: 'Clear Entire Inverted Index',
    })
    fireEvent.click(clearBtn)

    // Modal appears
    expect(screen.getByText('⚠️ Confirm Index Deletion')).toBeInTheDocument()

    const confirmInput = screen.getByPlaceholderText('Type CLEAR to confirm')
    const permanentClearBtn = screen.getByRole('button', {
      name: 'Permanently Clear Index',
    })

    // Button disabled when input is empty
    expect(permanentClearBtn).toBeDisabled()

    // Type CLEAR
    fireEvent.change(confirmInput, { target: { value: 'CLEAR' } })
    expect(permanentClearBtn).toBeEnabled()

    fireEvent.click(permanentClearBtn)

    await waitFor(() => {
      expect(adminClient.clearIndex).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Inverted index cleared successfully.')).toBeInTheDocument()
    })
  })
})

