import { useEffect, useState } from "react"

interface Action {
  id: string
  label: string
  icon: string
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

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24" onClick={() => setOpen(false)}>
      <div className="w-[420px] rounded-xl border border-border bg-bg-secondary shadow-lg" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSelected(0) }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setSelected((s) => Math.min(s + 1, filtered.length - 1))
            if (e.key === "ArrowUp") setSelected((s) => Math.max(s - 1, 0))
            if (e.key === "Enter" && filtered[selected]) { filtered[selected].run(); setOpen(false) }
          }}
          placeholder="Type a command…"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none"
        />
        <div className="max-h-64 overflow-y-auto">
          {filtered.map((a, i) => (
            <button
              key={a.id}
              onClick={() => { a.run(); setOpen(false) }}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-sm ${
                i === selected ? "bg-bg-hover text-accent" : "text-text-primary"
              }`}
            >
              <span>{a.icon}</span> {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
