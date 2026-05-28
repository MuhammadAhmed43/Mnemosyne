import { useCallback, useEffect, useState } from "react"

import { nodeColor, nodeLabel } from "~components/NodeTypeBadge"
import type { MnemosyneAPI } from "~lib/api"
import type { Brief } from "~lib/types"

interface Props {
  api: MnemosyneAPI
  workspaceId: string
  workspaceName?: string
  onOpenGraph?: () => void
}

export function Overview({ api, workspaceId, workspaceName, onOpenGraph }: Props) {
  const [health, setHealth] = useState<number | null>(null)
  const [conflicts, setConflicts] = useState(0)
  const [brief, setBrief] = useState<Brief | null>(null)
  const [syncing, setSyncing] = useState(false)

  const load = useCallback(() => {
    setSyncing(true)
    // Counts come from the brief (the endpoint caps node listing at 500, so the
    // old limit=1000 returned 422). Brief is the source of truth for the home view.
    Promise.all([
      api.getHealth(workspaceId).then((h) => setHealth(h.memory_health_score)).catch(() => setHealth(null)),
      api.getConflicts(workspaceId, "open").then((r) => setConflicts(r.total)).catch(() => setConflicts(0)),
      api.getBrief(workspaceId).then(setBrief).catch(() => setBrief(null)),
    ]).finally(() => setSyncing(false))
  }, [api, workspaceId])

  useEffect(load, [load])

  const activeCount = brief?.total ?? 0
  const typeCount = new Set((brief?.sections ?? []).flatMap((s) => s.items.map((i) => i.type))).size
  const healthPct = health !== null ? Math.round(health * 100) : null

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Brief canvas */}
      <div className="flex-1 space-y-lg overflow-y-auto p-lg">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="font-headline-lg text-headline-lg text-on-surface">{workspaceName ?? "Overview"}</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">The current state of this project — kept up to date as you talk.</p>
          </div>
          <div className="flex gap-sm">
            <button
              onClick={onOpenGraph}
              className="flex h-8 items-center gap-sm rounded border border-outline-variant bg-surface-container-high px-md font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:bg-surface-container-highest">
              <span className="material-symbols-outlined text-[14px]">hub</span>
              Graph
            </button>
            <button
              onClick={load}
              disabled={syncing}
              className="flex h-8 items-center gap-sm rounded bg-primary-container px-md font-label-caps text-label-caps uppercase text-on-primary-container transition-all hover:opacity-80 disabled:opacity-50">
              <span className={`material-symbols-outlined text-[14px] ${syncing ? "animate-spin" : ""}`}>refresh</span>
              Sync
            </button>
          </div>
        </div>

        {/* Stat grid */}
        <div className="grid grid-cols-1 gap-gutter md:grid-cols-3">
          <Stat label="Memory Health" value={healthPct !== null ? `${healthPct}%` : "—"} icon="shield" bar={healthPct ?? undefined} />
          <Stat label="Active Memories" value={String(activeCount)} icon="analytics" sub={`in ${workspaceName ?? "this workspace"}`} />
          <Stat label="Memory Types" value={String(typeCount)} icon="category" sub="distinct schemas" />
        </div>

        {/* Living brief */}
        <div className="space-y-gutter">
          {brief?.sections.map((sec) => (
            <div key={sec.title} className="border border-outline-variant bg-surface-container">
              <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-low p-md">
                <span className="font-label-caps text-label-caps uppercase text-on-surface">{sec.title}</span>
                <span className="font-code-md text-code-md text-on-surface-variant">{sec.items.length}</span>
              </div>
              <div className="divide-y divide-outline-variant/40">
                {sec.items.map((it) => (
                  <div key={it.id} className="flex gap-sm p-md transition-colors hover:bg-surface-container-highest/20">
                    <div className="mt-1 h-4 w-1 shrink-0" style={{ background: nodeColor(it.type) }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-sm">
                        <p className="font-body-md text-body-md text-on-surface">{it.content}</p>
                        {it.status && (
                          <span className="shrink-0 rounded bg-surface-container-highest px-xs py-[1px] font-label-caps text-[9px] uppercase text-on-surface-variant">{it.status}</span>
                        )}
                      </div>
                      {it.rationale && (
                        <p className="mt-xs border-l-2 border-outline-variant pl-sm font-body-sm text-body-sm text-on-surface-variant">Why: {it.rationale}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {(!brief || brief.sections.length === 0) && (
            <div className="flex flex-col items-center justify-center rounded border border-dashed border-outline-variant bg-surface-container-low py-xl text-center">
              <span className="material-symbols-outlined mb-md text-[40px] text-outline-variant">menu_book</span>
              <h4 className="font-headline-md text-headline-md text-on-surface-variant">No memories captured yet.</h4>
              <p className="max-w-sm font-body-sm text-body-sm text-outline">Start talking about this project in Claude / ChatGPT / Gemini — the brief fills in automatically.</p>
            </div>
          )}
        </div>
      </div>

      {/* Inspect panel */}
      <aside className="hidden w-80 shrink-0 flex-col border-l border-outline-variant bg-surface-container-low xl:flex">
        <div className="flex items-center justify-between border-b border-outline-variant p-md">
          <span className="font-label-caps text-label-caps uppercase text-on-surface">Inspect: System</span>
        </div>
        <div className="flex-1 space-y-lg overflow-y-auto p-md">
          <section className="space-y-sm">
            <span className="font-label-caps text-label-caps uppercase text-on-surface-variant opacity-50">Workspace State</span>
            <div className="space-y-sm border border-outline-variant bg-surface-container p-sm">
              <Row k="Active nodes" v={String(activeCount)} />
              <Row k="Memory types" v={String(typeCount)} />
              <Row k="Health score" v={healthPct !== null ? `${healthPct}%` : "—"} />
            </div>
          </section>

          <section className="space-y-sm">
            <span className="font-label-caps text-label-caps uppercase text-on-surface-variant opacity-50">Recent Activity</span>
            <div className="space-y-xs">
              {brief?.recent.slice(0, 6).map((r) => (
                <div key={r.id} className="flex items-start gap-sm border-b border-outline-variant/30 pb-xs">
                  <span className="mt-[3px] h-2 w-2 shrink-0 rounded-full" style={{ background: nodeColor(r.type) }} />
                  <div className="min-w-0">
                    <p className="truncate font-body-sm text-body-sm text-on-surface">{r.content}</p>
                    <span className="font-label-caps text-[9px] uppercase text-outline">{nodeLabel(r.type)}{r.version > 1 ? ` · v${r.version}` : ""}</span>
                  </div>
                </div>
              ))}
              {(!brief || brief.recent.length === 0) && <p className="font-body-sm text-body-sm text-on-surface-variant">Nothing yet.</p>}
            </div>
          </section>

          <section className="space-y-sm">
            <span className="font-label-caps text-label-caps uppercase text-on-surface-variant opacity-50">Schema Validation</span>
            {conflicts > 0 ? (
              <div className="rounded border border-error/30 bg-error-container/20 p-sm">
                <div className="flex items-center gap-sm text-error">
                  <span className="material-symbols-outlined text-[16px]">info</span>
                  <span className="font-label-caps text-label-caps uppercase">{conflicts} conflict{conflicts === 1 ? "" : "s"}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-sm rounded border border-outline-variant bg-surface-container p-sm text-emerald-400">
                <span className="material-symbols-outlined text-[16px]">check_circle</span>
                <span className="font-label-caps text-label-caps uppercase">Coherent</span>
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  )
}

function Stat({ label, value, icon, sub, bar }: { label: string; value: string; icon: string; sub?: string; bar?: number }) {
  return (
    <div className="flex h-32 flex-col justify-between border border-outline-variant bg-surface-container p-md transition-colors hover:bg-surface-container-high">
      <div className="flex items-start justify-between">
        <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">{label}</span>
        <span className="material-symbols-outlined text-primary">{icon}</span>
      </div>
      <div>
        <span className="font-headline-lg text-[32px] leading-none text-on-surface">{value}</span>
        {bar !== undefined ? (
          <div className="mt-sm h-1 w-full bg-surface-container-highest">
            <div className="h-full bg-emerald-500" style={{ width: `${bar}%` }} />
          </div>
        ) : (
          sub && <p className="mt-xs font-body-sm text-body-sm text-on-surface-variant">{sub}</p>
        )}
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between font-code-md text-code-md">
      <span className="text-on-surface-variant">{k}:</span>
      <span className="text-primary">{v}</span>
    </div>
  )
}
