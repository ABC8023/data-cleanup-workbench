import { useState } from 'react'
import type { DuplicateDecision, DuplicateGroup } from '../../api/types'

const ACTIONS = ['keep_separate', 'remove_record', 'merge_fields'] as const

interface DuplicateReviewProps {
  group: DuplicateGroup
  onDecision: (decision: DuplicateDecision) => void
}

export function DuplicateReview({ group, onDecision }: DuplicateReviewProps) {
  const [action, setAction] = useState<DuplicateDecision['action'] | ''>('')
  const [survivor, setSurvivor] = useState<string | null>(null)
  const needsSurvivor = action === 'remove_record' || action === 'merge_fields'
  const ready = action !== '' && (!needsSurvivor || survivor !== null)

  return (
    <fieldset>
      <legend>Duplicate group {group.id}</legend>
      <p>{Math.round(group.confidence * 100)}% confidence</p>
      <ul>
        {group.row_ids.map((rowId, index) => (
          <li key={rowId}>
            Row {rowId}: {group.display_values[index]}
          </li>
        ))}
      </ul>
      <dl>
        {Object.entries(group.evidence).map(([field, score]) => (
          <div key={field}>
            <dt>{field}</dt>
            <dd>{Math.round(score * 100)}% match</dd>
          </div>
        ))}
      </dl>
      {ACTIONS.map((value) => (
        <label key={value}>
          <input
            type="radio"
            name={`action-${group.id}`}
            checked={action === value}
            onChange={() => setAction(value)}
          />
          {value.replace(/_/g, ' ')}
        </label>
      ))}
      {needsSurvivor && (
        <fieldset>
          <legend>Keep which record?</legend>
          {group.row_ids.map((rowId) => (
            <label key={rowId}>
              <input
                type="radio"
                name={`survivor-${group.id}`}
                checked={survivor === rowId}
                onChange={() => setSurvivor(rowId)}
              />
              Row {rowId}
            </label>
          ))}
        </fieldset>
      )}
      <button
        type="button"
        disabled={!ready}
        onClick={() =>
          action !== '' &&
          onDecision({
            action,
            survivor_row_id: needsSurvivor ? survivor : null,
          })
        }
      >
        Save decision
      </button>
    </fieldset>
  )
}
