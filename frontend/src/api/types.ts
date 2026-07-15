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
  suggested_operation: { operation: string } | null
  evidence: Record<string, string | number>
}

export type RecipeStep = {
  id: string
  operation: string
  columns: string[]
  on_error: 'preserve' | 'set_null' | 'quarantine'
} & Record<string, unknown>

export interface Recipe {
  recipe_version: 1
  source_fingerprint: string
  steps: RecipeStep[]
}

export interface PreviewResult {
  before_rows: Record<string, unknown>[]
  after_rows: Record<string, unknown>[]
  schema_before: Record<string, string>
  schema_after: Record<string, string>
  null_deltas: Record<string, number>
  row_count_delta: number
  validation_failures: string[]
}

export interface DuplicateGroup {
  id: string
  row_ids: string[]
  display_values: string[]
  confidence: number
  evidence: Record<string, number>
}

export interface DuplicateDecision {
  action: 'keep_separate' | 'remove_record' | 'merge_fields'
  survivor_row_id: string | null
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
