import { useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { MemoryNode } from "~lib/types"

import { MemoryNodeCard } from "./MemoryNodeCard"

export function SearchTab({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<MemoryNode[]>([])

  let timer: ReturnType<typeof setTimeout>
  const onChange = (q: string) => {
    setQuery(q)
    clearTimeout(timer)
    if (q.length < 2) {
      setResults([])
      return
    }
    timer = setTimeout(() => {
      api.listNodes(workspaceId, { search: q }).then((r) => setResults(r.nodes))
    }, 300)
  }

  return (
    <div className="p-md">
      <div className="group relative">
        <span className="material-symbols-outlined absolute left-sm top-1/2 -translate-y-1/2 text-[16px] text-outline-variant transition-colors group-focus-within:text-primary">search</span>
        <input
          value={query}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search memories…"
          aria-label="Search memories"
          className="h-9 w-full border border-outline-variant bg-surface-container-low pl-xl pr-md font-body-sm text-body-sm text-on-surface outline-none transition-all placeholder:text-outline/50 focus:border-primary"
        />
      </div>
      <div className="mt-gutter space-y-xs">
        {results.map((n) => (
          <MemoryNodeCard key={n.id} node={n} compact />
        ))}
        {query.length >= 2 && results.length === 0 && (
          <p className="p-md text-center font-body-sm text-body-sm text-on-surface-variant">No memories found for "{query}"</p>
        )}
      </div>
    </div>
  )
}
