import { useState } from 'react'
import type { Finding, PreviewResult, RecipeStep } from '../../api/types'
import { PreviewPanel } from './PreviewPanel'
import { suggestStep } from './suggest'

const SEVERITY_LABELS: Record<number, string> = {
  1: 'info',
  2: 'warning',
  3: 'error',
}

interface IssueListProps {
  findings: Finding[]
  onPreview: (candidate: RecipeStep) => Promise<PreviewResult>
  onApprove: (step: RecipeStep) => void
}

function IssueItem({
  finding,
  onPreview,
  onApprove,
}: {
  finding: Finding
  onPreview: (candidate: RecipeStep) => Promise<PreviewResult>
  onApprove: (step: RecipeStep) => void
}) {
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const step = suggestStep(finding)

  const review = async () => {
    if (!step) return
    setError(null)
    try {
      setPreview(await onPreview(step))
    } catch (previewError) {
      setError(
        previewError instanceof Error ? previewError.message : 'preview failed',
      )
    }
  }

  return (
    <article aria-label={finding.rule_id}>
      <h3>{finding.rule_id}</h3>
      <p>
        {SEVERITY_LABELS[finding.severity] ?? finding.severity} ·{' '}
        {finding.affected_row_count.toLocaleString()} affected ·{' '}
        {Math.round(finding.confidence * 100)}% confidence · risk{' '}
        {finding.risk_level.replace('_', ' ')}
      </p>
      <p>Columns: {finding.columns.join(', ')}</p>
      {finding.examples.length > 0 && (
        <details>
          <summary>Examples</summary>
          {finding.examples.map((example) => example.value).join(', ')}
        </details>
      )}
      {step && (
        <button type="button" onClick={() => void review()}>
          Review {finding.rule_id.split('.')[1]?.replace(/_/g, ' ')}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {preview && (
        <PreviewPanel
          preview={preview}
          requireConfirmation={finding.risk_level === 'review_required'}
          onApprove={() => {
            if (step) onApprove(step)
            setPreview(null)
          }}
        />
      )}
    </article>
  )
}

export function IssueList({ findings, onPreview, onApprove }: IssueListProps) {
  return (
    <section aria-labelledby="issues-heading">
      <h2 id="issues-heading">Findings</h2>
      {findings.length === 0 && <p>No issues detected.</p>}
      {findings.map((finding) => (
        <IssueItem
          key={finding.id}
          finding={finding}
          onPreview={onPreview}
          onApprove={onApprove}
        />
      ))}
    </section>
  )
}
