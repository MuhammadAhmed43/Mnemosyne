import { useEffect, useState } from "react"

import { MemoryNodeCard } from "~components/MemoryNodeCard"
import type { MnemosyneAPI } from "~lib/api"
import type { MemoryNode, Workspace } from "~lib/types"

// Order + labels for the quick-filter chip row. Only chips with a non-zero
// count are shown (plus "All"), so the row stays relevant to this workspace.
const CHIP_ORDER = [
  "all", "goal", "decision", "insight", "user_note", "problem",
  "task", "technical_fact", "entity", "preference", "event",
]
const CHIP_LABELS: Record<string, string> = {
  all: "All",
  goal: "Goals",
  decision: "Decisions",
  insight: "💡 Ideas",
  user_note: "✎ Notes",
  problem: "Problems",
  task: "Tasks",
  technical_fact: "Tech",
  entity: "Entities",
  preference: "Preferences",
  event: "Events",
}

export function MemoryBrowser({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [nodes, setNodes] = useState<MemoryNode[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [type, setType] = useState("all")
  const [search, setSearch] = useState("")
  const [movingId, setMovingId] = useState<string | null>(null)
  const [otherWs, setOtherWs] = useState<Workspace[]>([])

  // Counts are computed server-side (grouped query) so they're accurate no
  // matter how many nodes exist — not a capped client-side tally. They track
  // the active search too.
  const loadCounts = () => {
    api.nodeCounts(workspaceId, search || undefined).then((r) => setCounts({ all: r.total, ...r.counts }))
  }
  // The list itself is fetched server-side per selected type, so filtering a
  // type with thousands of nodes still returns that type's rows (not whatever
  // happened to be in the first page).
  const loadNodes = () => {
    api
      .listNodes(workspaceId, {
        type: type === "all" ? undefined : type,
        status: "active",
        search: search || undefined,
        limit: 500,
      })
      .then((r) => setNodes(r.nodes))
  }

  useEffect(loadCounts, [api, workspaceId])
  useEffect(loadNodes, [api, workspaceId, type])

  const runSearch = () => {
    loadCounts()
    loadNodes()
  }

  const remove = async (id: string) => {
    await api.deleteNode(workspaceId, id)
    setNodes((prev) => prev.filter((n) => n.id !== id))
    loadCounts()
  }
  const boost = async (id: string) => {
    await api.boostNode(workspaceId, id, 0.2)
    loadNodes()
  }
  const startMove = async (id: string) => {
    const r = await api.listWorkspaces().catch(() => ({ workspaces: [] }))
    setOtherWs((r.workspaces ?? []).filter((w) => w.id !== workspaceId))
    setMovingId(id)
  }
  const doMove = async (targetId: string) => {
    if (!movingId || !targetId) return
    await api.moveNode(workspaceId, movingId, targetId)
    setNodes((prev) => prev.filter((n) => n.id !== movingId))
    setMovingId(null)
    loadCounts()
  }

  return (
    <div className="max-w-4xl p-8">
      <h1 className="mb-6 text-2xl font-bold">Memory Browser</h1>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && runSearch()}
        placeholder="Search… (press Enter)"
        className="mb-4 w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm"
      />

      <div className="mb-5 flex flex-wrap gap-2">
        {CHIP_ORDER.filter((t) => t === "all" || (counts[t] ?? 0) > 0).map((t) => {
          const active = type === t
          return (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                active
                  ? "border-accent bg-accent text-white"
                  : "border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
              }`}
            >
              {CHIP_LABELS[t] ?? t} <span className={active ? "opacity-80" : "opacity-60"}>({counts[t] ?? 0})</span>
            </button>
          )
        })}
      </div>

      <div className="space-y-2">
        {nodes.map((n) =>
          movingId === n.id ? (
            <div key={n.id} className="flex items-center gap-2 rounded-lg border border-accent bg-bg-secondary p-3">
              <span className="text-xs text-text-secondary">Move to:</span>
              <select
                defaultValue=""
                onChange={(e) => doMove(e.target.value)}
                className="flex-1 rounded border border-border bg-bg-tertiary px-2 py-1 text-xs"
              >
                <option value="" disabled>Choose a workspace…</option>
                {otherWs.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
              <button onClick={() => setMovingId(null)} className="rounded border border-border px-2 py-1 text-xs text-text-secondary">Cancel</button>
            </div>
          ) : (
            <MemoryNodeCard key={n.id} node={n} onBoost={boost} onMove={startMove} onDelete={remove} />
          ),
        )}
        {nodes.length === 0 && <p className="p-8 text-center text-sm text-text-secondary">No memories match.</p>}
      </div>
    </div>
  )
}
