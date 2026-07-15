interface ErrorStateProps {
  stage: string
  code: string
  actionLabel: string
  onAction: () => void
}

export function ErrorState({ stage, code, actionLabel, onAction }: ErrorStateProps) {
  return (
    <section role="alert">
      <p>
        {stage} failed ({code.replace(/_/g, ' ')}).
      </p>
      <button type="button" onClick={onAction}>
        {actionLabel}
      </button>
    </section>
  )
}
