const COLORS: Record<string, string> = {
  goal: "#34D399",
  decision: "#818CF8",
  task: "#60A5FA",
  problem: "#FB7185",
  entity: "#FBBF24",
  preference: "#F472B6",
  technical_fact: "#94A3B8",
  event: "#2DD4BF",
  insight: "#A78BFA",
  user_note: "#38BDF8",
  open_question: "#FB923C",
  hypothesis: "#C084FC",
  constraint: "#F87171",
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
