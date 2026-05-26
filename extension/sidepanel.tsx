import { useEffect, useState } from "react"

import { AuditTab } from "~components/AuditTab"
import { CommandPalette } from "~components/CommandPalette"
import { EngineOffline } from "~components/EmptyStates"
import { GraphTab } from "~components/GraphTab"
import { MemoryTab } from "~components/MemoryTab"
import { SearchTab } from "~components/SearchTab"
import { WorkspaceSelector } from "~components/WorkspaceSelector"
import { useApi } from "~lib/useApi"
import type { Workspace } from "~lib/types"

import "~style.css"

type TabId = "memory" | "graph" | "audit" | "search"
const TABS: [TabId, string][] = [
  ["memory", "Memory"],
  ["graph", "Graph"],
  ["audit", "Audit"],
  ["search", "Search"],
]

function SidePanel() {
  const { api, online } = useApi()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [active, setActive] = useState<Workspace | null>(null)
  const [tab, setTab] = useState<TabId>("memory")

  useEffect(() => {
    if (api && online) {
      api.listWorkspaces().then((r) => {
        setWorkspaces(r.workspaces)
        setActive(r.workspaces[0] ?? null)
      })
    }
  }, [api, online])

  if (!online || !api) return <EngineOffline />
  if (!active) return <div className="p-6 text-sm text-text-secondary">No workspaces yet. Create one to start capturing.</div>

  return (
    <div className="flex h-screen flex-col bg-bg-primary text-text-primary">
      <header className="border-b border-border p-3">
        <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />
      </header>
      <nav className="flex border-b border-border">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 py-2 text-sm transition ${
              tab === id ? "border-b-2 border-accent text-accent" : "text-text-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
      <main className="flex-1 overflow-y-auto">
        {tab === "memory" && <MemoryTab api={api} workspaceId={active.id} />}
        {tab === "graph" && <GraphTab api={api} workspaceId={active.id} />}
        {tab === "audit" && <AuditTab api={api} workspaceId={active.id} />}
        {tab === "search" && <SearchTab api={api} workspaceId={active.id} />}
      </main>
      <CommandPalette
        actions={[
          { id: "memory", label: "Go to Memory", run: () => setTab("memory") },
          { id: "graph", label: "Go to Graph", run: () => setTab("graph") },
          { id: "audit", label: "Go to Audit", run: () => setTab("audit") },
          { id: "search", label: "Go to Search", run: () => setTab("search") },
          { id: "dash", label: "Open Memory Audit dashboard",
            run: () => chrome.tabs.create({ url: chrome.runtime.getURL("tabs/dashboard.html") }) },
        ]}
      />
    </div>
  )
}

export default SidePanel
