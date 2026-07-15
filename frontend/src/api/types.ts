export interface SessionManifest {
  id: string
  filename: string
  size_bytes: number
  sha256: string
  state: 'staged' | 'profiled' | 'executed'
}

export interface ColumnProfile {
  name: string
  inferred_type: string
  null_count: number
  distinct_count: number
  min_value: string | null
  max_value: string | null
  examples: string[]
  top_values: [string, number][]
}

export interface DatasetProfile {
  source_fingerprint: string
  table: string
  row_count: number
  columns: ColumnProfile[]
  sampled: boolean
}

export interface Finding {
  id: string
  rule_id: string
  severity: number
  columns: string[]
  affected_row_count: number
  affected_ratio: number
  confidence: number
  risk_level: 'safe' | 'review_required' | 'informational'
  examples: Record<string, string>[]
}

export interface SavedProfile {
  profile: DatasetProfile
  findings: Finding[]
}

export interface JobStatus {
  id: string
  kind: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  error_code: string | null
}
