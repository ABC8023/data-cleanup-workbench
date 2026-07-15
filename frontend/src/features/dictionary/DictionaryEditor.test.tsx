import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AiPayloadPreview } from '../../api/types'
import { DictionaryEditor } from './DictionaryEditor'

const COLUMNS = [{ name: 'customer_id', inferred_type: 'VARCHAR' }]

const PREVIEW: AiPayloadPreview = {
  id: 'preview-1',
  provider: 'http',
  payload: {
    columns: [{ name: 'customer_id', inferred_type: 'VARCHAR' }],
    approved_samples: {},
  },
  expires_at: '2026-07-15T12:05:00Z',
}

describe('DictionaryEditor', () => {
  it('shows the exact ai payload before enabling approval', async () => {
    const user = userEvent.setup()
    const previewAi = vi.fn().mockResolvedValue(PREVIEW)
    const approveAi = vi.fn().mockResolvedValue({
      suggestion: null,
      fallback: {},
      error: { code: 'disabled', message: 'AI suggestion unavailable' },
    })
    render(
      <DictionaryEditor
        columns={COLUMNS}
        descriptions={{}}
        onSave={vi.fn()}
        api={{ previewAi, approveAi }}
      />,
    )

    await user.click(
      screen.getByRole('button', { name: /preview ai suggestion request/i }),
    )

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Review data sent to http')
    expect(dialog).toHaveTextContent('customer_id')
    expect(previewAi).toHaveBeenCalledWith({})
    expect(approveAi).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /approve and send/i }))
    expect(approveAi).toHaveBeenCalledWith('preview-1')
  })

  it('cancel closes the dialog without sending, and edits save deterministically', async () => {
    const user = userEvent.setup()
    const approveAi = vi.fn()
    const onSave = vi.fn()
    render(
      <DictionaryEditor
        columns={COLUMNS}
        descriptions={{}}
        onSave={onSave}
        api={{ previewAi: vi.fn().mockResolvedValue(PREVIEW), approveAi }}
      />,
    )

    await user.click(
      screen.getByRole('button', { name: /preview ai suggestion request/i }),
    )
    await user.click(await screen.findByRole('button', { name: /cancel/i }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(approveAi).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText(/customer_id/), 'Primary key')
    await user.click(screen.getByRole('button', { name: /save descriptions/i }))
    expect(onSave).toHaveBeenCalledWith({ customer_id: 'Primary key' })
  })
})
