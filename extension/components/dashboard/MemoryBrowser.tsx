import { useEffect, useState } from "react"

import { MemoryNodeCard } from "~components/MemoryNodeCard"
import { nodeColor, nodeLabel } from "~components/NodeTypeBadge"
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
  insight: "Ideas",
  user_note: "Notes",
  problem: "Problems",
  task: "Tasks",
  technical_fact: "Facts",
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

  const loadCounts = () => {
    api.nodeCounts(workspaceId, search || undefined).then((r) => setCounts({ all: r.total, ...r.counts }))
  }
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
  const clearFilters = () => {
    setSearch("")
    setType("all")
    api.nodeCounts(workspaceId).then((r) => setCounts({ all: r.total, ...r.counts }))
    api.listNodes(workspaceId, { status: "active", limit: 500 }).then((r) => setNodes(r.nodes))
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

  // Top types by count for the metrics panel (real data adaptation of Stitch "Node Proximity").
  const topTypes = Object.entries(counts)
    .filter(([t]) => t !== "all")
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Content */}
      <section className="flex-1 overflow-y-auto px-xl py-lg">
        <div className="mx-auto max-w-4xl space-y-lg">
          <div className="flex flex-col gap-base">
            <h2 className="font-headline-lg text-headline-lg tracking-tight text-on-surface">Memory Browser</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Exploring {counts.all ?? 0} persistent state node{(counts.all ?? 0) === 1 ? "" : "s"} in this workspace.
            </p>
          </div>

          {/* Search & Filters */}
          <div className="space-y-md">
            <div className="group relative">
              <span className="material-symbols-outlined absolute left-md top-1/2 -translate-y-1/2 text-outline-variant transition-colors group-focus-within:text-primary">search</span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                aria-label="Search memories"
                placeholder="Search across memory banks (press Enter)…"
                type="text"
                className="h-11 w-full border border-outline-variant bg-surface-container-low pl-xl pr-md font-body-md text-body-md text-on-surface transition-all placeholder:text-outline/50 focus:border-primary focus:outline-none focus:ring-0"
              />
              <kbd className="absolute right-md top-1/2 hidden -translate-y-1/2 rounded border border-outline-variant bg-surface-container-highest px-sm py-0.5 font-code-md text-code-md text-outline sm:block">⌘ K</kbd>
            </div>

            <div className="flex flex-wrap items-center gap-sm">
              {CHIP_ORDER.filter((t) => t === "all" || (counts[t] ?? 0) > 0).map((t) => {
                const isActive = type === t
                return (
                  <button
                    key={t}
                    onClick={() => setType(t)}
                    className={`flex h-7 items-center gap-2 px-md font-label-caps text-label-caps uppercase transition-colors ${
                      isActive
                        ? "bg-primary text-on-primary"
                        : "border border-outline-variant bg-surface-container-highest text-on-surface-variant hover:text-on-surface"
                    }`}>
                    {CHIP_LABELS[t] ?? t} <span className="opacity-70">{counts[t] ?? 0}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Memory List */}
          <div className="space-y-base">
            {nodes.map((n) =>
              movingId === n.id ? (
                <div key={n.id} className="group relative flex flex-col gap-sm border-2 border-primary bg-surface-container-high p-md">
                  <div className="mb-xs flex items-center justify-between">
                    <div className="flex items-center gap-sm">
                      <span className="material-symbols-outlined text-primary">drive_file_move</span>
                      <span className="font-label-caps text-label-caps uppercase text-primary">Move Memory To…</span>
                    </div>
                    <button onClick={() => setMovingId(null)} aria-label="Cancel move" className="text-on-surface-variant hover:text-on-surface">
                      <span className="material-symbols-outlined !text-[16px]">close</span>
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-sm">
                    {otherWs.length === 0 && (
                      <span className="col-span-2 font-body-sm text-body-sm text-on-surface-variant">No other workspaces.</span>
                    )}
                    {otherWs.map((w) => (
                      <button
                        key={w.id}
                        onClick={() => doMove(w.id)}
                        className="flex items-center gap-2 border border-outline-variant bg-surface-container-low px-sm py-sm text-left transition-all hover:border-primary hover:bg-primary/10">
                        <span className="material-symbols-outlined !text-[18px] text-outline">folder</span>
                        <span className="truncate font-body-sm text-body-sm text-on-surface">{w.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <MemoryNodeCard key={n.id} node={n} onBoost={boost} onMove={startMove} onDelete={remove} />
              ),
            )}

            {nodes.length === 0 && (
              <div className="flex flex-col items-center justify-center space-y-md py-xl opacity-60">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg border-2 border-dashed border-outline-variant">
                  <span className="material-symbols-outlined !text-[32px] text-outline-variant">search_off</span>
                </div>
                <div className="text-center">
                  <p className="font-headline-md text-headline-md text-on-surface-variant">No memories match.</p>
                  <p className="font-body-sm text-body-sm text-outline">Try adjusting your filter or search query.</p>
                </div>
                <button onClick={clearFilters} className="h-8 px-md font-label-caps text-label-caps uppercase transition-colors hover:bg-surface-container-highest">
                  Clear All Filters
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Memory Metrics Panel */}
      <aside className="hidden h-full w-[320px] shrink-0 flex-col overflow-hidden border-l border-outline-variant bg-surface-container-lowest lg:flex">
        <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-low p-md">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-on-surface">Memory Metrics</span>
          <span className="material-symbols-outlined !text-[18px] text-on-surface-variant">more_vert</span>
        </div>
        <div className="flex-1 space-y-lg overflow-y-auto p-md">
          <div className="space-y-sm">
            <label className="font-label-caps text-label-caps uppercase text-outline-variant">Spatial Distribution</label>
            <div className="relative flex aspect-square w-full items-center justify-center overflow-hidden border border-outline-variant bg-surface-container">
              <div className="absolute inset-0 opacity-10" style={{ backgroundImage: "radial-gradient(#c2c1ff 1px, transparent 1px)", backgroundSize: "16px 16px" }} />
              <div className="flex h-40 w-40 animate-pulse items-center justify-center rounded-full border border-primary/20">
                <div className="flex h-20 w-20 items-center justify-center rounded-full border border-primary/40">
                  <div className="h-2 w-2 bg-primary" />
                </div>
              </div>
              <div className="absolute bottom-base right-base font-code-md text-[10px] text-outline-variant">{counts.all ?? 0} NODES</div>
            </div>
          </div>

          <div className="space-y-sm">
            <label className="font-label-caps text-label-caps uppercase text-outline-variant">Decay Rate</label>
            <div className="border border-outline-variant bg-surface-container-low p-sm">
              <div className="mb-xs flex items-center justify-between">
                <span className="font-body-sm text-body-sm text-on-surface">Automatic Pruning</span>
                <div className="relative h-4 w-8 rounded-full bg-primary">
                  <div className="absolute right-0.5 top-0.5 h-3 w-3 rounded-sm bg-on-primary" />
                </div>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant opacity-60">Low-confidence memories are pruned on the decay cycle.</p>
            </div>
          </div>

          <div className="space-y-sm">
            <label className="font-label-caps text-label-caps uppercase text-outline-variant">Type Distribution</label>
            <ul className="space-y-xs">
              {topTypes.map(([t, c]) => (
                <li key={t} className="flex items-center justify-between border-b border-outline-variant/30 p-xs font-code-md text-code-md text-on-surface-variant">
                  <span className="flex items-center gap-sm">
                    <span className="h-3 w-1" style={{ background: nodeColor(t) }} />
                    {nodeLabel(t)}
                  </span>
                  <span className="text-primary">{c}</span>
                </li>
              ))}
              {topTypes.length === 0 && <li className="p-xs font-code-md text-code-md text-outline-variant">No data</li>}
            </ul>
          </div>
        </div>
      </aside>
    </div>
  )
}
