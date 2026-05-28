import type { ReactNode } from "react"

interface EmptyProps {
  icon: string
  title: string
  description: string
  children?: ReactNode
}

export function EmptyState({ icon, title, description, children }: EmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-md p-xl text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-dashed border-outline-variant">
        <span className="material-symbols-outlined text-[32px] text-outline-variant">{icon || "memory"}</span>
      </div>
      <h3 className="font-headline-md text-headline-md text-on-surface">{title}</h3>
      <p className="max-w-xs font-body-sm text-body-sm text-on-surface-variant">{description}</p>
      {children}
    </div>
  )
}

export const NoMemories = () => (
  <EmptyState icon="hub" title="Your knowledge graph starts here." description="Mnemosyne extracts structure automatically as you talk to your AI." />
)

export const NothingToReview = () => (
  <EmptyState icon="task_alt" title="Nothing to review" description="Everything extracted so far was high-confidence and committed automatically." />
)

export const EngineOffline = ({ onRestart }: { onRestart?: () => void }) => (
  <EmptyState icon="cloud_off" title="Mnemosyne engine is not running." description="Your browser still works normally. No capture or injection is active.">
    {onRestart && (
      <button
        className="rounded bg-primary px-md py-sm font-label-caps text-label-caps uppercase text-on-primary transition-opacity hover:opacity-90"
        onClick={onRestart}>
        Restart Engine
      </button>
    )}
  </EmptyState>
)
