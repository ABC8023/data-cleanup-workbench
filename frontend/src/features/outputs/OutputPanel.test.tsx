import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { OutputManifest } from '../../api/types'
import { OutputPanel } from './OutputPanel'

const MANIFEST: OutputManifest = {
  source_fingerprint: 'fixture',
  recipe_hash: 'abc',
  app_version: '0.1.0',
  row_reconciliation: { input: 10, output: 8, removed: 1, quarantined: 1 },
  state: 'complete',
  artifacts: [
    {
      id: 'report_html',
      kind: 'report_html',
      filename: 'report.html',
      sha256: 'a'.repeat(64),
      size_bytes: 10,
    },
    {
      id: 'cleaned',
      kind: 'cleaned',
      filename: 'cleaned.parquet',
      sha256: 'b'.repeat(64),
      size_bytes: 20,
    },
  ],
}

describe('OutputPanel', () => {
  it('lists only manifest artifacts and downloads by artifact id', async () => {
    const user = userEvent.setup()
    const onDownload = vi.fn()
    render(
      <OutputPanel
        execution={{ state: 'idle' }}
        manifest={MANIFEST}
        onExecute={vi.fn()}
        onCancel={vi.fn()}
        onDownload={onDownload}
      />,
    )

    expect(screen.getAllByRole('button', { name: /^download/i })).toHaveLength(2)
    await user.click(
      screen.getByRole('button', { name: /download quality report/i }),
    )
    expect(onDownload).toHaveBeenCalledWith('report_html')
    expect(screen.getByText(/8 of 10 rows kept/)).toBeInTheDocument()
  })

  it('shows progress with cancel while running and no downloads', () => {
    render(
      <OutputPanel
        execution={{ state: 'running', message: 'Executing recipe…' }}
        manifest={null}
        onExecute={vi.fn()}
        onCancel={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    expect(screen.getByText(/executing recipe/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /cancel execution/i }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^download/i })).toBeNull()
  })

  it('names the failed stage and offers retry as the only next action', async () => {
    const user = userEvent.setup()
    const onExecute = vi.fn()
    render(
      <OutputPanel
        execution={{ state: 'failed', errorCode: 'execution_failed' }}
        manifest={null}
        onExecute={onExecute}
        onCancel={vi.fn()}
        onDownload={vi.fn()}
      />,
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/execution failed/i)
    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(onExecute).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /^download/i })).toBeNull()
  })
})
