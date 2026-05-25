import { useEffect, useState } from "react"

import { NodeTypeBadge } from "~components/NodeTypeBadge"
import type { MnemosyneAPI } from "~lib/api"
import type { MemoryNode } from "~lib/types"

export function Overview({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [nodes, setNodes] = useState<MemoryNode[]>([])
  const [health, setHealth] = useState<number | null>(null)

  useEffect(() => {
    api.listNodes(workspaceId, { status: "active" }).then((r) => setNodes(r.nodes))
    api.getHealth(workspaceId).then((h) => setHealth(h.memory_health_score))
  }, [api, workspaceId])

  const byType = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.node_type] = (acc[n.node_type] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="max-w-4xl p-8">
      <h1 className="mb-6 text-2xl font-bold">Overview</h1>
      <div className="mb-8 grid grid-cols-3 gap-4">
        <Card label="Memory Health" value={health !== null ? `${Math.round(health * 100)}%` : "…"} />
        <Card label="Active Memories" value={nodes.length} />
        <Card label="Types" value={Object.keys(byType).length} />
      </div>
      <div className="rounded-lg border border-border bg-bg-secondary p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase text-text-secondary">Memory Breakdown</h2>
        {Object.entries(byType).map(([type, count]) => (
          <div key={type} className="flex items-center justify-between py-1.5 text-sm">
            <NodeTypeBadge type={type} />
            <span className="text-text-secondary">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Card({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-4">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  )
}
