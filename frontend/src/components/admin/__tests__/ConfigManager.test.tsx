import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ConfigManager } from '../ConfigManager'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getRuntimeConfig: vi.fn(),
    updateRuntimeConfig: vi.fn(),
  },
}))

describe('ConfigManager Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(adminClient.getRuntimeConfig).mockResolvedValue({
      settings: {
        log_level: 'INFO',
        rate_limit_per_minute: 100,
        crawler_max_depth: 2,
        crawler_politeness_delay: 1.0,
      },
      notice: 'Runtime-only settings. Changes reset when the server restarts.',
    })
  })

  it('renders runtime notice and configuration settings', async () => {
    render(<ConfigManager />)

    await waitFor(() => {
      expect(screen.getByText('Runtime Configuration')).toBeInTheDocument()
      expect(
        screen.getByText(/Runtime-only settings. Changes reset when the server restarts/i)
      ).toBeInTheDocument()
      expect(screen.getByText('Application Log Level')).toBeInTheDocument()
      expect(screen.getByText('API Rate Limit (Req/Min)')).toBeInTheDocument()
    })
  })

  it('updates allowlisted setting and shows success feedback', async () => {
    vi.mocked(adminClient.updateRuntimeConfig).mockResolvedValueOnce({
      settings: {
        log_level: 'DEBUG',
        rate_limit_per_minute: 100,
        crawler_max_depth: 2,
        crawler_politeness_delay: 1.0,
      },
      notice: 'Runtime-only settings. Changes reset when the server restarts.',
    })

    render(<ConfigManager />)

    const applyBtns = await screen.findAllByRole('button', { name: 'Apply' })
    const logLevelApply = applyBtns[0]

    fireEvent.click(logLevelApply)

    await waitFor(() => {
      expect(adminClient.updateRuntimeConfig).toHaveBeenCalledWith('log_level', 'INFO')
      expect(screen.getByText(/Updated 'log_level' successfully/i)).toBeInTheDocument()
    })
  })
})

