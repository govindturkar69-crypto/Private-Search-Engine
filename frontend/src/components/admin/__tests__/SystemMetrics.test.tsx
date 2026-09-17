import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SystemMetrics } from '../SystemMetrics'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getSystemMetrics: vi.fn(),
  },
}))

describe('SystemMetrics Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(adminClient.getSystemMetrics).mockResolvedValue({
      cpu_percent: 25.4,
      memory_percent: 62.1,
      disk_percent: 44.8,
      memory_used_mb: 4968,
      memory_total_mb: 8000,
      disk_used_gb: 112.5,
      disk_total_gb: 250.0,
    })
  })

  it('renders measured system resource utilization gauges', async () => {
    render(<SystemMetrics />)

    await waitFor(() => {
      expect(screen.getByText('System Performance & Resources')).toBeInTheDocument()
      expect(screen.getByText('25.4%')).toBeInTheDocument()
      expect(screen.getByText('62.1%')).toBeInTheDocument()
      expect(screen.getByText('44.8%')).toBeInTheDocument()
      expect(screen.getByText(/4,968 MB used of 8,000 MB total/)).toBeInTheDocument()
      expect(screen.getByText(/112.50 GB used of 250.00 GB total/)).toBeInTheDocument()
    })
  })
})

