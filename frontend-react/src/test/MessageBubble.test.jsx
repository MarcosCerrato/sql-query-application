import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MessageBubble from '../components/MessageBubble'

describe('MessageBubble', () => {
  it('renders loading dots for type=loading', () => {
    const { container } = render(
      <MessageBubble message={{ type: 'loading' }} />
    )
    // Loading indicator uses animate-bounce spans
    const dots = container.querySelectorAll('.animate-bounce')
    expect(dots.length).toBe(3)
  })

  it('renders error text in red container for type=error', () => {
    render(
      <MessageBubble message={{ type: 'error', content: 'Something went wrong' }} />
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    // The error container should have red styling
    const el = screen.getByText('Something went wrong')
    expect(el.closest('div')).toHaveClass('text-red-700')
  })

  it('renders user message aligned to the right for role=user', () => {
    const { container } = render(
      <MessageBubble message={{ role: 'user', type: 'text', content: 'Hello' }} />
    )
    const outer = container.firstChild
    expect(outer).toHaveClass('justify-end')
  })

  it('renders answer with SQL block when sql is provided', () => {
    render(
      <MessageBubble
        message={{
          type: 'answer',
          content: 'Here is the result',
          sql: 'SELECT * FROM sales',
        }}
      />
    )
    expect(screen.getByText('Here is the result')).toBeInTheDocument()
    // SQLBlock renders the SQL
    expect(screen.getByText('SELECT * FROM sales')).toBeInTheDocument()
  })

  it('does not render SQLBlock when no sql provided', () => {
    render(
      <MessageBubble
        message={{ type: 'answer', content: 'No SQL here' }}
      />
    )
    expect(screen.getByText('No SQL here')).toBeInTheDocument()
    // SQL label from SQLBlock should not exist
    expect(screen.queryByText('SQL')).not.toBeInTheDocument()
  })
})
