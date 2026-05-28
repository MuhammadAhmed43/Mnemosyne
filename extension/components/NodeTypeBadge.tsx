// Tailwind 500-shade palette — saturated enough to read with depth against the
// obsidian-bg canvas, but not so loud they overpower the rest of the UI.
export const NODE_COLORS: Record<string, string> = {
  goal: "#10B981",          // emerald-500
  decision: "#6366F1",      // indigo-500
  task: "#3B82F6",          // blue-500
  problem: "#EF4444",       // red-500
  entity: "#F59E0B",        // amber-500
  preference: "#EC4899",    // pink-500
  technical_fact: "#64748B",// slate-500
  event: "#14B8A6",         // teal-500
  insight: "#8B5CF6",       // violet-500
  user_note: "#0EA5E9",     // sky-500
  open_question: "#F97316", // orange-500
  hypothesis: "#A855F7",    // purple-500
  constraint: "#DC2626",    // red-600
}

export const NODE_LABELS: Record<string, string> = {
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

export function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? "#918f9f"
}

export function nodeLabel(type: string): string {
  return NODE_LABELS[type] ?? type
}

/** Stitch "memory type" badge: rectangular, color-coded left border, tinted bg, mono. */
export function NodeTypeBadge({ type }: { type: string }) {
  const color = nodeColor(type)
  return (
    <span
      className="inline-flex items-center border-l-2 px-2 py-0.5 font-code-md text-[10px] uppercase tracking-wider"
      style={{ borderColor: color, color, backgroundColor: `${color}1a` }}>
      {nodeLabel(type)}
    </span>
  )
}
