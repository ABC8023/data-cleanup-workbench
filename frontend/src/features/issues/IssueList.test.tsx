import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Finding, PreviewResult } from '../../api/types'
import { IssueList } from './IssueList'

const MIXED_DATE_FINDING: Finding = {
  id: 'f1',
  rule_id: 'validity.mixed_date',
  severity: 2,
  columns: ['seen'],
  affected_row_count: 8,
  affected_ratio: 0.8,
  confidence: 0.8,
  risk_level: 'review_required',
  examples: [{ column: 'seen', value: '3/4/2026' }],
  suggested_operation: { operation: 'parse_date' },
  evidence: { iso_count: 6, slash_count: 2 },
}

const PREVIEW: PreviewResult = {
  before_rows: [{ seen: '3/4/2026' }],
  after_rows: [{ seen: '2026-04-03' }],
  schema_before: { seen: 'VARCHAR' },
  schema_after: { seen: 'VARCHAR' },
  null_deltas: { seen: 0 },
  row_count_delta: 0,
  validation_failures: [],
}

describe('IssueList', () => {
  it('adds a transformation only after preview and confirmed approval', async () => {
    const user = userEvent.setup()
    const onPreview = vi.fn().mockResolvedValue(PREVIEW)
    const onApprove = vi.fn()
    render(
      <IssueList
        findings={[MIXED_DATE_FINDING]}
        onPreview={onPreview}
        onApprove={onApprove}
      />,
    )

    await user.click(screen.getByRole('button', { name: /review mixed date/i }))

    expect(await screen.findByRole('table', { name: 'Before' })).toBeVisible()
    expect(screen.getByRole('table', { name: 'After' })).toBeVisible()
    expect(onPreview).toHaveBeenCalledWith(
      expect.objectContaining({ operation: 'parse_date', columns: ['seen'] }),
    )
    expect(onApprove).not.toHaveBeenCalled()

    const approve = screen.getByRole('button', { name: /approve transformation/i })
    expect(approve).toBeDisabled()
    await user.click(screen.getByLabelText(/i reviewed the before and after/i))
    await user.click(approve)

    expect(onApprove).toHaveBeenCalledWith(
      expect.objectContaining({ operation: 'parse_date' }),
    )
  })

  it('lets the user edit the suggested date formats before previewing', async () => {
    const user = userEvent.setup()
    const onPreview = vi.fn().mockResolvedValue(PREVIEW)
    render(
      <IssueList
        findings={[MIXED_DATE_FINDING]}
        onPreview={onPreview}
        onApprove={vi.fn()}
      />,
    )

    const second = screen.getByLabelText('Input format 2')
    expect(second).toHaveValue('%d/%m/%Y')
    await user.clear(second)
    await user.type(second, '%m/%d/%Y')

    const output = screen.getByLabelText('Output format')
    await user.clear(output)
    await user.type(output, '%d %b %Y')

    await user.click(screen.getByRole('button', { name: /review mixed date/i }))

    expect(onPreview).toHaveBeenCalledWith(
      expect.objectContaining({
        operation: 'parse_date',
        formats: ['%Y-%m-%d', '%m/%d/%Y'],
        output_format: '%d %b %Y',
      }),
    )
  })

  it('clears a stale preview when formats change', async () => {
    const user = userEvent.setup()
    render(
      <IssueList
        findings={[MIXED_DATE_FINDING]}
        onPreview={vi.fn().mockResolvedValue(PREVIEW)}
        onApprove={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /review mixed date/i }))
    expect(await screen.findByRole('table', { name: 'Before' })).toBeVisible()

    expect(
      screen.getByRole('button', { name: /update preview/i }),
    ).toBeVisible()

    await user.type(screen.getByLabelText('Input format 1'), 'x')

    expect(screen.queryByRole('table', { name: 'Before' })).toBeNull()
    expect(
      screen.getByRole('button', { name: /review mixed date/i }),
    ).toBeVisible()
  })

  it('offers no review action for informational findings', () => {
    render(
      <IssueList
        findings={[
          {
            ...MIXED_DATE_FINDING,
            id: 'f2',
            rule_id: 'statistics.rare_category',
            risk_level: 'informational',
            suggested_operation: null,
          },
        ]}
        onPreview={vi.fn()}
        onApprove={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: /review/i })).toBeNull()
    expect(screen.getByText(/rare_category/)).toBeInTheDocument()
  })
})
