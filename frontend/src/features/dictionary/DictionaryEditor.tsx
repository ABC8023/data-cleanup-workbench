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
      setAiNote(
        `AI unavailable (${attempt.error?.code ?? 'unknown'}); deterministic dictionary remains.`,
      )
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
