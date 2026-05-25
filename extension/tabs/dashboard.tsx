import { useCallback, useEffect, useState } from "react"

import { GraphTab } from "~components/GraphTab"
import { WorkspaceSelector } from "~components/WorkspaceSelector"
import { ConflictManager } from "~components/dashboard/ConflictManager"
import { MemoryBrowser } from "~components/dashboard/MemoryBrowser"
import { Overview } from "~components/dashboard/Overview"
import { SessionReplay } from "~components/dashboard/SessionReplay"
import { SettingsPage } from "~components/dashboard/SettingsPage"
import { useApi } from "~lib/useApi"
import { showToast } from "~lib/toast"
import type { Workspace } from "~lib/types"

import "~style.css"

type PageId = "overview" | "graph" | "memory" | "conflicts" | "sessions" | "settings"
const NAV: [PageId, string, string][] = [
  ["overview", "📊", "Overview"],
  ["graph", "🕸", "Graph"],
  ["memory", "📝", "Memory"],
  ["conflicts", "⚡", "Conflicts"],
  ["sessions", "🎬", "Sessions"],
  ["settings", "⚙️", "Settings"],
]

function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const CSV_COLS = ["node_type", "content", "importance_score", "status", "created_at"]
function toCsv(nodes: Record<string, unknown>[]): string {
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`
  return [CSV_COLS.join(","), ...nodes.map((n) => CSV_COLS.map((c) => esc(n[c])).join(","))].join("\n")
}
function toMarkdown(wsName: string, nodes: Record<string, unknown>[]): string {
  const byType: Record<string, string[]> = {}
  for (const n of nodes) {
    const t = String(n.node_type ?? "other")
    ;(byType[t] ??= []).push(String(n.content ?? ""))
  }
  let out = `# ${wsName}\n\n_Exported ${new Date().toLocaleString()} · ${nodes.length} memories_\n\n`
  for (const [t, items] of Object.entries(byType)) {
    out += `## ${t} (${items.length})\n\n${items.map((c) => `- ${c}`).join("\n")}\n\n`
  }
  return out
}

function Dashboard() {
  const { api, online } = useApi()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [active, setActive] = useState<Workspace | null>(null)
  const [page, setPage] = useState<PageId>("overview")
  const [refreshKey, setRefreshKey] = useState(0) // bumped on live events to reload data views

  const loadWorkspaces = useCallback(() => {
    if (!api || !online) return
    api.listWorkspaces().then((r) => {
      setWorkspaces(r.workspaces)
      // Keep the user on their current workspace; just refresh its data.
      setActive((cur) => (cur ? r.workspaces.find((w) => w.id === cur.id) ?? cur : r.workspaces[0] ?? null))
    })
  }, [api, online])

  useEffect(loadWorkspaces, [loadWorkspaces])

  // Live updates: when the engine finishes extracting a turn, refresh counts and
  // the active view automatically, and toast what landed — no manual refresh,
  // no guessing which workspace it went to.
  useEffect(() => {
    if (!api || !online) return
    let ws: WebSocket | null = null
    try {
      ws = new WebSocket(api.eventsUrl())
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data)
          if (ev.event === "extraction_completed") {
            loadWorkspaces()
            setRefreshKey((k) => k + 1)
            const n = ev.nodes_committed || 0
            const p = ev.nodes_pending || 0
            if (n > 0) showToast(`🧠 Saved ${n} ${n === 1 ? "memory" : "memories"}${ev.workspace_name ? ` to ${ev.workspace_name}` : ""}`, p > 0 ? { sub: `${p} awaiting review` } : {})
            else if (p > 0) showToast(`📥 ${p} item${p === 1 ? "" : "s"} to review${ev.workspace_name ? ` in ${ev.workspace_name}` : ""}`)
          } else if (ev.event === "decay_completed") {
            loadWorkspaces()
            setRefreshKey((k) => k + 1)
          }
        } catch {
          /* ignore malformed event */
        }
      }
    } catch {
      /* engine may be momentarily unreachable; health poll will recover */
    }
    return () => {
      try { ws?.close() } catch { /* noop */ }
    }
  }, [api, online, loadWorkspaces])

  if (!online || !api) return <div className="p-8 text-text-secondary">Mnemosyne engine is not running.</div>

  const exportWorkspace = async (fmt: "json" | "csv" | "md") => {
    if (!active) return
    const data = await api.exportWorkspace(active.id)
    const nodes = (data.nodes as Record<string, unknown>[]) ?? []
    const base = `mnemosyne-${active.name.replace(/\s+/g, "_")}-${new Date().toISOString().slice(0, 10)}`
    if (fmt === "json") download(`${base}.json`, JSON.stringify(data, null, 2), "application/json")
    else if (fmt === "csv") download(`${base}.csv`, toCsv(nodes), "text/csv")
    else download(`${base}.md`, toMarkdown(active.name, nodes), "text/markdown")
  }

  const importWorkspace = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      try {
        const data = JSON.parse(String(reader.result))
        await api.importWorkspace(data)
        const r = await api.listWorkspaces()
        setWorkspaces(r.workspaces)
      } catch {
        alert("Import failed — not a valid Mnemosyne export file.")
      }
    }
    reader.readAsText(file)
    e.target.value = ""
  }

  return (
    <div className="flex h-screen bg-bg-primary text-text-primary">
      <aside className="flex w-[220px] flex-col border-r border-border">
        <header className="border-b border-border p-4 text-lg font-semibold">🧠 Mnemosyne</header>
        <div className="border-b border-border p-3">
          <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />
        </div>
        <nav className="flex-1 py-2">
          {NAV.map(([id, icon, label]) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-sm ${
                page === id ? "border-r-2 border-accent bg-bg-hover text-accent" : "text-text-secondary hover:bg-bg-hover"
              }`}
            >
              <span>{icon}</span> {label}
            </button>
          ))}
        </nav>
        <div className="space-y-2 border-t border-border p-3">
          <div className="text-[10px] font-semibold uppercase text-text-tertiary">Export workspace</div>
          <div className="flex gap-1">
            {(["json", "csv", "md"] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={() => exportWorkspace(fmt)}
                disabled={!active}
                className="flex-1 rounded-lg border border-border bg-bg-secondary py-1.5 text-xs text-text-secondary hover:text-text-primary disabled:opacity-40"
              >
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
          <label className="block w-full cursor-pointer rounded-lg border border-border bg-bg-secondary py-2 text-center text-xs text-text-secondary hover:text-text-primary">
            ⬆ Import (JSON)
            <input type="file" accept="application/json" onChange={importWorkspace} className="hidden" />
          </label>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        {/* `key` includes refreshKey so data views remount/reload on a live event.
            Settings is excluded so an in-progress edit isn't wiped by a refresh. */}
        {!active ? (
          <p className="p-8 text-text-secondary">No workspaces yet.</p>
        ) : page === "overview" ? (
          <Overview key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "graph" ? (
          <div className="h-full"><GraphTab key={refreshKey} api={api} workspaceId={active.id} /></div>
        ) : page === "memory" ? (
          <MemoryBrowser key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "conflicts" ? (
          <ConflictManager key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "sessions" ? (
          <div className="h-full"><SessionReplay key={refreshKey} api={api} workspaceId={active.id} /></div>
        ) : (
          <SettingsPage api={api} />
        )}
      </main>
    </div>
  )
}

export default Dashboard
