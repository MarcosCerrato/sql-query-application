import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SQLBlock from '../components/SQLBlock'

describe('SQLBlock', () => {
  it('displays the SQL in the document', () => {
    render(<SQLBlock sql="SELECT * FROM sales" />)
    expect(screen.getByText('SELECT * FROM sales')).toBeInTheDocument()
  })

  it('clicking Copy SQL calls clipboard.writeText', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      writable: true,
      configurable: true,
    })

    render(<SQLBlock sql="SELECT id FROM sales" />)
    const button = screen.getByRole('button', { name: /copy sql/i })
    await userEvent.click(button)
    expect(writeText).toHaveBeenCalledWith('SELECT id FROM sales')
  })

  it('shows "Copied!" after clicking and reverts after 2s', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      writable: true,
      configurable: true,
    })

    render(<SQLBlock sql="SELECT 1" />)
    const button = screen.getByRole('button', { name: /copy sql/i })

    await userEvent.click(button)
    // After click, button should show "Copied!"
    await act(async () => {})
    expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument()

    // After 2 seconds, should revert to "Copy SQL"
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByRole('button', { name: /copy sql/i })).toBeInTheDocument()

    vi.useRealTimers()
  })
})
