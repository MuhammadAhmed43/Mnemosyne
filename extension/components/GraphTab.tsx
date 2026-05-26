import cytoscape from "cytoscape"
import cola from "cytoscape-cola"
import { useEffect, useRef, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { Workspace } from "~lib/types"

cytoscape.use(cola)

const NODE_COLORS: Record<string, string> = {
  goal: "#10B981", decision: "#7C3AED", technical_fact: "#6B7280", problem: "#EF4444",
  entity: "#F59E0B", preference: "#EC4899", task: "#3B82F6", event: "#14B8A6",
  insight: "#A855F7", user_note: "#22D3EE", open_question: "#F97316",
}

const ADDABLE_TYPES = ["user_note", "goal", "decision", "task", "problem", "technical_fact", "preference", "insight"]

interface GraphNode { id: string; label: string; type: string; importance: number }
interface GraphEdge { id: string; source: string; target: string }
interface Selected { id: string; label: string; type: string; importance: number }

export function GraphTab({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<Selected | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [empty, setEmpty] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addType, setAddType] = useState("user_note")
  const [addText, setAddText] = useState("")
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState("")
  const [moving, setMoving] = useState(false)
  const [otherWs, setOtherWs] = useState<Workspace[]>([])
  const reload = () => { setSelected(null); setEditing(false); setMoving(false); setReloadKey((k) => k + 1) }

  useEffect(() => {
    if (!ref.current) return
    let cy: cytoscape.Core | undefined
    api.getGraph(workspaceId).then((data) => {
      const nodes = data.nodes as unknown as GraphNode[]
      const edges = data.edges as unknown as GraphEdge[]
      setEmpty(nodes.length === 0)
      if (!ref.current || nodes.length === 0) return
      cy = cytoscape({
        container: ref.current,
        elements: [
          ...nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, importance: n.importance } })),
          ...edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target } })),
        ],
        layout: { name: "cola", animate: true } as cytoscape.LayoutOptions,
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color": (el: cytoscape.NodeSingular) => NODE_COLORS[el.data("type")] ?? "#7C3AED",
              width: (el: cytoscape.NodeSingular) => 20 + el.data("importance") * 30,
              height: (el: cytoscape.NodeSingular) => 20 + el.data("importance") * 30,
              "font-size": "9px", color: "#E4E4E7", "text-wrap": "wrap", "text-max-width": "80px",
            },
          },
          { selector: "node:selected", style: { "border-width": 3, "border-color": "#fff" } },
          {
            selector: "edge",
            style: { width: 1.5, "line-color": "#3A3A4E", "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": "#3A3A4E" },
          },
        ],
      })
      cy.on("tap", "node", (evt) => {
        const d = evt.target.data()
        setSelected({ id: d.id, label: d.label, type: d.type, importance: d.importance })
      })
      cy.on("tap", (evt) => { if (evt.target === cy) setSelected(null) }) // click background to deselect
    })
    return () => cy?.destroy()
  }, [api, workspaceId, reloadKey])

  const del = async () => {
    if (!selected) return
    await api.deleteNode(workspaceId, selected.id)
    reload()
  }
  const boost = async () => {
    if (!selected) return
    await api.boostNode(workspaceId, selected.id, 0.2)
    reload()
  }
  const addNode = async () => {
    if (!addText.trim()) return
    await api.createNode(workspaceId, { node_type: addType, content: addText.trim() })
    setAddText(""); setAdding(false); reload()
  }
  const startEdit = async () => {
    if (!selected) return
    // The graph only carries a truncated label; fetch the full content to edit.
    const full = await api.getNode(workspaceId, selected.id).catch(() => null)
    setEditText(full?.node?.content ?? selected.label)
    setEditing(true)
  }
  const saveEdit = async () => {
    if (!selected || !editText.trim()) return
    await api.updateNode(workspaceId, selected.id, { content: editText.trim() })
    reload()
  }
  const startMove = async () => {
    const r = await api.listWorkspaces().catch(() => ({ workspaces: [] }))
    setOtherWs((r.workspaces ?? []).filter((w) => w.id !== workspaceId))
    setMoving(true)
  }
  const doMove = async (targetId: string) => {
    if (!selected || !targetId) return
    await api.moveNode(workspaceId, selected.id, targetId)
    reload()
  }

  return (
    <div className="relative h-full w-full">
      {/* toolbar */}
      <div className="absolute left-3 top-3 z-10 flex gap-2">
        <button onClick={() => setAdding((v) => !v)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white">+ Add memory</button>
        <button onClick={reload} className="rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary">↻ Refresh</button>
      </div>

      {adding && (
        <div className="absolute left-3 top-12 z-10 w-72 space-y-2 rounded-lg border border-border bg-bg-secondary p-3 shadow-xl">
          <select value={addType} onChange={(e) => setAddType(e.target.value)} className="w-full rounded border border-border bg-bg-tertiary px-2 py-1 text-xs">
            {ADDABLE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <textarea value={addText} onChange={(e) => setAddText(e.target.value)} placeholder="Memory content…" rows={3} className="w-full rounded border border-border bg-bg-tertiary px-2 py-1 text-xs" />
          <div className="flex gap-2">
            <button onClick={addNode} className="flex-1 rounded bg-accent py-1 text-xs font-medium text-white">Save</button>
            <button onClick={() => setAdding(false)} className="rounded border border-border px-3 py-1 text-xs text-text-secondary">Cancel</button>
          </div>
        </div>
      )}

      {/* node detail drawer */}
      {selected && (
        <div className="absolute right-3 top-3 z-10 w-72 space-y-2 rounded-lg border border-border bg-bg-secondary p-3 shadow-xl">
          <div className="flex items-center justify-between">
            <div className="text-[11px] uppercase text-text-tertiary">{selected.type}</div>
            <button onClick={() => { setSelected(null); setEditing(false) }} className="text-xs text-text-tertiary hover:text-text-primary">✕</button>
          </div>
          {editing ? (
            <>
              <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={4} className="w-full rounded border border-border bg-bg-tertiary px-2 py-1 text-xs" />
              <div className="flex gap-2">
                <button onClick={saveEdit} className="flex-1 rounded bg-accent py-1 text-xs font-medium text-white">Save</button>
                <button onClick={() => setEditing(false)} className="rounded border border-border px-3 py-1 text-xs text-text-secondary">Cancel</button>
              </div>
            </>
          ) : moving ? (
            <>
              <p className="text-xs text-text-secondary">Move this memory to:</p>
              <select
                defaultValue=""
                onChange={(e) => doMove(e.target.value)}
                className="w-full rounded border border-border bg-bg-tertiary px-2 py-1 text-xs"
              >
                <option value="" disabled>Choose a workspace…</option>
                {otherWs.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
              {otherWs.length === 0 && <p className="text-[11px] text-text-tertiary">No other workspaces — create one first.</p>}
              <button onClick={() => setMoving(false)} className="w-full rounded border border-border py-1 text-xs text-text-secondary">Cancel</button>
            </>
          ) : (
            <>
              <p className="text-sm text-text-primary">{selected.label}</p>
              <p className="text-xs text-text-secondary">importance {selected.importance.toFixed(2)}</p>
              <div className="flex gap-2 pt-1">
                <button onClick={startEdit} className="flex-1 rounded border border-border py-1 text-xs hover:text-accent">✎ Edit</button>
                <button onClick={boost} className="flex-1 rounded border border-border py-1 text-xs hover:text-accent">↑ Boost</button>
                <button onClick={del} className="flex-1 rounded border border-danger py-1 text-xs text-danger hover:bg-danger hover:text-white">Delete</button>
              </div>
              <button onClick={startMove} className="w-full rounded border border-border py-1 text-xs text-text-secondary hover:text-accent">⇄ Move to another workspace</button>
            </>
          )}
        </div>
      )}

      {empty && <div className="flex h-full items-center justify-center text-sm text-text-secondary">No memories in this workspace yet.</div>}
      <div ref={ref} className="h-full w-full" />
    </div>
  )
}
