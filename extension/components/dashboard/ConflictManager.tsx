import { useEffect, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { Conflict } from "~lib/types"

export function ConflictManager({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [conflicts, setConflicts] = useState<Conflict[]>([])

  const load = () => {
    void api.getConflicts(workspaceId, "pending").then((r) => setConflicts(r.conflicts))
  }
  useEffect(load, [api, workspaceId])

  const resolve = async (c: Conflict, strategy: string) => {
    await api.resolveConflict(workspaceId, c.id, { strategy })
    setConflicts((prev) => prev.filter((x) => x.id !== c.id))
  }

  return (
    <div className="max-w-4xl p-8">
      <h1 className="mb-6 text-2xl font-bold">Conflict Manager</h1>
      {conflicts.length === 0 && <p className="text-sm text-text-secondary">No pending conflicts.</p>}
      <div className="space-y-3">
        {conflicts.map((c) => (
          <div key={c.id} className="rounded-lg border border-warning bg-bg-secondary p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{c.conflict_type}</span>
              <span className="text-xs text-text-secondary">
                contradiction {Math.round(c.contradiction_score * 100)}%
              </span>
            </div>
            <p className="mb-3 font-mono text-xs text-text-secondary">
              A: {c.node_a_id.slice(0, 14)} ↔ B: {c.node_b_id.slice(0, 14)}
            </p>
            <div className="flex gap-2">
              <button className="rounded bg-accent px-3 py-1 text-xs text-white" onClick={() => resolve(c, "keep_a")}>Keep A</button>
              <button className="rounded bg-accent px-3 py-1 text-xs text-white" onClick={() => resolve(c, "keep_b")}>Keep B</button>
              <button className="rounded border border-border px-3 py-1 text-xs text-text-secondary" onClick={() => resolve(c, "merge")}>Both valid</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
