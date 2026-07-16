import { useCallback, useRef, useState } from 'react'
import { ApiClient } from '../api/client'
import type {
  OutputManifest,
  RecipeStep,
  SavedProfile,
  SessionManifest,
} from '../api/types'
import { DictionaryEditor } from '../features/dictionary/DictionaryEditor'
import { IssueList } from '../features/issues/IssueList'
import { Overview } from '../features/overview/Overview'
import type { ExecutionView } from '../features/outputs/OutputPanel'
import { OutputPanel } from '../features/outputs/OutputPanel'
import { RecipeEditor } from '../features/recipe/RecipeEditor'
import { UploadPanel } from '../features/upload/UploadPanel'

const POLL_INTERVAL_MS = 250

type Phase =
  | { kind: 'idle' }
  | { kind: 'profiling'; jobId: string }
  | { kind: 'profiled'; saved: SavedProfile }
  | { kind: 'failed'; code: string }

function readToken(): string {
  // The launcher passes the token in the fragment so it never reaches server
  // logs; read it once, strip it from the address bar and history, and keep
  // it in per-tab sessionStorage so a refresh does not lose the session.
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const fromFragment = fragment.get('token')
  if (fromFragment) {
    sessionStorage.setItem('workbench-token', fromFragment)
    history.replaceState(null, '', window.location.pathname)
    return fromFragment
  }
  const stored = sessionStorage.getItem('workbench-token')
  if (stored) return stored
  return new URLSearchParams(window.location.search).get('token') ?? ''
}

export function App({ api: injectedApi }: { api?: ApiClient }) {
  // Create the client exactly once: readToken() strips the URL fragment on
  // first read, so re-evaluating a default parameter on re-render would
  // produce token-less clients for every later request.
  const [boot] = useState(() => {
    if (injectedApi) return { api: injectedApi, missingToken: false }
    const token = readToken()
    return { api: new ApiClient('', token), missingToken: token === '' }
  })
  const api = boot.api
  const [session, setSession] = useState<SessionManifest | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [steps, setSteps] = useState<RecipeStep[]>([])
  const [execution, setExecution] = useState<ExecutionView>({ state: 'idle' })
  const [executionJobId, setExecutionJobId] = useState<string | null>(null)
  const [manifest, setManifest] = useState<OutputManifest | null>(null)
  const cancelled = useRef(false)

  const execute = useCallback(async () => {
    if (!session) return
    setManifest(null)
    setExecution({ state: 'running', message: 'Executing recipe…' })
    try {
      const { job_id } = await api.executeRecipe(
        session.id,
        {
          recipe_version: 1,
          source_fingerprint: session.sha256,
          steps,
        },
        'parquet',
      )
      setExecutionJobId(job_id)
      for (;;) {
        const job = await api.getJob(job_id)
        if (job.state === 'succeeded') {
          setManifest(await api.buildArtifacts(session.id))
          setExecution({ state: 'idle' })
          return
        }
        if (job.state === 'failed' || job.state === 'cancelled') {
          setExecution({
            state: job.state,
            errorCode: job.error_code ?? undefined,
          })
          return
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
      }
    } catch {
      setExecution({ state: 'failed', errorCode: 'execution_failed' })
    }
  }, [api, session, steps])

  const previewWith = useCallback(
    (candidate: RecipeStep) => {
      if (!session) return Promise.reject(new Error('no session'))
      return api.previewRecipe(session.id, {
        recipe_version: 1,
        source_fingerprint: session.sha256,
        steps: [...steps, candidate],
      })
    },
    [api, session, steps],
  )

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
      <p className="tagline">
        Upload a dataset, review detected issues, approve fixes with a
        before/after preview, and download the cleaned result. Everything
        stays on this machine; your original file is never modified.
      </p>
      {boot.missingToken && (
        <section role="alert">
          <p>
            No session token — this tab cannot talk to the workbench. Open
            the address printed by the launcher (it ends in{' '}
            <code>#token=…</code>), or append <code>?token=…</code> to the
            URL, then reload.
          </p>
        </section>
      )}
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
        <>
          <Overview
            profile={phase.saved.profile}
            findingCount={phase.saved.findings.length}
          />
          <IssueList
            findings={phase.saved.findings}
            onPreview={previewWith}
            onApprove={(step) => setSteps((current) => [...current, step])}
          />
          <RecipeEditor steps={steps} onChange={setSteps} />
          {session && (
            <>
              <DictionaryEditor
                columns={phase.saved.profile.columns}
                descriptions={{}}
                onSave={(descriptions) =>
                  void api.saveDictionary(session.id, descriptions)
                }
                api={{
                  previewAi: (selected) =>
                    api.previewAiDictionary(session.id, selected),
                  approveAi: (previewId) =>
                    api.approveAiDictionary(session.id, previewId),
                }}
              />
              <OutputPanel
                execution={execution}
                manifest={manifest}
                onExecute={() => void execute()}
                onCancel={() =>
                  executionJobId && void api.cancelJob(executionJobId)
                }
                onDownload={(artifactId) =>
                  void api.downloadArtifact(session.id, artifactId)
                }
              />
            </>
          )}
        </>
      )}
    </main>
  )
}

export default App
