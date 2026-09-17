import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CrawlManager } from '../CrawlManager'
import { adminClient } from '../../../api/adminClient'

vi.mock('../../../api/adminClient', () => ({
  adminClient: {
    getCrawlerStatus: vi.fn(),
    startCrawler: vi.fn(),
    pauseCrawler: vi.fn(),
    resumeCrawler: vi.fn(),
    stopCrawler: vi.fn(),
  },
}))

describe('CrawlManager Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(adminClient.getCrawlerStatus).mockResolvedValue({
      crawl_id: 'crawl-initial',
      status: 'idle',
      documents_crawled: 0,
      documents_indexed: 0,
      errors: 0,
      urls_queued: 0,
      progress_percent: 0,
    })
  })

  it('renders initial idle status and controls', async () => {
    render(<CrawlManager />)

    await waitFor(() => {
      expect(screen.getByText('Web Crawler Orchestration')).toBeInTheDocument()
      expect(screen.getByText('IDLE')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Launch Crawler' })).toBeInTheDocument()
    })
  })

  it('validates seed URLs before starting', async () => {
    render(<CrawlManager />)

    const textarea = await screen.findByLabelText(/Seed URLs/i)
    fireEvent.change(textarea, { target: { value: '   ' } })

    const startBtn = screen.getByRole('button', { name: 'Launch Crawler' })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(adminClient.startCrawler).not.toHaveBeenCalled()
    })
  })

  it('starts crawl successfully and displays running status', async () => {
    vi.mocked(adminClient.startCrawler).mockResolvedValueOnce({
      crawl_id: 'crawl-100',
      status: 'running',
      documents_crawled: 1,
      documents_indexed: 1,
      errors: 0,
      urls_queued: 5,
      progress_percent: 2,
    })

    render(<CrawlManager />)

    const startBtn = await screen.findByRole('button', { name: 'Launch Crawler' })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(adminClient.startCrawler).toHaveBeenCalledWith(
        expect.objectContaining({
          seed_urls: ['https://example.com'],
          max_documents: 500,
          max_depth: 2,
        })
      )
    })
  })

  it('handles pause, resume, and stop button actions', async () => {
    vi.mocked(adminClient.getCrawlerStatus).mockResolvedValue({
      crawl_id: 'crawl-active',
      status: 'running',
      documents_crawled: 10,
      documents_indexed: 10,
      errors: 0,
      urls_queued: 20,
      progress_percent: 20,
    })

    vi.mocked(adminClient.pauseCrawler).mockResolvedValueOnce({
      crawl_id: 'crawl-active',
      status: 'paused',
      documents_crawled: 10,
      documents_indexed: 10,
      errors: 0,
      urls_queued: 20,
      progress_percent: 20,
    })

    render(<CrawlManager />)

    const pauseBtn = await screen.findByRole('button', { name: 'Pause Crawl' })
    fireEvent.click(pauseBtn)

    await waitFor(() => {
      expect(adminClient.pauseCrawler).toHaveBeenCalledTimes(1)
    })
  })
})

