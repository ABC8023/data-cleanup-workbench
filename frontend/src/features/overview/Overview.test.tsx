import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { DatasetProfile } from '../../api/types'
import { Overview } from './Overview'

const PROFILE: DatasetProfile = {
  source_fingerprint: 'fixture',
  table: 'data',
  row_count: 1234,
  sampled: false,
  columns: [
    {
      name: 'customer_id',
      inferred_type: 'VARCHAR',
      null_count: 1,
      distinct_count: 3,
      min_value: 'c1',
      max_value: 'c9',
      examples: ['c1', 'c2'],
      top_values: [['c1', 2]],
    },
  ],
}

describe('Overview', () => {
  it('summarizes rows, columns, findings, and the column table', () => {
    render(<Overview profile={PROFILE} findingCount={4} />)

    expect(
      screen.getByText(/1,234 rows · 1 columns · 4 findings/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('rowheader', { name: 'customer_id' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'VARCHAR' })).toBeInTheDocument()
  })

  it('keeps sample values collapsed by default', () => {
    render(<Overview profile={PROFILE} findingCount={0} />)

    const details = screen.getByText(/show samples/i).closest('details')
    expect(details).not.toHaveAttribute('open')
    expect(details).toHaveTextContent('c1, c2')
  })
})
