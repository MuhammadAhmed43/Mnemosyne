import { useEffect, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { MemoryNode } from "~lib/types"

import { MemoryNodeCard } from "./MemoryNodeCard"
import { NoMemories } from "./EmptyStates"

const TYPE_ORDER = ["goal", "decision", "problem", "technical_fact", "event", "preference", "entity", "task"]
const TYPE_LABELS: Record<string, string> = {
  goal: "Goals", decision: "Decisions", problem: "Open Problems", technical_fact: "Tech Stack",
  event: "Events", preference: "Preferences", entity: "People & Tools", task: "Tasks",
}

export function MemoryTab({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [nodes, setNodes] = useState<MemoryNode[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.listNodes(workspaceId, { status: "active" }).then((r) => {
      setNodes(r.nodes)
      setLoading(false)
    })
  }, [api, workspaceId])

  if (loading) return <p className="p-md font-body-sm text-body-sm text-on-surface-variant">Loading…</p>
  if (nodes.length === 0) return <NoMemories />

  const grouped = nodes.reduce<Record<string, MemoryNode[]>>((acc, n) => {
    ;(acc[n.node_type] ??= []).push(n)
    return acc
  }, {})

  return (
    <div className="space-y-lg p-md">
      {TYPE_ORDER.filter((t) => grouped[t]).map((t) => (
        <section key={t}>
          <h3 className="mb-sm font-label-caps text-label-caps uppercase text-on-surface-variant">
            {TYPE_LABELS[t]} ({grouped[t].length})
          </h3>
          <div className="space-y-xs">
            {grouped[t].map((n) => (
              <MemoryNodeCard key={n.id} node={n} compact />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
