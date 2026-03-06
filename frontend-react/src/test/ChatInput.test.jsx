import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ChatInput from '../components/ChatInput'

describe('ChatInput', () => {
  it('does not call onSend when input is empty', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)
    const button = screen.getByRole('button', { name: /send/i })
    await userEvent.click(button)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('calls onSend on Enter key (without Shift)', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)
    const textarea = screen.getByRole('textbox')
    await userEvent.type(textarea, 'How many sales?')
    await userEvent.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledWith('How many sales?')
  })

  it('does not send on Shift+Enter', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)
    const textarea = screen.getByRole('textbox')
    await userEvent.type(textarea, 'Hello')
    await userEvent.keyboard('{Shift>}{Enter}{/Shift}')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('prefill prop populates the textarea', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} prefill="Prefilled text" />)
    const textarea = screen.getByRole('textbox')
    expect(textarea).toHaveValue('Prefilled text')
  })

  it('button is disabled when disabled=true', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={true} />)
    const button = screen.getByRole('button', { name: /send/i })
    expect(button).toBeDisabled()
  })

  it('clears input after sending', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} disabled={false} />)
    const textarea = screen.getByRole('textbox')
    await userEvent.type(textarea, 'Test question')
    await userEvent.keyboard('{Enter}')
    expect(textarea).toHaveValue('')
  })
})
