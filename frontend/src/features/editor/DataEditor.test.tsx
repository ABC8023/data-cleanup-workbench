import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AppliedEdit, EditPreview, RowsPreview } from '../../api/types'
import { DataEditor, type DataEditorApi } from './DataEditor'

const ROWS: RowsPreview = {
  table: 'customers',
  columns: ['customer_id', 'name', 'city'],
  total_rows: 3,
  rows: [
    ['c1', ' Ada ', 'kul'],
    ['c2', 'lin', null],
  ],
}

const TRIM_PREVIEW: EditPreview = {
  command: { operation: 'trim_whitespace', column: 'name' },
  table: 'customers',
  columns_before: ['customer_id', 'name', 'city'],
  columns_after: ['customer_id', 'name', 'city'],
  affected_row_count: 1,
  samples: [{ before: ' Ada ', after: 'Ada' }],
}

const APPLIED: AppliedEdit = {
  sequence: 1,
  table: 'customers',
  command: { operation: 'trim_whitespace', column: 'name' },
  staged_filename: 'edit-0001.parquet',
  row_count: 3,
}

function makeApi(overrides: Partial<DataEditorApi> = {}): DataEditorApi {
  return {
    getRows: vi.fn().mockResolvedValue(ROWS),
    previewEdit: vi.fn().mockResolvedValue(TRIM_PREVIEW),
    applyEdit: vi.fn().mockResolvedValue(APPLIED),
    listEdits: vi.fn().mockResolvedValue([]),
    ...overrides,
  }
}

describe('DataEditor', () => {
  it('shows a data preview grid with nulls marked', async () => {
    render(<DataEditor api={makeApi()} />)

    expect(
      await screen.findByRole('table', { name: 'Data preview' }),
    ).toBeVisible()
    expect(screen.getByText('customer_id')).toBeInTheDocument()
    expect(screen.getByText(/3 rows/)).toBeInTheDocument()
    expect(screen.getByText('∅')).toBeInTheDocument()
  })

  it('previews a typed command and applies it only on approval', async () => {
    const user = userEvent.setup()
    const api = makeApi({
      listEdits: vi
        .fn()
        .mockResolvedValueOnce([])
        .mockResolvedValue([APPLIED]),
    })
    render(<DataEditor api={api} />)
    await screen.findByRole('table', { name: 'Data preview' })

    await user.type(
      screen.getByLabelText('Command'),
      'trim whitespace in column name',
    )
    await user.click(screen.getByRole('button', { name: /preview edit/i }))

    expect(api.previewEdit).toHaveBeenCalledWith(
      'trim whitespace in column name',
    )
    expect(await screen.findByText(/1 values would change/)).toBeVisible()
    expect(api.applyEdit).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /apply edit/i }))

    expect(api.applyEdit).toHaveBeenCalledWith(
      'trim whitespace in column name',
    )
    expect(await screen.findByText(/applied edits \(1\)/i)).toBeVisible()
  })

  it('builds a move command from dragging one header onto another', async () => {
    const api = makeApi()
    render(<DataEditor api={api} />)
    await screen.findByRole('table', { name: 'Data preview' })

    const source = screen.getByText('city')
    const target = screen.getByText('customer_id')
    fireEvent.dragStart(source)
    fireEvent.dragOver(target)
    fireEvent.drop(target)

    await waitFor(() =>
      expect(api.previewEdit).toHaveBeenCalledWith(
        'move column city before customer_id',
      ),
    )
  })

  it('surfaces backend rejections from the preview', async () => {
    const user = userEvent.setup()
    const api = makeApi({
      previewEdit: vi
        .fn()
        .mockRejectedValue(new Error('{"detail":"unsupported edit command"}')),
    })
    render(<DataEditor api={api} />)
    await screen.findByRole('table', { name: 'Data preview' })

    await user.type(screen.getByLabelText('Command'), 'make it pretty')
    await user.click(screen.getByRole('button', { name: /preview edit/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'unsupported edit command',
    )
  })
})
