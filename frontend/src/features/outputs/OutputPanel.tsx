import type { OutputManifest } from '../../api/types'
import { ErrorState } from '../../components/ErrorState'

const KIND_LABELS: Record<string, string> = {
  cleaned: 'cleaned data',
  quarantine: 'quarantine file',
  recipe: 'recipe',
  report_html: 'quality report',
  report_json: 'JSON report',
  dictionary_md: 'data dictionary (Markdown)',
  dictionary_json: 'data dictionary (JSON)',
}

export interface ExecutionView {
  state: 'idle' | 'running' | 'failed' | 'cancelled'
  message?: string
  errorCode?: string
}

interface OutputPanelProps {
  execution: ExecutionView
  manifest: OutputManifest | null
  onExecute: () => void
  onCancel: () => void
  onDownload: (artifactId: string) => void
}

export function OutputPanel({
  execution,
  manifest,
  onExecute,
  onCancel,
  onDownload,
}: OutputPanelProps) {
  if (execution.state === 'failed' || execution.state === 'cancelled') {
    return (
      <ErrorState
        stage="Execution"
        code={execution.errorCode ?? execution.state}
        actionLabel="Retry"
        onAction={onExecute}
      />
    )
  }
  if (execution.state === 'running') {
    return (
      <section aria-live="polite">
        <p>{execution.message ?? 'Executing recipe…'}</p>
        <progress aria-label="Execution progress" />
        <button type="button" onClick={onCancel}>
          Cancel execution
        </button>
      </section>
    )
  }
  if (!manifest) {
    return (
      <section aria-labelledby="outputs-heading">
        <h2 id="outputs-heading">Outputs</h2>
        <p>Execute the approved recipe to produce downloadable outputs.</p>
        <button type="button" onClick={onExecute}>
          Execute recipe
        </button>
      </section>
    )
  }
  return (
    <section aria-labelledby="outputs-heading">
      <h2 id="outputs-heading">Outputs</h2>
      <p>
        {manifest.row_reconciliation.output} of {manifest.row_reconciliation.input}{' '}
        rows kept · {manifest.row_reconciliation.quarantined} quarantined ·{' '}
        {manifest.row_reconciliation.removed} removed
      </p>
      <ul>
        {manifest.artifacts.map((artifact) => (
          <li key={artifact.id}>
            <button type="button" onClick={() => onDownload(artifact.id)}>
              Download {KIND_LABELS[artifact.kind] ?? artifact.kind}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={onExecute}>
        Re-run execution
      </button>
    </section>
  )
}
