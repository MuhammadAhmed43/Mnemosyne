import { useCallback, useEffect, useRef, useState } from "react"

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
  ["overview", "Overview", "dashboard"],
  ["graph", "Graph", "hub"],
  ["memory", "Memory Banks", "memory"],
  ["conflicts", "Conflicts", "warning"],
  ["sessions", "Sessions", "history"],
  ["settings", "Settings", "settings"],
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
  const fileInput = useRef<HTMLInputElement>(null)

  const loadWorkspaces = useCallback(() => {
    if (!api || !online) return
    Promise.all([
      api.listWorkspaces(),
      chrome.storage.local.get("mn_active_workspace_id"),
    ]).then(([r, stored]) => {
      setWorkspaces(r.workspaces)
      // Keep the user on their current workspace; on first load fall back to
      // the workspace the sidepanel / previous dashboard session was using.
      setActive((cur) => {
        if (cur) return r.workspaces.find((w) => w.id === cur.id) ?? cur
        const remembered = r.workspaces.find((w) => w.id === stored.mn_active_workspace_id)
        return remembered ?? r.workspaces[0] ?? null
      })
    })
  }, [api, online])

  useEffect(loadWorkspaces, [loadWorkspaces])

  // Persist the active workspace id so the sidepanel / next dashboard open
  // lands on the same one.
  useEffect(() => {
    if (active) void chrome.storage.local.set({ mn_active_workspace_id: active.id })
  }, [active])

  // Stay in sync if the sidepanel switches workspaces while the dashboard tab
  // is open.
  useEffect(() => {
    const handler = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "local" || !changes.mn_active_workspace_id) return
      const newId = changes.mn_active_workspace_id.newValue as string | undefined
      if (!newId || newId === active?.id) return
      const ws = workspaces.find((w) => w.id === newId)
      if (ws) setActive(ws)
    }
    chrome.storage.onChanged.addListener(handler)
    return () => chrome.storage.onChanged.removeListener(handler)
  }, [workspaces, active])

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
            if (n > 0) showToast(`Saved ${n} ${n === 1 ? "memory" : "memories"}${ev.workspace_name ? ` to ${ev.workspace_name}` : ""}`, p > 0 ? { sub: `${p} awaiting review` } : {})
            else if (p > 0) showToast(`${p} item${p === 1 ? "" : "s"} to review${ev.workspace_name ? ` in ${ev.workspace_name}` : ""}`)
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

  const exportWorkspace = async (fmt: "json" | "csv" | "md") => {
    if (!active || !api) return
    const data = await api.exportWorkspace(active.id)
    const nodes = (data.nodes as Record<string, unknown>[]) ?? []
    const base = `mnemosyne-${active.name.replace(/\s+/g, "_")}-${new Date().toISOString().slice(0, 10)}`
    if (fmt === "json") download(`${base}.json`, JSON.stringify(data, null, 2), "application/json")
    else if (fmt === "csv") download(`${base}.csv`, toCsv(nodes), "text/csv")
    else download(`${base}.md`, toMarkdown(active.name, nodes), "text/markdown")
  }

  const importWorkspace = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !api) return
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

  if (!online || !api)
    return (
      <div className="flex h-screen items-center justify-center bg-background font-body-md text-on-surface-variant">
        Mnemosyne engine is not running.
      </div>
    )

  return (
    <div className="flex h-screen overflow-hidden bg-background font-body-md text-on-background">
      {/* SideNavBar */}
      <aside className="z-50 flex h-full w-60 shrink-0 flex-col space-y-base border-r border-outline-variant bg-surface-container-lowest py-md">
        {/* Wordmark & Workspace */}
        <div className="mb-lg px-md">
          <h1 className="font-headline-md text-headline-md font-black tracking-tight text-on-surface">Mnemosyne</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant opacity-60">AI Persistent State</p>
          <div className="mt-lg">
            <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-grow space-y-base overflow-y-auto px-xs">
          {NAV.map(([id, label, icon]) => {
            const isActive = page === id
            return (
              <button
                key={id}
                onClick={() => setPage(id)}
                aria-current={isActive ? "page" : undefined}
                className={`flex w-full items-center px-md py-sm transition-all hover:bg-surface-container-highest/50 ${
                  isActive
                    ? "translate-x-1 border-r-2 border-primary bg-secondary-container/30 text-primary"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}>
                <span className="material-symbols-outlined mr-sm">{icon}</span>
                <span className="font-label-caps text-label-caps uppercase">{label}</span>
              </button>
            )
          })}
        </nav>

        {/* Export & Import */}
        <div className="mt-auto space-y-md border-t border-outline-variant px-md py-md">
          <div className="space-y-xs">
            <span className="mb-xs block font-label-caps text-label-caps uppercase text-on-surface-variant opacity-50">Export Engine</span>
            <div className="grid grid-cols-3 gap-xs">
              {(["json", "csv", "md"] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => exportWorkspace(fmt)}
                  disabled={!active}
                  className="border border-outline-variant bg-surface-container py-xs font-code-md text-code-md uppercase text-on-surface transition-colors hover:bg-surface-container-high disabled:opacity-40">
                  {fmt}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => fileInput.current?.click()}
            className="group flex w-full cursor-pointer flex-col items-center justify-center border-2 border-dashed border-outline-variant p-sm transition-colors hover:border-primary">
            <span className="material-symbols-outlined mb-xs text-on-surface-variant group-hover:text-primary">upload_file</span>
            <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">Import State</span>
          </button>
          <input ref={fileInput} type="file" accept="application/json" onChange={importWorkspace} className="hidden" />
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* TopNavBar */}
        <header className="sticky top-0 z-40 flex h-12 w-full items-center justify-between border-b border-outline-variant bg-surface/80 px-md backdrop-blur-xl">
          <div className="flex items-center gap-xs">
            <span className={`h-2 w-2 rounded-full ${online ? "animate-pulse bg-emerald-500" : "bg-error"}`} />
            <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">
              {online ? "Engine running" : "Engine offline"}
            </span>
          </div>
          <div className="flex items-center gap-md">
            <button
              onClick={() => setPage("settings")}
              aria-label="Settings"
              className="material-symbols-outlined rounded p-xs text-on-surface-variant transition-colors hover:bg-surface-container-high">
              settings
            </button>
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-outline-variant bg-surface-container-high text-on-surface-variant">
              <span className="material-symbols-outlined text-[18px]">person</span>
            </div>
          </div>
        </header>

        {/* Page Canvas — pages own their internal layout + any inspect panel.
            `key` includes refreshKey so data views remount on a live event;
            Settings is excluded so an in-progress edit isn't wiped by a refresh. */}
        {!active ? (
          <p className="p-lg font-body-md text-body-md text-on-surface-variant">No workspaces yet.</p>
        ) : page === "overview" ? (
          <Overview key={refreshKey} api={api} workspaceId={active.id} workspaceName={active.name} onOpenGraph={() => setPage("graph")} />
        ) : page === "graph" ? (
          <GraphTab key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "memory" ? (
          <MemoryBrowser key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "conflicts" ? (
          <ConflictManager key={refreshKey} api={api} workspaceId={active.id} />
        ) : page === "sessions" ? (
          <SessionReplay key={refreshKey} api={api} workspaceId={active.id} />
        ) : (
          <SettingsPage api={api} />
        )}
      </main>
    </div>
  )
}

export default Dashboard
