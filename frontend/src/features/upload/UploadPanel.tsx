import { useState } from 'react'
import type { SessionManifest } from '../../api/types'

export interface UploadApi {
  upload(file: File, onProgress: (ratio: number) => void): Promise<SessionManifest>
}

interface UploadPanelProps {
  api: UploadApi
  onSession: (session: SessionManifest) => void
}

export function UploadPanel({ api, onSession }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = async () => {
    if (!file) return
    setError(null)
    setProgress(0)
    try {
      const session = await api.upload(file, setProgress)
      onSession(session)
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'upload failed')
    } finally {
      setProgress(null)
    }
  }

  return (
    <section aria-labelledby="upload-heading">
      <h2 id="upload-heading">Upload</h2>
      <p className="hint">
        Pick a CSV, Excel (.xlsx), JSON, NDJSON, or Parquet file up to 5 GB,
        then start profiling. A read-only copy is staged for analysis.
      </p>
      <label>
        Choose dataset
        <input
          type="file"
          accept=".csv,.json,.ndjson,.parquet,.xlsx"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <button type="button" disabled={!file || progress !== null} onClick={start}>
        Profile dataset
      </button>
      {progress !== null && (
        <progress aria-label="Upload progress" value={progress} max={1} />
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
