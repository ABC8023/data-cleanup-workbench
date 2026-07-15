import type {
  AiAttempt,
  AiPayloadPreview,
  JobStatus,
  OutputManifest,
  PreviewResult,
  Recipe,
  SavedProfile,
  SessionManifest,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly token: string

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl
    this.token = token
  }

  upload(file: File, onProgress: (ratio: number) => void): Promise<SessionManifest> {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest()
      const url = `${this.baseUrl}/api/sessions?filename=${encodeURIComponent(file.name)}`
      request.open('POST', url)
      request.setRequestHeader('X-Session-Token', this.token)
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total)
      }
      request.onerror = () => reject(new ApiError(0, 'upload failed'))
      request.onload = () => {
        if (request.status < 300) {
          resolve(JSON.parse(request.responseText) as SessionManifest)
        } else {
          reject(new ApiError(request.status, request.responseText))
        }
      }
      // The File streams as the request body; never read it with FileReader.
      request.send(file)
    })
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        'X-Session-Token': this.token,
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
    if (!response.ok) {
      const body = await response.text()
      throw new ApiError(response.status, body)
    }
    return (await response.json()) as T
  }

  startProfile(sessionId: string): Promise<{ job_id: string }> {
    return this.request(`/api/sessions/${sessionId}/profile`, { method: 'POST' })
  }

  getJob(jobId: string): Promise<JobStatus> {
    return this.request(`/api/jobs/${jobId}`)
  }

  cancelJob(jobId: string): Promise<{ id: string; state: string }> {
    return this.request(`/api/jobs/${jobId}`, { method: 'DELETE' })
  }

  getProfile(sessionId: string): Promise<SavedProfile> {
    return this.request(`/api/sessions/${sessionId}/profile`)
  }

  previewRecipe(sessionId: string, recipe: Recipe): Promise<PreviewResult> {
    return this.request(`/api/sessions/${sessionId}/recipe/preview`, {
      method: 'POST',
      body: JSON.stringify({ recipe }),
    })
  }

  executeRecipe(
    sessionId: string,
    recipe: Recipe,
    outputFormat: 'csv' | 'parquet',
  ): Promise<{ job_id: string }> {
    return this.request(`/api/sessions/${sessionId}/recipe/execute`, {
      method: 'POST',
      body: JSON.stringify({
        recipe,
        output_format: outputFormat,
        approved: true,
      }),
    })
  }

  saveDictionary(
    sessionId: string,
    descriptions: Record<string, string>,
  ): Promise<Record<string, string>> {
    return this.request(`/api/sessions/${sessionId}/dictionary`, {
      method: 'PUT',
      body: JSON.stringify({ descriptions }),
    })
  }

  buildArtifacts(sessionId: string): Promise<OutputManifest> {
    return this.request(`/api/sessions/${sessionId}/artifacts`, {
      method: 'POST',
    })
  }

  previewAiDictionary(
    sessionId: string,
    selectedSamples: Record<string, string[]>,
  ): Promise<AiPayloadPreview> {
    return this.request(`/api/sessions/${sessionId}/ai/dictionary/preview`, {
      method: 'POST',
      body: JSON.stringify({ selected_samples: selectedSamples }),
    })
  }

  approveAiDictionary(sessionId: string, previewId: string): Promise<AiAttempt> {
    return this.request(`/api/sessions/${sessionId}/ai/dictionary/approve`, {
      method: 'POST',
      body: JSON.stringify({ preview_id: previewId }),
    })
  }

  async downloadArtifact(sessionId: string, artifactId: string): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/api/sessions/${sessionId}/artifacts/${artifactId}`,
      { headers: { 'X-Session-Token': this.token } },
    )
    if (!response.ok) throw new ApiError(response.status, await response.text())
    const disposition = response.headers.get('content-disposition') ?? ''
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? artifactId
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  }
}
