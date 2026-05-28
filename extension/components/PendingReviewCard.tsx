import type { PendingItem } from "~lib/types"

import { NodeTypeBadge } from "./NodeTypeBadge"

interface Props {
  item: PendingItem
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

export function PendingReviewCard({ item, onApprove, onReject }: Props) {
  return (
    <div className="space-y-sm border border-outline-variant bg-surface-container p-sm">
      <div className="flex items-center justify-between">
        <NodeTypeBadge type={item.candidate_type} />
        <span className="font-code-md text-[10px] text-on-surface-variant">
          {Math.round(item.candidate_confidence * 100)}% · {item.source_platform}
        </span>
      </div>
      <p className="font-body-sm text-body-sm text-on-surface">{item.candidate_content}</p>
      {item.source_context && (
        <p className="border-l-2 border-outline-variant pl-sm font-body-sm text-body-sm italic text-on-surface-variant">
          "{item.source_context}"
        </p>
      )}
      <div className="flex gap-xs">
        <button
          className="flex-1 bg-primary py-1 font-label-caps text-[9px] uppercase text-on-primary transition-opacity hover:opacity-90"
          onClick={() => onApprove(item.id)}>
          Approve
        </button>
        <button
          className="flex-1 border border-outline-variant py-1 font-label-caps text-[9px] uppercase text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={() => onReject(item.id)}>
          Reject
        </button>
      </div>
    </div>
  )
}
