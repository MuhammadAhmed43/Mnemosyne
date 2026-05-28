import { useEffect, useState } from "react"

interface Action {
  id: string
  label: string
  icon?: string
  group?: string
  run: () => void
}

export function CommandPalette({ actions }: { actions: Action[] }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((o) => !o)
        setQuery("")
        setSelected(0)
      }
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  if (!open) return null

  const filtered = actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()))
  // Group while preserving order, tracking each item's flat index for keyboard selection.
  const groups: { name: string; items: { a: Action; idx: number }[] }[] = []
  filtered.forEach((a, idx) => {
    const name = a.group ?? "Commands"
    let g = groups.find((x) => x.name === name)
    if (!g) {
      g = { name, items: [] }
      groups.push(g)
    }
    g.items.push({ a, idx })
  })

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-background/60 pt-[120px] backdrop-blur-sm"
      onClick={() => setOpen(false)}>
      <div
        className="flex w-full max-w-lg flex-col overflow-hidden rounded-lg border border-outline-variant bg-surface-container-high shadow-2xl backdrop-blur-glass"
        onClick={(e) => e.stopPropagation()}>
        {/* Search */}
        <div className="flex items-center border-b border-outline-variant px-md py-gutter">
          <span className="material-symbols-outlined mr-sm text-primary">terminal</span>
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelected(0)
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setSelected((s) => Math.min(s + 1, filtered.length - 1))
              if (e.key === "ArrowUp") setSelected((s) => Math.max(s - 1, 0))
              if (e.key === "Enter" && filtered[selected]) {
                filtered[selected].run()
                setOpen(false)
              }
            }}
            placeholder="Type a command or search…"
            className="flex-1 border-none bg-transparent font-body-md text-body-md text-on-surface outline-none placeholder:text-on-surface-variant"
          />
          <kbd className="rounded border border-outline-variant bg-surface px-1 text-[10px] text-on-surface-variant">ESC</kbd>
        </div>

        {/* List */}
        <div className="max-h-[300px] overflow-y-auto p-xs">
          {groups.map((g) => (
            <div key={g.name}>
              <div className="px-md py-xs">
                <span className="font-label-caps text-[9px] uppercase text-on-surface-variant">{g.name}</span>
              </div>
              {g.items.map(({ a, idx }) => (
                <button
                  key={a.id}
                  onMouseEnter={() => setSelected(idx)}
                  onClick={() => {
                    a.run()
                    setOpen(false)
                  }}
                  className={`group flex w-full items-center justify-between px-md py-sm text-left transition-colors ${
                    idx === selected ? "bg-surface" : ""
                  }`}>
                  <div className="flex items-center gap-sm">
                    {a.icon && (
                      <span className={`material-symbols-outlined text-[18px] ${idx === selected ? "text-primary" : "text-on-surface-variant"}`}>
                        {a.icon}
                      </span>
                    )}
                    <span className="font-body-sm text-body-sm text-on-surface">{a.label}</span>
                  </div>
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-md py-sm font-body-sm text-body-sm text-on-surface-variant">No matching commands.</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-outline-variant bg-surface-container-highest p-sm">
          <div className="flex gap-md">
            <div className="flex items-center gap-xs">
              <kbd className="rounded border border-outline-variant px-1 text-[9px] text-on-surface-variant">↑↓</kbd>
              <span className="text-[10px] text-on-surface-variant">Navigate</span>
            </div>
            <div className="flex items-center gap-xs">
              <kbd className="rounded border border-outline-variant px-1 text-[9px] text-on-surface-variant">↵</kbd>
              <span className="text-[10px] text-on-surface-variant">Select</span>
            </div>
          </div>
          <span className="font-code-md text-[10px] text-on-surface-variant">CMD_PALETTE</span>
        </div>
      </div>
    </div>
  )
}
