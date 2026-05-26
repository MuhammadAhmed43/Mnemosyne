import cytoscape from "cytoscape"
import cola from "cytoscape-cola"
import { useEffect, useRef, useState } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { Workspace } from "~lib/types"

cytoscape.use(cola)

const NODE_COLORS: Record<string, string> = {
  goal: "#34D399", decision: "#818CF8", technical_fact: "#94A3B8", problem: "#FB7185",
  entity: "#FBBF24", preference: "#F472B6", task: "#60A5FA", event: "#2DD4BF",
  insight: "#A78BFA", user_note: "#38BDF8", open_question: "#FB923C",
  hypothesis: "#C084FC", constraint: "#F87171",
}

const TYPE_LABEL: Record<string, string> = {
  goal: "Goal", decision: "Decision", technical_fact: "Tech fact", problem: "Problem",
  entity: "Entity", preference: "Preference", task: "Task", event: "Event",
  insight: "Insight", user_note: "Note", open_question: "Question",
  hypothesis: "Hypothesis", constraint: "Constraint",
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
  const [legendTypes, setLegendTypes] = useState<string[]>([])
  const reload = () => { setSelected(null); setEditing(false); setMoving(false); setReloadKey((k) => k + 1) }

  useEffect(() => {
    if (!ref.current) return
    let cy: cytoscape.Core | undefined
    api.getGraph(workspaceId).then((data) => {
      const nodes = data.nodes as unknown as GraphNode[]
      const edges = data.edges as unknown as GraphEdge[]
      setEmpty(nodes.length === 0)
      setLegendTypes([...new Set(nodes.map((n) => n.type))])
      if (!ref.current || nodes.length === 0) return
      cy = cytoscape({
        container: ref.current,
        minZoom: 0.25,
        maxZoom: 2.5,
        elements: [
          ...nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, importance: n.importance } })),
          ...edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target } })),
        ],
        // Force-directed layout for structure; importance is encoded via node size.
        layout: { name: "cola", animate: true, nodeSpacing: 14, edgeLength: 130, avoidOverlap: true, maxSimulationTime: 2500, randomize: false } as cytoscape.LayoutOptions,
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color": (el: cytoscape.NodeSingular) => NODE_COLORS[el.data("type")] ?? "#94A3B8",
              // Size = importance: the more important the memory, the bigger the dot.
              width: (el: cytoscape.NodeSingular) => 22 + el.data("importance") * 48,
              height: (el: cytoscape.NodeSingular) => 22 + el.data("importance") * 48,
              "font-size": (el: cytoscape.NodeSingular) => `${9 + el.data("importance") * 5}px`,
              color: "#E6EAF2",
              "text-valign": "bottom", "text-halign": "center", "text-margin-y": 4,
              "text-wrap": "wrap", "text-max-width": "120px",
              // Crisp labels over any background; hidden when zoomed out (declutter).
              "text-outline-width": 2, "text-outline-color": "#0D1117",
              "min-zoomed-font-size": 7,
              "border-width": 1, "border-color": "#0D1117",
            },
          },
          // Important nodes get a bright halo so they pop at a glance.
          { selector: "node[importance >= 0.8]", style: { "border-width": 3, "border-color": "#E6EAF2", "border-opacity": 0.9 } },
          { selector: "node:selected", style: { "border-width": 4, "border-color": "#4D7CFE", "border-opacity": 1 } },
          {
            selector: "edge",
            style: {
              width: 1.2, "line-color": "#3B4757", "line-opacity": 0.55, "curve-style": "bezier",
              "target-arrow-shape": "triangle", "target-arrow-color": "#3B4757", "arrow-scale": 0.8,
            },
          },
          { selector: ".mn-faded", style: { opacity: 0.12, "text-opacity": 0.05 } },
        ],
      })
      cy.on("tap", "node", (evt) => {
        const d = evt.target.data()
        setSelected({ id: d.id, label: d.label, type: d.type, importance: d.importance })
      })
      cy.on("tap", (evt) => { if (evt.target === cy) setSelected(null) }) // click background to deselect
      // Hover a node -> spotlight it + its neighbours, fade the rest (readability).
      cy.on("mouseover", "node", (evt) => {
        cy?.elements().addClass("mn-faded")
        evt.target.closedNeighborhood().removeClass("mn-faded")
      })
      cy.on("mouseout", "node", () => cy?.elements().removeClass("mn-faded"))
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
        <button onClick={reload} className="rounded-lg border border-border bg-bg-secondary px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary">Refresh</button>
      </div>

      {adding && (
        <div className="absolute left-3 top-12 z-10 w-72 space-y-2 rounded-lg border border-border bg-bg-secondary/80 p-3 shadow-xl backdrop-blur-md">
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
        <div className="absolute right-3 top-3 z-10 w-72 space-y-2 rounded-lg border border-border bg-bg-secondary/80 p-3 shadow-xl backdrop-blur-md">
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
                <button onClick={startEdit} className="flex-1 rounded border border-border py-1 text-xs hover:text-accent">Edit</button>
                <button onClick={boost} className="flex-1 rounded border border-border py-1 text-xs hover:text-accent">Boost</button>
                <button onClick={del} className="flex-1 rounded border border-danger py-1 text-xs text-danger hover:bg-danger hover:text-white">Delete</button>
              </div>
              <button onClick={startMove} className="w-full rounded border border-border py-1 text-xs text-text-secondary hover:text-accent">Move to another workspace</button>
            </>
          )}
        </div>
      )}

      {/* Legend — what the colors and sizes mean. */}
      {!empty && legendTypes.length > 0 && (
        <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-border bg-bg-secondary/90 p-2.5 text-[10px] shadow-lg backdrop-blur">
          <div className="mb-1.5 font-semibold uppercase tracking-wide text-text-secondary">Legend</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {legendTypes.map((t) => (
              <div key={t} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS[t] ?? "#94A3B8" }} />
                <span className="text-text-secondary">{TYPE_LABEL[t] ?? t}</span>
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 border-t border-border pt-1.5 text-text-tertiary">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-text-tertiary" />
            <span className="inline-block h-3 w-3 rounded-full bg-text-tertiary" />
            <span>larger = more important</span>
          </div>
        </div>
      )}

      {empty && <div className="flex h-full items-center justify-center text-sm text-text-secondary">No memories in this workspace yet.</div>}
      <div ref={ref} className="h-full w-full" />
    </div>
  )
}
