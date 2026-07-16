import type { Finding, RecipeStep } from '../../api/types'

export function suggestStep(finding: Finding): RecipeStep | null {
  const operation = finding.suggested_operation?.operation
  if (!operation) return null
  const base = {
    id: `${finding.rule_id}:${finding.columns.join('+')}`,
    columns: finding.columns,
    on_error: 'preserve' as const,
  }
  switch (operation) {
    case 'parse_date':
      return {
        ...base,
        operation,
        formats: ['%Y-%m-%d', '%d/%m/%Y'],
        output_format: '%Y-%m-%d',
      }
    case 'cast_number':
      return { ...base, operation, target: 'decimal' }
    case 'replace_value':
      return {
        ...base,
        operation,
        old: finding.examples[0]?.value ?? '',
        new: null,
      }
    case 'trim_whitespace':
      return { ...base, operation: 'normalize_text', trim: true, case: 'preserve' }
    case 'set_case':
      return { ...base, operation: 'normalize_text', trim: true, case: 'upper' }
    default:
      return null
  }
}
