import { useCallback, useRef, useState } from 'react'
import { ApiClient } from '../api/client'
import type { SavedProfile, SessionManifest } from '../api/types'
import { Overview } from '../features/overview/Overview'
import { UploadPanel } from '../features/upload/UploadPanel'

const POLL_INTERVAL_MS = 250

type Phase =
  | { kind: 'idle' }
  | { kind: 'profiling'; jobId: string }
  | { kind: 'profiled'; saved: SavedProfile }
  | { kind: 'failed'; code: string }

function defaultClient(): ApiClient {
  const token = new URLSearchParams(window.location.search).get('token') ?? ''
  return new ApiClient('', token)
}

export function App({ api = defaultClient() }: { api?: ApiClient }) {
  const [session, setSession] = useState<SessionManifest | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const cancelled = useRef(false)

  const profile = useCallback(
    async (target: SessionManifest) => {
      cancelled.current = false
      const { job_id } = await api.startProfile(target.id)
      setPhase({ kind: 'profiling', jobId: job_id })
      for (;;) {
        const job = await api.getJob(job_id)
        if (job.state === 'succeeded') {
          setPhase({ kind: 'profiled', saved: await api.getProfile(target.id) })
          return
        }
        if (job.state === 'failed' || job.state === 'cancelled') {
          setPhase({ kind: 'failed', code: job.error_code ?? job.state })
          return
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
      }
    },
    [api],
  )

  const onSession = useCallback(
    (staged: SessionManifest) => {
      setSession(staged)
      void profile(staged).catch(() =>
        setPhase({ kind: 'failed', code: 'profile_failed' }),
      )
    },
    [profile],
  )

  return (
    <main>
      <h1>Data Cleanup Workbench</h1>
      <UploadPanel api={api} onSession={onSession} />
      {phase.kind === 'profiling' && (
        <section aria-live="polite">
          <p>Profiling {session?.filename}…</p>
          <button type="button" onClick={() => void api.cancelJob(phase.jobId)}>
            Cancel profiling
          </button>
        </section>
      )}
      {phase.kind === 'failed' && (
        <section role="alert">
          <p>Profiling failed ({phase.code}).</p>
          {session && (
            <button type="button" onClick={() => void profile(session)}>
              Retry profiling
            </button>
          )}
        </section>
      )}
      {phase.kind === 'profiled' && (
        <Overview
          profile={phase.saved.profile}
          findingCount={phase.saved.findings.length}
        />
      )}
    </main>
  )
}

export default App
