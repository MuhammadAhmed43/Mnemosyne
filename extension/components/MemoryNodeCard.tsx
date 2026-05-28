import type { MemoryNode } from "~lib/types"

import { NodeTypeBadge } from "./NodeTypeBadge"

interface Props {
  node: MemoryNode
  compact?: boolean
  onEdit?: (id: string) => void
  onBoost?: (id: string) => void
  onDelete?: (id: string) => void
  onMove?: (id: string) => void
}

function shortId(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, "").slice(-4).toUpperCase()
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

export function MemoryNodeCard({ node, compact, onEdit, onBoost, onDelete, onMove }: Props) {
  const isIdea = node.structured_data?.kind === "idea"
  const isManualNote = node.structured_data?.source === "manual_selection"
  const conf = Math.round((node.extraction_confidence ?? 0) * 100)

  return (
    <div className="group relative flex flex-col gap-sm border border-outline-variant bg-surface-container-low p-md transition-all duration-200 hover:border-outline">
      <div className="flex items-start justify-between">
        <div className="flex flex-wrap items-center gap-sm">
          <NodeTypeBadge type={node.node_type} />
          {isIdea && (
            <span title="Captured from a brainstorming chat" className="border-l-2 border-[#C084FC] bg-[#C084FC1a] px-2 py-0.5 font-code-md text-[10px] uppercase tracking-wider text-[#C084FC]">
              Idea
            </span>
          )}
          {isManualNote && (
            <span title="Saved via right-click → Save selection" className="border-l-2 border-[#22D3EE] bg-[#22D3EE1a] px-2 py-0.5 font-code-md text-[10px] uppercase tracking-wider text-[#22D3EE]">
              Saved
            </span>
          )}
          <span className="font-body-sm text-body-sm tracking-tight text-outline">
            Node: #{shortId(node.id)} • {relativeTime(node.created_at)}
            {node.user_verified && " • verified"}
            {node.is_permanent && " • pinned"}
            {node.version > 1 && ` • v${node.version}`}
          </span>
        </div>
        {!compact && (
          <div className="flex items-center gap-base opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
            {onEdit && (
              <button aria-label="Edit memory" title="Edit" onClick={() => onEdit(node.id)} className="p-1 text-on-surface-variant hover:bg-surface-container-highest">
                <span className="material-symbols-outlined !text-[16px]">edit</span>
              </button>
            )}
            {onBoost && (
              <button aria-label="Boost importance" title="Boost confidence" onClick={() => onBoost(node.id)} className="p-1 text-primary hover:bg-surface-container-highest">
                <span className="material-symbols-outlined !text-[16px]">rocket_launch</span>
              </button>
            )}
            {onMove && (
              <button aria-label="Move to another workspace" title="Move" onClick={() => onMove(node.id)} className="p-1 text-on-surface-variant hover:bg-surface-container-highest">
                <span className="material-symbols-outlined !text-[16px]">drive_file_move</span>
              </button>
            )}
            {onDelete && (
              <button aria-label="Delete memory" title="Delete" onClick={() => onDelete(node.id)} className="p-1 text-error hover:bg-error/20">
                <span className="material-symbols-outlined !text-[16px]">delete</span>
              </button>
            )}
          </div>
        )}
      </div>

      <p className="font-body-md text-body-md text-on-surface">{node.content}</p>

      {!compact && (
        <div className="flex items-center gap-md">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-container-highest">
            <div className="h-full bg-primary" style={{ width: `${conf}%` }} />
          </div>
          <span className="font-code-md text-[11px] text-primary">{conf}% CONFIDENCE</span>
        </div>
      )}
    </div>
  )
}
