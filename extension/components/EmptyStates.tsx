import type { ReactNode } from "react"

interface EmptyProps {
  icon: string
  title: string
  description: string
  children?: ReactNode
}

export function EmptyState({ icon, title, description, children }: EmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-8 text-center">
      {icon
        ? <div className="text-3xl text-text-tertiary">{icon}</div>
        : <div className="h-10 w-10 rounded-full border-2 border-accent/40 bg-accent/10" />}
      <h3 className="text-base font-semibold text-text-primary">{title}</h3>
      <p className="max-w-xs text-sm text-text-secondary">{description}</p>
      {children}
    </div>
  )
}

export const NoMemories = () => (
  <EmptyState icon="" title="Your knowledge graph starts here." description="Mnemosyne extracts structure automatically as you talk to your AI." />
)

export const NothingToReview = () => (
  <EmptyState icon="✓" title="Nothing to review" description="Everything extracted so far was high-confidence and committed automatically." />
)

export const EngineOffline = ({ onRestart }: { onRestart?: () => void }) => (
  <EmptyState icon="⚠" title="Mnemosyne engine is not running." description="Your browser still works normally. No capture or injection is active.">
    {onRestart && (
      <button className="rounded-lg bg-accent px-4 py-2 text-sm text-white" onClick={onRestart}>
        Restart Engine
      </button>
    )}
  </EmptyState>
)
