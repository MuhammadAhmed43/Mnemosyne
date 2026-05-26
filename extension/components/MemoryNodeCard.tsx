import type { MemoryNode } from "~lib/types"

import { ConfidenceBar } from "./ConfidenceBar"
import { NodeTypeBadge } from "./NodeTypeBadge"

interface Props {
  node: MemoryNode
  compact?: boolean
  onEdit?: (id: string) => void
  onBoost?: (id: string) => void
  onDelete?: (id: string) => void
  onMove?: (id: string) => void
}

export function MemoryNodeCard({ node, compact, onEdit, onBoost, onDelete, onMove }: Props) {
  // Idea nodes are auto-captured when the user drills into a concept while
  // brainstorming (vs. stated decisions/facts) — flag them so they're easy to spot.
  const isIdea = node.structured_data?.kind === "idea"
  const isManualNote = node.structured_data?.source === "manual_selection"
  return (
    <div className="group rounded-lg border border-border bg-bg-secondary p-3 transition hover:bg-bg-hover">
      <div className="mb-1 flex items-center gap-2">
        <NodeTypeBadge type={node.node_type} />
        {isIdea && (
          <span title="Captured from an idea/brainstorming chat" className="rounded-full bg-[#A855F722] px-2 py-0.5 text-[11px] font-medium text-[#C084FC]">
            💡 Idea
          </span>
        )}
        {isManualNote && (
          <span title="Saved via right-click → Save selection" className="rounded-full bg-[#22D3EE22] px-2 py-0.5 text-[11px] font-medium text-[#22D3EE]">
            ✎ Saved
          </span>
        )}
        {node.user_verified && <span title="Verified" className="text-success">✓</span>}
        {node.is_permanent && <span title="Permanent">🔒</span>}
        {node.version > 1 && <span className="text-[11px] text-text-tertiary">v{node.version}</span>}
      </div>
      <p className="text-sm text-text-primary">{node.content}</p>
      {!compact && (
        <div className="mt-2 flex items-center justify-between">
          <ConfidenceBar value={node.extraction_confidence} />
          {/* opacity (not display:none) keeps actions in the tab order; revealed on
              hover OR keyboard focus so they're reachable without a mouse. */}
          <div className="flex gap-3 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
            {onEdit && <button aria-label="Edit memory" className="text-xs text-text-secondary hover:text-accent" onClick={() => onEdit(node.id)}>Edit</button>}
            {onBoost && <button aria-label="Boost importance" className="text-xs text-text-secondary hover:text-accent" onClick={() => onBoost(node.id)}>Boost</button>}
            {onMove && <button aria-label="Move to another workspace" className="text-xs text-text-secondary hover:text-accent" onClick={() => onMove(node.id)}>Move</button>}
            {onDelete && <button aria-label="Delete memory" className="text-xs text-text-secondary hover:text-danger" onClick={() => onDelete(node.id)}>Delete</button>}
          </div>
        </div>
      )}
    </div>
  )
}
