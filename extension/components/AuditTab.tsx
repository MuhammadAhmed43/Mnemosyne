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

  if (loading) return <p className="p-4 text-sm text-text-secondary">Loading…</p>
  if (items.length === 0) return <NothingToReview />

  return (
    <div className="space-y-3 p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase text-text-secondary">
          Pending Review ({items.length})
        </h3>
        <button
          onClick={rejectAll}
          className="rounded border border-danger px-2 py-1 text-xs text-danger hover:bg-danger hover:text-white"
        >
          Reject all
        </button>
      </div>
      {items.map((item) => (
        <PendingReviewCard key={item.id} item={item} onApprove={approve} onReject={reject} />
      ))}
    </div>
  )
}
