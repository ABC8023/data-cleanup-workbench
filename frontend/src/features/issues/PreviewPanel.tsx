import { useState } from 'react'
import type { PreviewResult } from '../../api/types'

interface PreviewPanelProps {
  preview: PreviewResult
  requireConfirmation: boolean
  onApprove: () => void
}

function SampleTable({
  title,
  schema,
  rows,
}: {
  title: string
  schema: Record<string, string>
  rows: Record<string, unknown>[]
}) {
  const columns = Object.keys(schema)
  return (
    <table>
      <caption>{title}</caption>
      <thead>
        <tr>
          {columns.map((name) => (
            <th key={name} scope="col">
              {name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 5).map((row, index) => (
          <tr key={index}>
            {columns.map((name) => (
              <td key={name}>{row[name] === null ? '∅' : String(row[name])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function PreviewPanel({
  preview,
  requireConfirmation,
  onApprove,
}: PreviewPanelProps) {
  const [confirmed, setConfirmed] = useState(!requireConfirmation)
  return (
    <section aria-label="Transformation preview">
      <SampleTable
        title="Before"
        schema={preview.schema_before}
        rows={preview.before_rows}
      />
      <SampleTable
        title="After"
        schema={preview.schema_after}
        rows={preview.after_rows}
      />
      <p>Row count change: {preview.row_count_delta}</p>
      {preview.validation_failures.length > 0 && (
        <ul role="alert">
          {preview.validation_failures.map((failure) => (
            <li key={failure}>{failure}</li>
          ))}
        </ul>
      )}
      {requireConfirmation && (
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          I reviewed the before and after samples
        </label>
      )}
      <button type="button" disabled={!confirmed} onClick={onApprove}>
        Approve transformation
      </button>
    </section>
  )
}
