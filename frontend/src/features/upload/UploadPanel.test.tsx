import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SessionManifest } from '../../api/types'
import { UploadPanel } from './UploadPanel'

const STAGED: SessionManifest = {
  id: 'a'.repeat(32),
  filename: 'sample.csv',
  size_bytes: 8,
  sha256: 'f'.repeat(64),
  state: 'staged',
}

describe('UploadPanel', () => {
  it('uploads a selected file and reports the staged session', async () => {
    const user = userEvent.setup()
    const upload = vi.fn().mockResolvedValue(STAGED)
    const onSession = vi.fn()
    render(<UploadPanel api={{ upload }} onSession={onSession} />)

    await user.upload(
      screen.getByLabelText(/choose dataset/i),
      new File(['a,b\n1,2'], 'sample.csv', { type: 'text/csv' }),
    )
    await user.click(screen.getByRole('button', { name: /profile dataset/i }))

    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'sample.csv' }),
      expect.any(Function),
    )
    expect(onSession).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'staged' }),
    )
  })

  it('disables profiling until a file is chosen and surfaces upload errors', async () => {
    const user = userEvent.setup()
    const upload = vi.fn().mockRejectedValue(new Error('file exceeds 5 GB limit'))
    render(<UploadPanel api={{ upload }} onSession={vi.fn()} />)

    expect(screen.getByRole('button', { name: /profile dataset/i })).toBeDisabled()

    await user.upload(
      screen.getByLabelText(/choose dataset/i),
      new File(['x'], 'big.csv', { type: 'text/csv' }),
    )
    await user.click(screen.getByRole('button', { name: /profile dataset/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /file exceeds 5 GB limit/i,
    )
  })
})
