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

function DateFormatFields({
  step,
  onChange,
}: {
  step: RecipeStep
  onChange: (next: RecipeStep) => void
}) {
  const formats = (step.formats as string[]) ?? []
  const setFormats = (next: string[]) => onChange({ ...step, formats: next })
  return (
    <fieldset className="format-editor">
      <legend>Date formats</legend>
      <p className="hint">
        Formats tried in order when parsing (strptime codes: %Y year, %m
        month, %d day, %H:%M time). The suggestions are pre-filled — edit
        them to match your data, then preview again.
      </p>
      {formats.map((format, index) => (
        <div className="format-row" key={index}>
          <input
            type="text"
            aria-label={`Input format ${index + 1}`}
            value={format}
            onChange={(event) =>
              setFormats(
                formats.map((current, position) =>
                  position === index ? event.target.value : current,
                ),
              )
            }
          />
          <button
            type="button"
            aria-label={`Remove format ${index + 1}`}
            disabled={formats.length === 1}
            onClick={() =>
              setFormats(formats.filter((_, position) => position !== index))
            }
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" onClick={() => setFormats([...formats, ''])}>
        Add format
      </button>
      <label className="format-output">
        Output format
        <input
          type="text"
          value={(step.output_format as string) ?? '%Y-%m-%d'}
          onChange={(event) =>
            onChange({ ...step, output_format: event.target.value })
          }
        />
      </label>
    </fieldset>
  )
}

function effectiveStep(step: RecipeStep): RecipeStep | null {
  if (step.operation !== 'parse_date') return step
  const formats = ((step.formats as string[]) ?? [])
    .map((format) => format.trim())
    .filter(Boolean)
  if (formats.length === 0) return null
  const output = String(step.output_format ?? '').trim() || '%Y-%m-%d'
  return { ...step, formats, output_format: output }
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
  const [step, setStep] = useState<RecipeStep | null>(() =>
    suggestStep(finding),
  )

  const editStep = (next: RecipeStep) => {
    setStep(next)
    // The shown preview no longer matches the edited step; ask for a new one.
    setPreview(null)
  }

  const review = async () => {
    if (!step) return
    const candidate = effectiveStep(step)
    if (!candidate) {
      setError('add at least one date format')
      return
    }
    setError(null)
    try {
      setPreview(await onPreview(candidate))
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
      {step?.operation === 'parse_date' && (
        <DateFormatFields step={step} onChange={editStep} />
      )}
      {step && (
        <button type="button" onClick={() => void review()}>
          {preview
            ? 'Update preview'
            : `Review ${finding.rule_id.split('.')[1]?.replace(/_/g, ' ') ?? ''}`}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {preview && step && (
        <PreviewPanel
          preview={preview}
          requireConfirmation={finding.risk_level === 'review_required'}
          onApprove={() => {
            const candidate = effectiveStep(step)
            if (candidate) onApprove(candidate)
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
      <p className="hint">
        Issues detected in your data. Click Review to see exactly what a fix
        would change — nothing is applied until you approve it.
      </p>
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
