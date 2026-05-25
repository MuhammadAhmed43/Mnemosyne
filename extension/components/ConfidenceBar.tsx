export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value > 0.8 ? "#10B981" : value >= 0.6 ? "#F59E0B" : "#EF4444"
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-bg-tertiary">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-[11px] text-text-secondary">{pct}%</span>
    </div>
  )
}
