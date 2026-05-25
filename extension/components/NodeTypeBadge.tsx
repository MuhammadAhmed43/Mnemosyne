const COLORS: Record<string, string> = {
  goal: "#10B981",
  decision: "#7C3AED",
  task: "#3B82F6",
  problem: "#EF4444",
  entity: "#F59E0B",
  preference: "#EC4899",
  technical_fact: "#6B7280",
  event: "#14B8A6",
  insight: "#A855F7",
  user_note: "#22D3EE",
  open_question: "#F97316",
  hypothesis: "#8B5CF6",
  constraint: "#DC2626",
}

const LABELS: Record<string, string> = {
  goal: "Goal",
  decision: "Decision",
  task: "Task",
  problem: "Problem",
  entity: "Entity",
  preference: "Preference",
  technical_fact: "Tech",
  event: "Event",
  insight: "Insight",
  user_note: "Note",
  open_question: "Question",
  hypothesis: "Hypothesis",
  constraint: "Constraint",
}

export function NodeTypeBadge({ type }: { type: string }) {
  const color = COLORS[type] ?? "#6B7280"
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ backgroundColor: `${color}22`, color }}
    >
      {LABELS[type] ?? type}
    </span>
  )
}
