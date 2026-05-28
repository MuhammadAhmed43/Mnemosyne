import { useEffect, useRef, useState } from "react"

import type { Workspace } from "~lib/types"

interface Props {
  workspaces: Workspace[]
  active: Workspace | null
  onChange: (ws: Workspace) => void
}

export function WorkspaceSelector({ workspaces, active, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  return (
    <div className="group relative" ref={ref}>
      <button
        aria-label="Active workspace"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded border border-outline-variant bg-surface-container-high px-sm py-xs transition-all duration-200 hover:bg-surface-container-highest/50">
        <div className="flex min-w-0 items-center gap-sm">
          <div
            className="h-4 w-4 shrink-0 rounded-sm"
            style={{ background: active?.color || "#c2c1ff" }}
          />
          <span className="truncate font-body-sm text-body-sm font-semibold text-on-surface">
            {active?.name ?? "Select workspace"}
          </span>
        </div>
        <span className="material-symbols-outlined text-on-surface-variant">unfold_more</span>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-xs max-h-72 overflow-y-auto rounded border border-outline-variant bg-surface-container-high shadow-2xl backdrop-blur-glass">
          {workspaces.length === 0 && (
            <div className="px-sm py-xs font-body-sm text-body-sm text-on-surface-variant">No workspaces</div>
          )}
          {workspaces.map((w) => {
            const isActive = w.id === active?.id
            return (
              <button
                key={w.id}
                role="option"
                aria-selected={isActive}
                onClick={() => {
                  onChange(w)
                  setOpen(false)
                }}
                className={`flex w-full items-center justify-between gap-sm px-sm py-xs text-left transition-colors hover:bg-surface-container-highest/60 ${
                  isActive ? "bg-secondary-container/30" : ""
                }`}>
                <span className="flex min-w-0 items-center gap-sm">
                  <span className="h-4 w-4 shrink-0 rounded-sm" style={{ background: w.color || "#c2c1ff" }} />
                  <span className="truncate font-body-sm text-body-sm text-on-surface">{w.name}</span>
                </span>
                <span className="shrink-0 font-code-md text-code-md text-on-surface-variant">{w.node_count}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
