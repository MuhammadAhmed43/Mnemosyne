import { useEffect, useState } from "react"

import { GraphTab } from "~components/GraphTab"
import { WorkspaceSelector } from "~components/WorkspaceSelector"
import { ConflictManager } from "~components/dashboard/ConflictManager"
import { MemoryBrowser } from "~components/dashboard/MemoryBrowser"
import { Overview } from "~components/dashboard/Overview"
import { SessionReplay } from "~components/dashboard/SessionReplay"
import { SettingsPage } from "~components/dashboard/SettingsPage"
import { useApi } from "~lib/useApi"
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

  useEffect(() => {
    if (api && online) {
      api.listWorkspaces().then((r) => {
        setWorkspaces(r.workspaces)
        setActive(r.workspaces[0] ?? null)
      })
    }
  }, [api, online])

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
        {!active ? (
          <p className="p-8 text-text-secondary">No workspaces yet.</p>
        ) : page === "overview" ? (
          <Overview api={api} workspaceId={active.id} />
        ) : page === "graph" ? (
          <div className="h-full"><GraphTab api={api} workspaceId={active.id} /></div>
        ) : page === "memory" ? (
          <MemoryBrowser api={api} workspaceId={active.id} />
        ) : page === "conflicts" ? (
          <ConflictManager api={api} workspaceId={active.id} />
        ) : page === "sessions" ? (
          <div className="h-full"><SessionReplay api={api} workspaceId={active.id} /></div>
        ) : (
          <SettingsPage api={api} />
        )}
      </main>
    </div>
  )
}

export default Dashboard
