import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LogViewer } from '../LogViewer'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getLogs: vi.fn(),
  },
}))

describe('LogViewer Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(adminClient.getLogs).mockResolvedValue([
      {
        timestamp: '2026-09-15 12:00:01',
        level: 'INFO',
        module: 'src.main',
        message: 'System initialization complete',
      },
      {
        timestamp: '2026-09-15 12:00:02',
        level: 'ERROR',
        module: 'src.crawler',
        message: 'Connection timed out',
      },
    ])
  })

  it('renders log entries safely with correct level badges', async () => {
    render(<LogViewer />)

    await waitFor(() => {
      expect(screen.getByText('Application Logs')).toBeInTheDocument()
      expect(screen.getByText('System initialization complete')).toBeInTheDocument()
      expect(screen.getByText('Connection timed out')).toBeInTheDocument()
      expect(screen.getAllByText('INFO').length).toBeGreaterThan(0)
      expect(screen.getAllByText('ERROR').length).toBeGreaterThan(0)
    })
  })

  it('filters logs by lines and level when selected', async () => {
    render(<LogViewer />)

    const linesSelect = await screen.findByLabelText('Lines:')
    fireEvent.change(linesSelect, { target: { value: '250' } })

    await waitFor(() => {
      expect(adminClient.getLogs).toHaveBeenCalledWith(250, 'ALL')
    })

    const levelSelect = screen.getByLabelText('Level:')
    fireEvent.change(levelSelect, { target: { value: 'ERROR' } })

    await waitFor(() => {
      expect(adminClient.getLogs).toHaveBeenCalledWith(250, 'ERROR')
    })
  })
})
