import { useEffect, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { Conflict } from "~lib/types"

function shortHex(id: string): string {
  const h = id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 4).toUpperCase()
  return `0x${h}…`
}

// Human-friendly label + accent color per conflict type (backend stores raw
// snake_case like "version_fork"; never show that to the user).
function conflictType(type: string): { label: string; text: string; bg: string; border: string } {
  switch (type) {
    case "version_fork":
      return { label: "Changed plan", text: "text-primary", bg: "bg-primary/10", border: "border-primary/20" }
    case "direct_fact":
      return { label: "Fact collision", text: "text-error", bg: "bg-error/10", border: "border-error/20" }
    case "goal_state":
    case "goal_conflict":
      return { label: "Goal change", text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" }
    case "preference":
      return { label: "Preference", text: "text-secondary", bg: "bg-secondary/10", border: "border-secondary/20" }
    case "logical_error":
    case "logical_inconsistency":
      return { label: "Logic error", text: "text-error", bg: "bg-error/10", border: "border-error/20" }
    case "semantic_drift":
      return { label: "Drift", text: "text-secondary", bg: "bg-secondary/10", border: "border-secondary/20" }
    case "scope_contradiction":
      return { label: "Scope change", text: "text-primary", bg: "bg-primary/10", border: "border-primary/20" }
    case "entity_disambiguation":
      return { label: "Same name", text: "text-secondary", bg: "bg-secondary/10", border: "border-secondary/20" }
    default:
      return { label: type.replace(/_/g, " "), text: "text-on-surface-variant", bg: "bg-surface-container-highest", border: "border-outline-variant" }
  }
}

function statusChip(status: string): { label: string; cls: string } {
  switch (status) {
    case "auto_resolved":
      return { label: "Auto-resolved", cls: "bg-primary/10 text-primary" }
    case "user_resolved":
      return { label: "Resolved", cls: "bg-emerald-500/10 text-emerald-400" }
    case "dismissed":
      return { label: "Dismissed", cls: "bg-surface-container-highest text-outline" }
    default:
      return { label: status, cls: "bg-surface-container-highest text-on-surface-variant" }
  }
}

export function ConflictManager({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [contents, setContents] = useState<Record<string, string>>({})

  const load = () => {
    // Fetch ALL conflicts (no status filter) so auto-resolved ones are visible
    // too — otherwise a silent supersession just shows as "0 pending".
    api.getConflicts(workspaceId).then((r) => {
      setConflicts(r.conflicts)
      // Pull both nodes' text so each card can show STATE A / STATE B.
      const ids = new Set<string>()
      r.conflicts.forEach((c) => {
        ids.add(c.node_a_id)
        ids.add(c.node_b_id)
      })
      ids.forEach((id) => {
        api
          .getNode(workspaceId, id)
          .then((res) => setContents((prev) => ({ ...prev, [id]: res.node.content })))
          .catch(() => {})
      })
    })
  }
  useEffect(load, [api, workspaceId])

  const resolve = async (c: Conflict, strategy: string) => {
    await api.resolveConflict(workspaceId, c.id, { strategy })
    load() // refetch so it moves into the Resolved section rather than vanishing
  }

  const pending = conflicts.filter((c) => c.status === "pending")
  const resolved = conflicts.filter((c) => c.status !== "pending")

  return (
    <div className="flex flex-1 overflow-hidden">
      <section className="mx-auto w-full max-w-4xl flex-1 overflow-y-auto px-lg py-lg">
        <div className="mb-lg flex items-end justify-between">
          <div>
            <h3 className="font-headline-lg text-headline-lg text-on-surface">Memory Arbitration</h3>
            <p className="max-w-md font-body-sm text-body-sm text-on-surface-variant">
              The engine has identified logical contradictions within the active memory bank. Resolve these state conflicts to maintain coherence.
            </p>
          </div>
          <div className="text-right">
            <span className="mb-1 block font-label-caps text-label-caps uppercase text-on-surface-variant">Queue Status</span>
            <span className="rounded border border-primary/20 bg-primary/10 px-sm py-0.5 font-code-md text-code-md text-primary">
              {pending.length} Pending
            </span>
          </div>
        </div>

        <div className="space-y-md">
          {pending.map((c) => {
            const score = Math.round(c.contradiction_score * 100)
            const high = c.contradiction_score >= 0.8
            const accent = high ? "border-primary" : "border-secondary"
            const scoreColor = high ? "text-error" : "text-secondary"
            const ct = conflictType(c.conflict_type)
            return (
              <div key={c.id} className={`group border-l-2 bg-surface-container-low transition-all duration-150 hover:border-l-4 ${accent}`}>
                <div className="flex items-start justify-between border-b border-outline-variant/30 p-md">
                  <div className="flex items-center gap-sm">
                    <span className={`border px-sm py-1 font-label-caps text-label-caps uppercase ${ct.bg} ${ct.text} ${ct.border}`}>{ct.label}</span>
                    <span className="font-code-md text-code-md text-on-surface-variant">
                      {shortHex(c.node_a_id)} ↔ {shortHex(c.node_b_id)}
                    </span>
                  </div>
                  <div className="flex items-center gap-xs">
                    <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">Contradiction Score</span>
                    <span className={`font-code-md text-code-md ${scoreColor}`}>{score}%</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-md bg-surface-container-lowest/50 p-md md:grid-cols-2">
                  <div className="space-y-sm">
                    <span className="font-label-caps text-label-caps uppercase opacity-50">State A</span>
                    <div className="rounded border border-outline-variant/50 bg-surface-container-high p-sm">
                      <p className="font-body-md text-body-md text-on-surface">{contents[c.node_a_id] ?? "…"}</p>
                    </div>
                  </div>
                  <div className="space-y-sm">
                    <span className="font-label-caps text-label-caps uppercase opacity-50">State B</span>
                    <div className="rounded border border-outline-variant/50 bg-surface-container-high p-sm">
                      <p className="font-body-md text-body-md text-on-surface">{contents[c.node_b_id] ?? "…"}</p>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-sm bg-surface-container-low p-sm">
                  <button onClick={() => resolve(c, "merge")} className="border border-outline-variant px-md py-1.5 font-label-caps text-label-caps uppercase transition-colors hover:bg-surface-container-highest">
                    Both valid
                  </button>
                  <button onClick={() => resolve(c, "keep_b")} className="border border-outline-variant bg-surface-container-highest px-md py-1.5 font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:border-primary">
                    Keep B
                  </button>
                  <button onClick={() => resolve(c, "keep_a")} className="bg-primary-container px-md py-1.5 font-label-caps text-label-caps uppercase text-on-primary-container transition-opacity hover:opacity-90">
                    Keep A
                  </button>
                </div>
              </div>
            )
          })}

          {conflicts.length === 0 && (
            <div className="flex flex-col items-center justify-center rounded border border-dashed border-outline-variant bg-surface-container-low py-xl">
              <span className="material-symbols-outlined mb-md text-[48px] text-outline-variant">task_alt</span>
              <h4 className="font-headline-md text-headline-md text-on-surface-variant">No conflicts yet.</h4>
              <p className="font-body-sm text-body-sm text-outline">State is currently coherent across all active threads.</p>
            </div>
          )}

          {pending.length === 0 && resolved.length > 0 && (
            <div className="flex items-center gap-sm rounded border border-outline-variant/50 bg-surface-container-low p-sm">
              <span className="material-symbols-outlined text-[18px] text-emerald-400">task_alt</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant">No conflicts awaiting your decision — see resolved history below.</span>
            </div>
          )}
        </div>

        {/* Resolved history — includes silent auto-resolutions (e.g. a newer
            choice that superseded an older one) so nothing is hidden. */}
        {resolved.length > 0 && (
          <div className="mt-lg space-y-sm">
            <div className="flex items-center gap-sm border-b border-outline-variant/30 pb-xs">
              <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">Resolved</span>
              <span className="font-code-md text-[10px] text-outline">{resolved.length}</span>
            </div>
            {resolved.map((c) => {
              const chip = statusChip(c.status)
              return (
                <div key={c.id} className="flex items-center justify-between border-l-2 border-outline-variant bg-surface-container-low/60 p-sm">
                  <div className="flex min-w-0 items-center gap-sm">
                    <span className={`shrink-0 border px-sm py-0.5 font-label-caps text-label-caps uppercase ${conflictType(c.conflict_type).bg} ${conflictType(c.conflict_type).text} ${conflictType(c.conflict_type).border}`}>{conflictType(c.conflict_type).label}</span>
                    <span className="truncate font-code-md text-code-md text-on-surface-variant">
                      {contents[c.node_a_id] ?? shortHex(c.node_a_id)} <span className="text-outline">↔</span> {contents[c.node_b_id] ?? shortHex(c.node_b_id)}
                    </span>
                  </div>
                  <span className={`ml-sm shrink-0 rounded px-sm py-0.5 font-label-caps text-[10px] uppercase ${chip.cls}`}>{chip.label}</span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Inference Metadata Panel */}
      <aside className="hidden w-[320px] flex-col border-l border-outline-variant bg-surface-container-low lg:flex">
        <div className="border-b border-outline-variant p-md">
          <h3 className="font-label-caps text-label-caps uppercase text-on-surface-variant">Inference Metadata</h3>
        </div>
        <div className="flex-1 space-y-lg overflow-y-auto p-md">
          <div className="space-y-sm">
            <span className="font-label-caps text-label-caps uppercase opacity-40">Queue Pressure</span>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
              <div className="h-full bg-primary" style={{ width: `${Math.min(100, pending.length * 20)}%` }} />
            </div>
            <div className="flex justify-between font-code-md text-[10px] text-on-surface-variant">
              <span>PENDING: {pending.length}</span>
              <span>RESOLVED: {resolved.length}</span>
            </div>
          </div>

          <div className="space-y-md">
            <span className="font-label-caps text-label-caps uppercase opacity-40">Active Memory Visualization</span>
            <div className="relative flex aspect-square items-center justify-center overflow-hidden border border-outline-variant bg-surface-container-lowest">
              <div className="pointer-events-none absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_50%_50%,#5856d6_0%,transparent_70%)]" />
              <div className="grid h-full w-full grid-cols-6 grid-rows-6 gap-1 p-md">
                {Array.from({ length: 36 }).map((_, i) => {
                  const isConflict = i < pending.length * 3 && i % 5 === 0
                  const isActive = i % 7 === 0
                  return (
                    <div
                      key={i}
                      className={
                        isConflict
                          ? "border border-error/40 bg-error/20"
                          : isActive
                            ? "border border-primary/40 bg-primary/20"
                            : "border border-outline-variant bg-surface-container-highest"
                      }
                    />
                  )
                })}
              </div>
              <div className="absolute bottom-2 left-2 right-2 border border-outline-variant bg-background/80 px-sm py-1 font-code-md text-[9px] text-on-surface-variant backdrop-blur">
                ACTIVE_CONTRADICTIONS: {pending.length}
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}
