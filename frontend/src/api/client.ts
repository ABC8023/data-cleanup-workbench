import type { JobStatus, SavedProfile, SessionManifest } from './types'

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
}
