import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RecipeStep } from '../../api/types'
import { RecipeEditor } from './RecipeEditor'

const STEPS: RecipeStep[] = [
  { id: 'trim', operation: 'normalize_text', columns: ['name'], on_error: 'preserve' },
  {
    id: 'cast',
    operation: 'cast_number',
    columns: ['amount'],
    on_error: 'preserve',
    target: 'decimal',
  },
]

describe('RecipeEditor', () => {
  it('reorders steps with keyboard-accessible controls', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RecipeEditor steps={STEPS} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Move cast up' }))

    expect(onChange).toHaveBeenCalledWith([STEPS[1], STEPS[0]])
    expect(screen.getByRole('button', { name: 'Move trim up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move cast down' })).toBeDisabled()
  })

  it('removes steps', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RecipeEditor steps={STEPS} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Remove trim' }))

    expect(onChange).toHaveBeenCalledWith([STEPS[1]])
  })
})
