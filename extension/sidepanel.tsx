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
const TABS: [TabId, string, string][] = [
  ["memory", "Memory", "memory"],
  ["graph", "Graph", "account_tree"],
  ["audit", "Audit", "verified_user"],
  ["search", "Filter", "filter_list"],
]

function SidePanel() {
  const { api, online } = useApi()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [active, setActive] = useState<Workspace | null>(null)
  const [tab, setTab] = useState<TabId>("memory")

  useEffect(() => {
    if (!api || !online) return
    Promise.all([
      api.listWorkspaces(),
      chrome.storage.local.get("mn_active_workspace_id"),
    ]).then(([r, stored]) => {
      setWorkspaces(r.workspaces)
      const remembered = r.workspaces.find((w) => w.id === stored.mn_active_workspace_id)
      setActive(remembered ?? r.workspaces[0] ?? null)
    })
  }, [api, online])

  // Persist the active workspace id so the dashboard / next sidepanel open
  // lands on the same one instead of resetting to workspaces[0].
  useEffect(() => {
    if (active) void chrome.storage.local.set({ mn_active_workspace_id: active.id })
  }, [active])

  // Stay in sync if the dashboard (in another tab) switches workspaces while
  // the sidepanel is open.
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

  if (!online || !api) return <EngineOffline />
  if (!active)
    return (
      <div className="flex h-screen items-center justify-center bg-surface-container-lowest p-6 text-center font-body-sm text-body-sm text-on-surface-variant">
        No workspaces yet. Create one to start capturing.
      </div>
    )

  return (
    <div className="flex h-screen flex-col bg-surface-container-lowest font-body-md text-on-background">
      {/* Header: workspace + command hint */}
      <header className="border-b border-outline-variant p-md">
        <div className="mb-gutter flex items-center gap-sm">
          <div className="h-2 w-2 rounded-full bg-primary" />
          <span className="font-label-caps text-label-caps uppercase text-on-surface">Project: Mnemosyne</span>
        </div>
        <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />
        <div className="mt-gutter flex items-center gap-base rounded border border-outline-variant bg-surface-container-low p-xs">
          <span className="material-symbols-outlined ml-xs text-[16px] text-on-surface-variant">bolt</span>
          <span className="w-full py-xs font-body-sm text-body-sm text-on-surface-variant">Press for commands</span>
          <kbd className="rounded border border-outline-variant bg-surface px-1 py-0.5 text-[9px] text-on-surface-variant">⌘K</kbd>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex border-b border-outline-variant">
        {TABS.map(([id, label, icon]) => {
          const isActive = tab === id
          return (
            <button
              key={id}
              onClick={() => setTab(id)}
              aria-current={isActive ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-xs border-b-2 py-gutter transition-colors duration-200 ${
                isActive ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
              }`}>
              <span className="material-symbols-outlined text-[18px]">{icon}</span>
              <span className="font-label-caps text-label-caps uppercase">{label}</span>
            </button>
          )
        })}
      </nav>

      {/* Content */}
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {tab === "memory" && <MemoryTab api={api} workspaceId={active.id} />}
        {tab === "graph" && <GraphTab api={api} workspaceId={active.id} />}
        {tab === "audit" && <AuditTab api={api} workspaceId={active.id} />}
        {tab === "search" && <SearchTab api={api} workspaceId={active.id} />}
      </main>

      {/* Footer */}
      <footer className="flex items-center justify-between border-t border-outline-variant bg-surface-container-lowest p-md">
        <div className="flex -space-x-1">
          <div className="flex h-6 w-6 items-center justify-center rounded-full border border-background bg-primary-container text-[8px] font-bold text-on-primary-container">AI</div>
          <div className="flex h-6 w-6 items-center justify-center rounded-full border border-background bg-secondary-container text-[8px] font-bold text-on-secondary-container">ME</div>
        </div>
        <button
          onClick={() => chrome.tabs.create({ url: chrome.runtime.getURL("tabs/dashboard.html") })}
          aria-label="Open dashboard"
          className="material-symbols-outlined text-[18px] text-on-surface-variant hover:text-on-surface">
          settings
        </button>
      </footer>

      <CommandPalette
        actions={[
          { id: "memory", label: "Go to Memory", icon: "memory", group: "Navigation", run: () => setTab("memory") },
          { id: "graph", label: "Go to Graph", icon: "account_tree", group: "Navigation", run: () => setTab("graph") },
          { id: "audit", label: "Go to Audit", icon: "verified_user", group: "Navigation", run: () => setTab("audit") },
          { id: "search", label: "Go to Filter", icon: "filter_list", group: "Navigation", run: () => setTab("search") },
          {
            id: "dash",
            label: "Open Memory Audit dashboard",
            icon: "insights",
            group: "Actions",
            run: () => chrome.tabs.create({ url: chrome.runtime.getURL("tabs/dashboard.html") }),
          },
        ]}
      />
    </div>
  )
}

export default SidePanel
