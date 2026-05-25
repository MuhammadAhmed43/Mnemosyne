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
    <div className="p-3">
      <input
        value={query}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search memories…"
        className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary"
      />
      <div className="mt-3 space-y-2">
        {results.map((n) => (
          <MemoryNodeCard key={n.id} node={n} compact />
        ))}
        {query.length >= 2 && results.length === 0 && (
          <p className="p-4 text-center text-sm text-text-secondary">No memories found for "{query}"</p>
        )}
      </div>
    </div>
  )
}
