import type { PendingItem } from "~lib/types"

import { NodeTypeBadge } from "./NodeTypeBadge"

interface Props {
  item: PendingItem
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

export function PendingReviewCard({ item, onApprove, onReject }: Props) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-3">
      <div className="mb-1 flex items-center justify-between">
        <NodeTypeBadge type={item.candidate_type} />
        <span className="text-[11px] text-text-secondary">
          {Math.round(item.candidate_confidence * 100)}% · {item.source_platform}
        </span>
      </div>
      <p className="mb-2 text-sm text-text-primary">{item.candidate_content}</p>
      {item.source_context && (
        <p className="mb-2 border-l-2 border-border pl-2 text-xs italic text-text-secondary">
          "{item.source_context}"
        </p>
      )}
      <div className="flex gap-2">
        <button className="rounded bg-success px-3 py-1 text-xs font-medium text-white" onClick={() => onApprove(item.id)}>
          Approve
        </button>
        <button className="rounded border border-border px-3 py-1 text-xs text-text-secondary hover:text-danger" onClick={() => onReject(item.id)}>
          Reject
        </button>
      </div>
    </div>
  )
}
