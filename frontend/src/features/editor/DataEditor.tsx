import { useCallback, useEffect, useState } from 'react'
import type {
  AppliedEdit,
  EditCommand,
  EditPreview,
  RowsPreview,
} from '../../api/types'

export interface DataEditorApi {
  getRows(): Promise<RowsPreview>
  previewEdit(command: string): Promise<EditPreview>
  applyEdit(command: string): Promise<AppliedEdit>
  listEdits(): Promise<AppliedEdit[]>
}

const GRID_ROWS = 10

const COMMAND_EXAMPLES = [
  'rename column old_name to new_name',
  'drop column name',
  "replace 'N/A' with null in column name",
  "fill nulls in column name with 'unknown'",
  'uppercase column name',
  'lowercase column name',
  'trim whitespace in column name',
  'move column name before other_name',
  'move column name to end',
]

function quoteName(name: string): string {
  if (/[\s'"]/.test(name)) return `"${name.replace(/"/g, '')}"`
  return name
}

function describeCommand(command: EditCommand): string {
  const parts = [String(command.operation).replace(/_/g, ' '), command.column]
  if (command.operation === 'rename_column') {
    parts.push(`→ ${String(command.new_name)}`)
  }
  if (command.operation === 'move_column') {
    parts.push(
      command.reference
        ? `${String(command.position)} ${String(command.reference)}`
        : `to ${String(command.position)}`,
    )
  }
  return parts.join(' ')
}

function errorDetail(error: unknown): string {
  if (error instanceof Error) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown }
      if (parsed?.detail) return String(parsed.detail)
    } catch {
      // not JSON — fall through to the raw message
    }
    return error.message || 'request failed'
  }
  return 'request failed'
}

interface PendingEdit {
  command: string
  preview: EditPreview
}

export function DataEditor({ api }: { api: DataEditorApi }) {
  const [rows, setRows] = useState<RowsPreview | null>(null)
  const [history, setHistory] = useState<AppliedEdit[]>([])
  const [command, setCommand] = useState('')
  const [pending, setPending] = useState<PendingEdit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragged, setDragged] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setRows(await api.getRows())
    setHistory(await api.listEdits())
  }, [api])

  useEffect(() => {
    void refresh().catch((loadError: unknown) =>
      setError(errorDetail(loadError)),
    )
  }, [refresh])

  const preview = useCallback(
    async (text: string) => {
      setError(null)
      setBusy(true)
      try {
        setPending({ command: text, preview: await api.previewEdit(text) })
      } catch (previewError) {
        setPending(null)
        setError(errorDetail(previewError))
      } finally {
        setBusy(false)
      }
    },
    [api],
  )

  const apply = useCallback(async () => {
    if (!pending) return
    setError(null)
    setBusy(true)
    try {
      await api.applyEdit(pending.command)
      setPending(null)
      setCommand('')
      await refresh()
    } catch (applyError) {
      setError(errorDetail(applyError))
    } finally {
      setBusy(false)
    }
  }, [api, pending, refresh])

  const dropOn = (target: string) => {
    if (!dragged || !rows || dragged === target) {
      setDragged(null)
      return
    }
    const from = rows.columns.indexOf(dragged)
    const to = rows.columns.indexOf(target)
    const position = from < to ? 'after' : 'before'
    void preview(
      `move column ${quoteName(dragged)} ${position} ${quoteName(target)}`,
    )
    setDragged(null)
  }

  return (
    <section aria-labelledby="editor-heading">
      <h2 id="editor-heading">Edit data</h2>
      <p className="hint">
        A live preview of your table with every applied edit. Drag a column
        header onto another column to move it, or type a command below. Each
        change shows a preview first and applies only when you approve it —
        your original file is never modified.
      </p>
      {error && <p role="alert">{error}</p>}
      {rows && (
        <>
          <p>
            {rows.total_rows.toLocaleString()} rows · showing the first{' '}
            {Math.min(GRID_ROWS, rows.rows.length)}
          </p>
          <div className="data-grid-wrap">
            <table className="data-grid" aria-label="Data preview">
              <thead>
                <tr>
                  {rows.columns.map((name) => (
                    <th
                      key={name}
                      scope="col"
                      draggable
                      aria-label={`Column ${name} (drag onto another column to move it)`}
                      className={dragged === name ? 'dragging' : undefined}
                      onDragStart={() => setDragged(name)}
                      onDragEnd={() => setDragged(null)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => dropOn(name)}
                    >
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.rows.slice(0, GRID_ROWS).map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((value, columnIndex) => (
                      <td key={columnIndex}>{value === null ? '∅' : value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <form
        className="command-row"
        onSubmit={(event) => {
          event.preventDefault()
          if (command.trim()) void preview(command.trim())
        }}
      >
        <label htmlFor="edit-command">Command</label>
        <input
          id="edit-command"
          type="text"
          list="edit-command-examples"
          placeholder="e.g. rename column customer_id to customer"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
        />
        <datalist id="edit-command-examples">
          {COMMAND_EXAMPLES.map((example) => (
            <option key={example} value={example} />
          ))}
        </datalist>
        <button type="submit" disabled={busy || !command.trim()}>
          Preview edit
        </button>
      </form>
      <details>
        <summary>Supported commands</summary>
        <ul>
          {COMMAND_EXAMPLES.map((example) => (
            <li key={example}>
              <code>{example}</code>
            </li>
          ))}
        </ul>
      </details>
      {pending && (
        <article aria-label="Edit preview" className="edit-preview">
          <h3>
            Preview: <code>{pending.command}</code>
          </h3>
          <p>
            {pending.preview.affected_row_count.toLocaleString()} values would
            change · columns after: {pending.preview.columns_after.join(', ')}
          </p>
          {pending.preview.samples.length > 0 && (
            <table>
              <caption>Sample changes</caption>
              <thead>
                <tr>
                  <th scope="col">Before</th>
                  <th scope="col">After</th>
                </tr>
              </thead>
              <tbody>
                {pending.preview.samples.slice(0, 8).map((sample, index) => (
                  <tr key={index}>
                    <td>{sample.before ?? '∅'}</td>
                    <td>{sample.after ?? '∅'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" onClick={() => setPending(null)}>
            Cancel
          </button>
          <button type="button" disabled={busy} onClick={() => void apply()}>
            Apply edit
          </button>
        </article>
      )}
      {history.length > 0 && (
        <details open>
          <summary>Applied edits ({history.length})</summary>
          <ol>
            {history.map((edit) => (
              <li key={edit.sequence}>
                {describeCommand(edit.command)} ·{' '}
                {edit.row_count.toLocaleString()} rows
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  )
}
