import { useState } from 'react'
import type { AiAttempt, AiPayloadPreview } from '../../api/types'

export interface DictionaryAiApi {
  previewAi(selected: Record<string, string[]>): Promise<AiPayloadPreview>
  approveAi(previewId: string): Promise<AiAttempt>
}

interface DictionaryEditorProps {
  columns: { name: string; inferred_type: string }[]
  descriptions: Record<string, string>
  onSave: (descriptions: Record<string, string>) => void
  api: DictionaryAiApi
}

const AI_ERROR_HINTS: Record<string, string> = {
  disabled:
    'AI assist is off. Restart the workbench with --ai anthropic (API key from the OS keyring or ANTHROPIC_API_KEY) to enable it.',
  no_api_key:
    'No API key found. Store one with the keyring (service data-cleanup-workbench, entry ai_api_key) or set ANTHROPIC_API_KEY, then restart.',
  denied: 'The AI provider rejected the API key — check it and try again.',
  timeout: 'The AI provider timed out — try again in a moment.',
  unavailable: 'The AI provider could not be reached — check your connection.',
  malformed: 'The AI reply could not be understood — try again.',
  expired: 'The approval window expired — preview the request again.',
}

function AiPreviewDialog({
  preview,
  onApprove,
  onCancel,
}: {
  preview: AiPayloadPreview
  onApprove: (previewId: string) => void
  onCancel: () => void
}) {
  return (
    <dialog open aria-labelledby="ai-preview-title">
      <h3 id="ai-preview-title">Review data sent to {preview.provider}</h3>
      <pre>
        <code>{JSON.stringify(preview.payload, null, 2)}</code>
      </pre>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
      <button type="button" onClick={() => onApprove(preview.id)}>
        Approve and send
      </button>
    </dialog>
  )
}

export function DictionaryEditor({
  columns,
  descriptions,
  onSave,
  api,
}: DictionaryEditorProps) {
  const [draft, setDraft] = useState<Record<string, string>>(descriptions)
  const [preview, setPreview] = useState<AiPayloadPreview | null>(null)
  const [aiNote, setAiNote] = useState<string | null>(null)

  const approve = async (previewId: string) => {
    const attempt = await api.approveAi(previewId)
    setPreview(null)
    if (attempt.suggestion) {
      setDraft((current) => {
        const next = { ...current }
        for (const column of attempt.suggestion!.columns) {
          if (!next[column.name]) next[column.name] = column.description
        }
        return next
      })
      setAiNote('AI suggestions filled empty descriptions.')
    } else {
      const code = attempt.error?.code ?? 'unknown'
      const hint =
        AI_ERROR_HINTS[code] ?? 'The deterministic dictionary remains available.'
      setAiNote(`AI unavailable (${code}). ${hint}`)
    }
  }

  return (
    <section aria-labelledby="dictionary-heading">
      <h2 id="dictionary-heading">Data dictionary</h2>
      <p className="hint">
        Describe what each column means; descriptions are included in the
        exported documentation. The optional AI assist shows you the exact
        payload before anything is sent — and sends nothing without approval.
      </p>
      <div className="dict-grid">
        {columns.map((column) => (
          <label key={column.name}>
            {column.name} ({column.inferred_type})
            <input
              type="text"
              placeholder="What does this column contain?"
              value={draft[column.name] ?? ''}
              onChange={(event) =>
                setDraft({ ...draft, [column.name]: event.target.value })
              }
            />
          </label>
        ))}
      </div>
      <button type="button" onClick={() => onSave(draft)}>
        Save descriptions
      </button>
      <button
        type="button"
        onClick={() => void api.previewAi({}).then(setPreview)}
      >
        Preview AI suggestion request
      </button>
      {aiNote && <p role="status">{aiNote}</p>}
      {preview && (
        <AiPreviewDialog
          preview={preview}
          onApprove={(previewId) => void approve(previewId)}
          onCancel={() => setPreview(null)}
        />
      )}
    </section>
  )
}
