import { useEffect, useState } from "react"

import { NodeTypeBadge } from "~components/NodeTypeBadge"
import type { MnemosyneAPI, ThreadNode, ThreadSummary } from "~lib/api"

export function SessionReplay({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [nodes, setNodes] = useState<ThreadNode[]>([])

  useEffect(() => {
    api.getThreads(workspaceId).then((r) => setThreads(r.threads))
  }, [api, workspaceId])

  const open = (id: string) => {
    setSelected(id)
    api.getThreadNodes(workspaceId, id).then((r) => setNodes(r.nodes))
  }

  const byTurn = nodes.reduce<Record<number, ThreadNode[]>>((acc, n) => {
    ;(acc[n.turn_index] ??= []).push(n)
    return acc
  }, {})

  return (
    <div className="flex h-full">
      <div className="w-[300px] overflow-y-auto border-r border-border">
        {threads.length === 0 && <p className="p-4 text-sm text-text-secondary">No sessions yet.</p>}
        {threads.map((t) => (
          <button
            key={t.id}
            onClick={() => open(t.id)}
            className={`block w-full border-b border-border p-3 text-left text-sm ${
              selected === t.id ? "bg-bg-hover text-accent" : "text-text-primary hover:bg-bg-hover"
            }`}
          >
            <div className="font-medium">{t.platform}</div>
            <div className="text-xs text-text-secondary">
              {t.turn_count} turns · {new Date(t.started_at).toLocaleString()}
            </div>
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {!selected ? (
          <p className="text-text-secondary">Select a session to replay its extractions.</p>
        ) : (
          Object.entries(byTurn).map(([turn, items]) => (
            <div key={turn} className="mb-6">
              <h3 className="mb-2 text-xs text-text-tertiary">Turn {Number(turn) + 1}</h3>
              {items.map((n) => (
                <div key={n.node_id} className="mb-2 flex items-center gap-2 rounded border border-border bg-bg-secondary p-2 text-sm">
                  <NodeTypeBadge type={n.node_type} /> {n.content}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
