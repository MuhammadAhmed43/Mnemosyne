import { useEffect, useState } from "react"

import { WorkspaceSelector } from "~components/WorkspaceSelector"
import { useApi } from "~lib/useApi"
import type { Workspace } from "~lib/types"

import "~style.css"

function Popup() {
  const { api, online } = useApi()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [active, setActive] = useState<Workspace | null>(null)
  const [capture, setCapture] = useState(true)
  const [incognito, setIncognito] = useState(false)
  const [pending, setPending] = useState(0)

  useEffect(() => {
    chrome.storage.local.get("capture_enabled").then(({ capture_enabled }) =>
      setCapture(capture_enabled ?? true)
    )
    chrome.storage.session.get("incognito").then(({ incognito }) => setIncognito(incognito === true))
    if (api && online) {
      api.listWorkspaces().then((r) => {
        setWorkspaces(r.workspaces)
        const a = r.workspaces[0] ?? null
        setActive(a)
        if (a) api.getPending(a.id).then((p) => setPending(p.total))
      })
    }
  }, [api, online])

  const toggleCapture = () => {
    const next = !capture
    setCapture(next)
    void chrome.storage.local.set({ capture_enabled: next })
  }

  const toggleIncognito = () => {
    const next = !incognito
    setIncognito(next)
    // storage.session clears on browser close -> incognito is per browser session.
    void chrome.storage.session.set({ incognito: next })
    // Purple badge while active (pollHealth only sets the badge *color*, so this
    // text survives). Cleared when toggled off.
    void chrome.action.setBadgeText({ text: next ? "INC" : "" })
    if (next) void chrome.action.setBadgeBackgroundColor({ color: "#7C3AED" })
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
    <div className="flex w-[400px] flex-col gap-4 bg-bg-primary p-4 text-text-primary">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${online ? "bg-success" : "bg-danger"}`} />
        <span className="text-sm">{online ? "Engine running" : "Engine offline"}</span>
      </div>

      {online && (
        <>
          <WorkspaceSelector workspaces={workspaces} active={active} onChange={setActive} />

          <div className="grid grid-cols-2 gap-3">
            <Stat label="Memories" value={active?.node_count ?? 0} />
            <Stat label="Pending" value={pending} highlight={pending > 0} />
          </div>

          <button
            onClick={toggleCapture}
            disabled={incognito}
            className={`w-full rounded-lg py-3 text-sm font-medium disabled:opacity-50 ${
              capture ? "bg-accent text-white" : "border border-warning text-warning"
            }`}
          >
            {capture ? "Capture Active — Pause" : "Capture Paused — Resume"}
          </button>

          <button
            onClick={toggleIncognito}
            className={`w-full rounded-lg py-2 text-sm font-medium ${
              incognito ? "bg-[#7C3AED] text-white" : "border border-border text-text-secondary hover:text-text-primary"
            }`}
          >
            {incognito ? "Incognito ON — nothing is captured" : "Incognito Mode"}
          </button>

          <div className="space-y-2">
            <Action label="Open Sidebar" onClick={openSidebar} />
            <Action label="Memory Audit" onClick={openDashboard} />
          </div>
        </>
      )}

      <p className="text-center text-xs text-text-tertiary">Local only · No data sent</p>
    </div>
  )
}

function Stat({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`text-xl font-bold ${highlight ? "text-warning" : ""}`}>{value}</p>
    </div>
  )
}

function Action({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full rounded-lg border border-border bg-bg-secondary py-2 text-sm hover:bg-bg-hover">
      {label}
    </button>
  )
}

export default Popup
