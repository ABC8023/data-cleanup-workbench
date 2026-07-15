import type { RecipeStep } from '../../api/types'

interface RecipeEditorProps {
  steps: RecipeStep[]
  onChange: (steps: RecipeStep[]) => void
}

export function RecipeEditor({ steps, onChange }: RecipeEditorProps) {
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= steps.length) return
    const next = [...steps]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  const remove = (index: number) => {
    onChange(steps.filter((_, position) => position !== index))
  }

  return (
    <section aria-labelledby="recipe-heading">
      <h2 id="recipe-heading">Recipe</h2>
      {steps.length === 0 && <p>No approved steps yet.</p>}
      <ol>
        {steps.map((step, index) => (
          <li key={step.id}>
            <span>
              {step.operation.replace(/_/g, ' ')} — {step.columns.join(', ')}
            </span>
            <button
              type="button"
              aria-label={`Move ${step.id} up`}
              disabled={index === 0}
              onClick={() => move(index, -1)}
            >
              Move up
            </button>
            <button
              type="button"
              aria-label={`Move ${step.id} down`}
              disabled={index === steps.length - 1}
              onClick={() => move(index, 1)}
            >
              Move down
            </button>
            <button
              type="button"
              aria-label={`Remove ${step.id}`}
              onClick={() => remove(index)}
            >
              Remove
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}
