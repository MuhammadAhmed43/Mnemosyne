import { useEffect, useState } from "react"

import { nodeColor, nodeLabel } from "~components/NodeTypeBadge"
import type { MnemosyneAPI, ThreadNode, ThreadSummary } from "~lib/api"

function shortSession(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 6).toLowerCase()
}

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

  const selectedThread = threads.find((t) => t.id === selected) ?? null

  const byTurn = nodes.reduce<Record<number, ThreadNode[]>>((acc, n) => {
    ;(acc[n.turn_index] ??= []).push(n)
    return acc
  }, {})

  const exportJson = () => {
    if (!selectedThread) return
    const blob = new Blob([JSON.stringify({ thread: selectedThread, nodes }, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `session-${shortSession(selectedThread.session_id)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Session List */}
      <section className="flex w-[360px] shrink-0 flex-col overflow-hidden border-r border-outline-variant bg-surface-container-lowest">
        <div className="flex items-center justify-between border-b border-outline-variant p-md">
          <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">Recent Sessions</h2>
          <span className="rounded bg-surface-container-highest px-xs py-[1px] font-label-caps text-[10px] uppercase text-primary">{threads.length} Active</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {threads.length === 0 && <p className="p-md font-body-sm text-body-sm text-on-surface-variant">No sessions yet.</p>}
          {threads.map((t) => {
            const isActive = selected === t.id
            return (
              <button
                key={t.id}
                onClick={() => open(t.id)}
                className={`block w-full cursor-pointer border-b border-outline-variant p-md text-left transition-colors hover:bg-surface-container-low ${
                  isActive ? "border-l-2 border-l-primary bg-surface-container-high/40" : ""
                }`}>
                <div className="mb-base flex items-start justify-between">
                  <span className={`font-label-caps text-label-caps uppercase ${isActive ? "text-primary" : "text-on-surface-variant"}`}>
                    Platform: {t.platform}
                  </span>
                  <span className="font-code-md text-[11px] text-outline">#{shortSession(t.session_id)}</span>
                </div>
                <div className="mb-xs flex items-center gap-sm">
                  <span className="material-symbols-outlined text-[14px] text-on-surface-variant">sync_alt</span>
                  <span className={`font-body-md text-body-md text-on-surface ${isActive ? "font-bold" : ""}`}>Session {shortSession(t.session_id)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-label-caps text-[10px] uppercase text-on-surface-variant">{t.turn_count} Turns</span>
                  <span className="font-label-caps text-[10px] uppercase text-outline">{new Date(t.started_at).toLocaleString()}</span>
                </div>
              </button>
            )
          })}
        </div>
      </section>

      {/* Replay Canvas */}
      <section className="relative flex flex-1 flex-col overflow-hidden">
        {!selected || !selectedThread ? (
          <div className="flex flex-1 flex-col items-center justify-center p-xl text-center">
            <div className="mb-md flex h-16 w-16 items-center justify-center rounded-full border border-outline-variant bg-surface-container-low">
              <span className="material-symbols-outlined text-[32px] text-outline-variant">history</span>
            </div>
            <h3 className="mb-xs font-headline-md text-headline-md text-on-surface">No Session Selected</h3>
            <p className="max-w-xs font-body-md text-body-md text-on-surface-variant">
              Select a session from the list to replay its memory extractions and turn-by-turn state changes.
            </p>
          </div>
        ) : (
          <div className="flex h-full flex-col">
            <div className="flex h-12 items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-md">
              <div className="flex items-center gap-sm">
                <span className="font-label-caps text-label-caps uppercase text-primary">Replay: {shortSession(selectedThread.session_id)}</span>
                <span className="text-outline">/</span>
                <span className="font-label-caps text-label-caps uppercase text-on-surface-variant">Logs</span>
              </div>
              <div className="flex gap-sm">
                <button onClick={exportJson} className="rounded border border-outline-variant bg-surface-container-highest px-sm py-1 font-label-caps text-[10px] uppercase transition-all hover:border-primary hover:bg-primary/20">
                  Export JSON
                </button>
              </div>
            </div>

            <div className="flex-1 space-y-lg overflow-y-auto p-lg">
              {Object.entries(byTurn).map(([turn, items]) => (
                <div key={turn} className="space-y-md">
                  <div className="flex items-center gap-md">
                    <span className="border-l border-primary bg-secondary-container px-sm py-1 font-label-caps text-label-caps uppercase text-on-secondary-container">
                      Turn {String(Number(turn) + 1).padStart(2, "0")}
                    </span>
                    <div className="h-px flex-1 bg-outline-variant/30" />
                  </div>
                  <div className="space-y-xs">
                    {items.map((n) => {
                      const color = nodeColor(n.node_type)
                      return (
                        <div key={n.node_id} className="group flex items-start gap-md border border-outline-variant bg-surface-container-low p-sm transition-colors hover:border-primary/50">
                          <span
                            className="w-20 border-l-2 px-xs py-1 font-label-caps text-[10px] uppercase"
                            style={{ borderColor: color, color, backgroundColor: `${color}1a` }}>
                            {nodeLabel(n.node_type)}
                          </span>
                          <p className="flex-1 font-body-md text-body-md text-on-surface-variant">{n.content}</p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
              {nodes.length === 0 && (
                <p className="font-body-sm text-body-sm text-on-surface-variant">No extractions recorded for this session.</p>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
