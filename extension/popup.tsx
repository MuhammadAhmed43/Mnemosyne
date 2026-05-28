import { useEffect, useState } from "react"

import { WorkspaceSelector } from "~components/WorkspaceSelector"
import { useApi } from "~lib/useApi"
import type { Workspace } from "~lib/types"

import "~style.css"

function Popup() {
  const { api, online, checking } = useApi()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [active, setActive] = useState<Workspace | null>(null)
  const [capture, setCapture] = useState(true)
  const [incognito, setIncognito] = useState(false)
  const [pending, setPending] = useState(0)

  useEffect(() => {
    chrome.storage.local.get("capture_enabled").then(({ capture_enabled }) => setCapture(capture_enabled ?? true))
    chrome.storage.session.get("incognito").then(({ incognito }) => setIncognito(incognito === true))
    if (api && online) {
      Promise.all([
        api.listWorkspaces(),
        chrome.storage.local.get("mn_active_workspace_id"),
      ]).then(([r, stored]) => {
        setWorkspaces(r.workspaces)
        const remembered = r.workspaces.find((w) => w.id === stored.mn_active_workspace_id)
        const a = remembered ?? r.workspaces[0] ?? null
        setActive(a)
        if (a) api.getPending(a.id).then((p) => setPending(p.total))
      })
    }
  }, [api, online])

  // Persist active workspace so the sidepanel / dashboard land on the same one.
  useEffect(() => {
    if (active) void chrome.storage.local.set({ mn_active_workspace_id: active.id })
  }, [active])

  // Stay in sync if another surface (sidepanel / dashboard) switches workspaces
  // while the popup is open.
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

  useEffect(() => {
    if (api && online && active) api.getPending(active.id).then((p) => setPending(p.total)).catch(() => {})
  }, [api, online, active])

  const toggleCapture = () => {
    const next = !capture
    setCapture(next)
    void chrome.storage.local.set({ capture_enabled: next })
  }
  const toggleIncognito = () => {
    const next = !incognito
    setIncognito(next)
    void chrome.storage.session.set({ incognito: next })
    void chrome.action.setBadgeText({ text: next ? "INC" : "" })
    if (next) void chrome.action.setBadgeBackgroundColor({ color: "#5856d6" })
  }
  const openSidebar = () => {
    void chrome.windows.getCurrent().then((w) => {
      if (w.id !== undefined) void chrome.sidePanel.open({ windowId: w.id })
    })
  }
  const openDashboard = () => {
    void chrome.tabs.create({ url: chrome.runtime.getURL("tabs/dashboard.html") })
  }

  return (
    <div className="flex w-[400px] flex-col overflow-hidden bg-surface font-body-md text-on-background">
      {/* Header */}
      <header className="flex h-12 items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-md py-sm">
        <div className="flex items-center gap-sm">
          <span className={`h-2 w-2 rounded-full ${checking ? "animate-pulse bg-amber-400" : online ? "animate-pulse bg-primary shadow-[0_0_8px_#c2c1ff]" : "bg-error"}`} />
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-on-surface">
            {checking ? "Connecting…" : online ? "Engine running" : "Engine offline"}
          </span>
        </div>
        <div className="flex gap-sm">
          <button onClick={openDashboard} aria-label="Settings" className="material-symbols-outlined text-on-surface-variant transition-colors hover:text-primary">settings</button>
          <button onClick={() => window.close()} aria-label="Close" className="material-symbols-outlined text-on-surface-variant transition-colors hover:text-primary">close</button>
        </div>
      </header>

      {checking ? (
        <p className="p-lg text-center font-body-sm text-body-sm text-on-surface-variant">Connecting to the engine…</p>
      ) : !online ? (
        <p className="p-lg text-center font-body-sm text-body-sm text-on-surface-variant">Mnemosyne engine is not running.</p>
      ) : (
        <>
          {/* Workspace selector */}
          <div className="border-b border-outline-variant bg-surface-container-low p-md">
            <label className="mb-base block font-label-caps text-label-caps uppercase text-outline">Current Workspace</label>
            <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />
          </div>

          {/* Stat grid */}
          <div className="grid grid-cols-2 gap-px bg-outline-variant">
            <div className="flex flex-col gap-xs bg-surface p-md">
              <span className="font-label-caps text-label-caps uppercase text-outline">Memories</span>
              <span className="font-headline-md text-headline-md text-on-surface">{active?.node_count ?? 0}</span>
            </div>
            <div className="flex flex-col gap-xs bg-surface p-md">
              <div className="flex items-start justify-between">
                <span className={`font-label-caps text-label-caps uppercase ${pending > 0 ? "text-primary" : "text-outline"}`}>Pending</span>
                {pending > 0 && <div className="h-2 w-2 rounded-full bg-primary" />}
              </div>
              <span className={`font-headline-md text-headline-md ${pending > 0 ? "text-primary" : "text-on-surface"}`}>{pending}</span>
            </div>
          </div>

          {/* Toggles */}
          <div className="space-y-gutter border-t border-outline-variant p-md">
            <PillToggle
              label="Capture Active"
              sub={incognito ? "Paused while incognito" : capture ? "Syncing memory state" : "Capture paused"}
              on={capture && !incognito}
              disabled={incognito}
              onToggle={toggleCapture}
            />
            <PillToggle
              label="Incognito Mode"
              sub="Disable persistent storage"
              on={incognito}
              onToggle={toggleIncognito}
            />
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-sm border-t border-outline-variant bg-surface-container-lowest p-md">
            <button onClick={openSidebar} className="flex w-full items-center justify-between rounded-sm bg-primary px-md py-sm font-body-md text-body-md text-on-primary transition-all hover:opacity-90 active:scale-[0.98]">
              <span>Open Sidebar</span>
              <span className="material-symbols-outlined">dock_to_right</span>
            </button>
            <button onClick={openDashboard} className="flex w-full items-center justify-between rounded-sm border border-outline-variant bg-surface-container-highest px-md py-sm font-body-md text-body-md text-on-surface transition-all hover:bg-surface-bright active:scale-[0.98]">
              <span>Memory Audit</span>
              <span className="material-symbols-outlined">analytics</span>
            </button>
          </div>
        </>
      )}

      {/* Footer */}
      <footer className="flex items-center justify-between border-t border-outline-variant bg-surface-container-lowest px-md py-sm">
        <div className="flex items-center gap-xs">
          <span className="material-symbols-outlined text-[14px] text-outline">encrypted</span>
          <span className="font-label-caps text-label-caps uppercase tracking-tighter text-outline">Local only · No data sent</span>
        </div>
        <span className="font-code-md text-[10px] text-on-surface-variant">v1.0.0</span>
      </footer>
    </div>
  )
}

function PillToggle({
  label,
  sub,
  on,
  disabled,
  onToggle,
}: {
  label: string
  sub: string
  on: boolean
  disabled?: boolean
  onToggle: () => void
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex flex-col">
        <span className="font-body-md text-body-md text-on-surface">{label}</span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">{sub}</span>
      </div>
      <button
        role="switch"
        aria-checked={on}
        aria-label={label}
        disabled={disabled}
        onClick={onToggle}
        className={`flex h-6 w-11 items-center rounded-full p-1 transition-colors duration-200 disabled:opacity-50 ${
          on ? "bg-primary-container" : "bg-secondary-container"
        }`}>
        <div className={`h-4 w-4 rounded-sm bg-on-primary-container shadow-sm transition-transform duration-200 ${on ? "translate-x-5" : ""}`} />
      </button>
    </div>
  )
}

export default Popup
