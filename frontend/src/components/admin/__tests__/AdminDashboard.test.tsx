import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AdminDashboard } from '../../../pages/AdminDashboard'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getAuthToken: vi.fn(),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    checkHealth: vi.fn(),
    getCrawlerStatus: vi.fn(),
    getIndexMetrics: vi.fn(),
    getSystemMetrics: vi.fn(),
    getLogs: vi.fn(),
    getRuntimeConfig: vi.fn(),
  },
}))

describe('AdminDashboard & Authentication Gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(adminClient.getCrawlerStatus).mockResolvedValue({
      crawl_id: 'crawl-1',
      status: 'idle',
      documents_crawled: 0,
      documents_indexed: 0,
      errors: 0,
      urls_queued: 0,
      progress_percent: 0,
    })

    vi.mocked(adminClient.getIndexMetrics).mockResolvedValue({
      total_documents: 50,
      total_terms: 200,
      total_postings: 500,
      avg_postings_per_term: 2.5,
      index_size_mb: 2.1,
      last_updated: '2026-09-15T12:00:00Z',
      health_status: 'healthy',
    })

    vi.mocked(adminClient.getSystemMetrics).mockResolvedValue({
      cpu_percent: 10.0,
      memory_percent: 45.0,
      disk_percent: 55.0,
      memory_used_mb: 3600,
      memory_total_mb: 8000,
      disk_used_gb: 110,
      disk_total_gb: 250,
    })

    vi.mocked(adminClient.getLogs).mockResolvedValue([
      {
        timestamp: '2026-09-15 12:00:00',
        level: 'INFO',
        module: 'src.main',
        message: 'Server started',
      },
    ])

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

  it('renders login gate when no token exists in session', async () => {
    vi.mocked(adminClient.getAuthToken).mockReturnValue(null)

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Admin Authentication')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Enter secret token...')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Authenticate' })).toBeInTheDocument()
    })
  })

  it('authenticates user and transitions to dashboard upon valid token entry', async () => {
    vi.mocked(adminClient.getAuthToken).mockReturnValue(null)
    vi.mocked(adminClient.checkHealth).mockResolvedValueOnce({
      status: 'ok',
      admin_ready: true,
      crawler_ready: true,
      index_ready: true,
      timestamp: '2026-09-15T12:00:00Z',
    })

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>
    )

    const tokenInput = await screen.findByPlaceholderText('Enter secret token...')
    fireEvent.change(tokenInput, { target: { value: 'correct-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }))

    await waitFor(() => {
      expect(adminClient.setAuthToken).toHaveBeenCalledWith('correct-secret')
      expect(screen.getByText('Admin Portal')).toBeInTheDocument()
      expect(screen.getByText('Web Crawler Orchestration')).toBeInTheDocument()
    })
  })

  it('displays error message when invalid token is entered', async () => {
    vi.mocked(adminClient.getAuthToken).mockReturnValue(null)
    vi.mocked(adminClient.checkHealth).mockRejectedValueOnce(
      new Error('Invalid admin token. Access denied.')
    )

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>
    )

    const tokenInput = await screen.findByPlaceholderText('Enter secret token...')
    fireEvent.change(tokenInput, { target: { value: 'bad-token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }))

    await waitFor(() => {
      expect(screen.getByText('Invalid admin token. Access denied.')).toBeInTheDocument()
      expect(adminClient.clearAuthToken).toHaveBeenCalled()
    })
  })

  it('switches tabs smoothly when authenticated', async () => {
    vi.mocked(adminClient.getAuthToken).mockReturnValue('valid-token')
    vi.mocked(adminClient.checkHealth).mockResolvedValue({
      status: 'ok',
      admin_ready: true,
      crawler_ready: true,
      index_ready: true,
      timestamp: '2026-09-15T12:00:00Z',
    })

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>
    )

    // Crawler tab default
    await waitFor(() => {
      expect(screen.getByText('Web Crawler Orchestration')).toBeInTheDocument()
    })

    // Click Index & Stats tab
    fireEvent.click(screen.getByRole('button', { name: /Index & Stats/i }))
    await waitFor(() => {
      expect(screen.getByText('Index Statistics & Storage')).toBeInTheDocument()
    })

    // Click System Resources tab
    fireEvent.click(screen.getByRole('button', { name: /System Resources/i }))
    await waitFor(() => {
      expect(screen.getByText('System Performance & Resources')).toBeInTheDocument()
    })

    // Click Logs tab
    fireEvent.click(screen.getByRole('button', { name: /Logs/i }))
    await waitFor(() => {
      expect(screen.getByText('Application Logs')).toBeInTheDocument()
    })

    // Click Configuration tab
    fireEvent.click(screen.getByRole('button', { name: /Configuration/i }))
    await waitFor(() => {
      expect(screen.getByText('Runtime Configuration')).toBeInTheDocument()
    })
  })

  it('clears token and returns to login gate when logout is clicked', async () => {
    vi.mocked(adminClient.getAuthToken).mockReturnValue('valid-token')
    vi.mocked(adminClient.checkHealth).mockResolvedValue({
      status: 'ok',
      admin_ready: true,
      crawler_ready: true,
      index_ready: true,
      timestamp: '2026-09-15T12:00:00Z',
    })

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Logout')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Logout'))

    await waitFor(() => {
      expect(adminClient.clearAuthToken).toHaveBeenCalled()
      expect(screen.getByText('Admin Authentication')).toBeInTheDocument()
    })
  })
})

