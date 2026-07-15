import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DuplicateGroup } from '../../api/types'
import { DuplicateReview } from './DuplicateReview'

const GROUP: DuplicateGroup = {
  id: 'g1',
  row_ids: ['1', '2'],
  display_values: ['j@x.com | John Smith', 'j@x.com | JOHN SMITH'],
  confidence: 0.95,
  evidence: { name: 1.0, email: 1.0 },
}

describe('DuplicateReview', () => {
  it('starts undecided and saves keep separate without a survivor', async () => {
    const user = userEvent.setup()
    const onDecision = vi.fn()
    render(<DuplicateReview group={GROUP} onDecision={onDecision} />)

    const save = screen.getByRole('button', { name: /save decision/i })
    expect(save).toBeDisabled()

    await user.click(screen.getByLabelText(/keep separate/i))
    await user.click(save)

    expect(onDecision).toHaveBeenCalledWith({
      action: 'keep_separate',
      survivor_row_id: null,
    })
  })

  it('requires a survivor before removing a record', async () => {
    const user = userEvent.setup()
    const onDecision = vi.fn()
    render(<DuplicateReview group={GROUP} onDecision={onDecision} />)

    await user.click(screen.getByLabelText(/remove record/i))
    const save = screen.getByRole('button', { name: /save decision/i })
    expect(save).toBeDisabled()

    await user.click(screen.getByLabelText('Row 1'))
    await user.click(save)

    expect(onDecision).toHaveBeenCalledWith({
      action: 'remove_record',
      survivor_row_id: '1',
    })
    expect(screen.getByText(/95% confidence/)).toBeInTheDocument()
    expect(screen.getAllByText(/100% match/i)).toHaveLength(2)
  })
})
