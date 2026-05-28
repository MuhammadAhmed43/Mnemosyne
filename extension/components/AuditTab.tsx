import { useEffect, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { PendingItem } from "~lib/types"

import { NothingToReview } from "./EmptyStates"
import { PendingReviewCard } from "./PendingReviewCard"

export function AuditTab({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [items, setItems] = useState<PendingItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.getPending(workspaceId).then((r) => {
      setItems(r.items)
      setLoading(false)
    })
  }
  useEffect(load, [api, workspaceId])

  const approve = async (id: string) => {
    await api.approvePending(workspaceId, id)
    setItems((prev) => prev.filter((i) => i.id !== id))
  }
  const reject = async (id: string) => {
    await api.rejectPending(workspaceId, id)
    setItems((prev) => prev.filter((i) => i.id !== id))
  }
  const rejectAll = async () => {
    if (!confirm(`Reject all ${items.length} pending items? This can't be undone.`)) return
    await api.rejectAllPending(workspaceId)
    setItems([])
  }

  if (loading) return <p className="p-md font-body-sm text-body-sm text-on-surface-variant">Loading…</p>
  if (items.length === 0) return <NothingToReview />

  return (
    <div className="space-y-gutter p-md">
      <div className="flex items-center justify-between">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface">
          Pending Review ({items.length})
        </h3>
        <button
          onClick={rejectAll}
          className="border border-error/30 px-sm py-xs font-label-caps text-[10px] uppercase text-error transition-colors hover:bg-error/10">
          Reject all
        </button>
      </div>
      {items.map((item) => (
        <PendingReviewCard key={item.id} item={item} onApprove={approve} onReject={reject} />
      ))}
    </div>
  )
}
