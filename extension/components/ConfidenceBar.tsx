export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-sm">
      <div className="h-1 w-16 overflow-hidden rounded-full bg-surface-container-highest">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-code-md text-[11px] text-primary">{pct}%</span>
    </div>
  )
}
