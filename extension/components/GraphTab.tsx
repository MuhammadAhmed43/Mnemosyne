import cytoscape from "cytoscape"
import cola from "cytoscape-cola"
import { Suspense, lazy, useEffect, useRef, useState } from "react"

import { NODE_COLORS, nodeLabel } from "~components/NodeTypeBadge"
import type { MnemosyneAPI } from "~lib/api"
import { showToast } from "~lib/toast"
import type { Workspace } from "~lib/types"

cytoscape.use(cola)

// Lazy-load the 3D explorer so its three.js + force-graph bundle (~700KB)
// only downloads when the user toggles into 3D mode.
const Graph3DMode = lazy(() => import("~components/Graph3DMode").then((m) => ({ default: m.Graph3DMode })))

const ADDABLE_TYPES = ["user_note", "goal", "decision", "task", "problem", "technical_fact", "preference", "insight"]

interface GraphNode { id: string; label: string; type: string; importance: number }
interface GraphEdge { id: string; source: string; target: string }
interface Selected { id: string; label: string; type: string; importance: number }
interface Overlay { id: string; label: string; type: string; importance: number; x: number; y: number; size: number; hub: boolean }

function shortId(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 6).toUpperCase()
}

/** Ambient "cosmic web" backdrop — drifting particles + delicate white connection
 * lines, matching the Stitch Intricate Memory Graph aesthetic. Sits behind the
 * real data graph and has no interaction beyond a faint mouse-attraction line. */
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    const parent = canvas?.parentElement as HTMLElement | null
    if (!canvas || !parent) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    interface P { x: number; y: number; vx: number; vy: number; r: number; hub: boolean }
    let particles: P[] = []
    let width = 0
    let height = 0
    let raf = 0
    let dpr = 1
    const mouse = { x: -1, y: -1 }

    const resize = () => {
      const r = parent.getBoundingClientRect()
      dpr = Math.min(2, window.devicePixelRatio || 1)
      width = Math.max(1, r.width)
      height = Math.max(1, r.height)
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // Density scales with area; side panel ~50, full dashboard ~180.
      const count = Math.max(50, Math.min(200, Math.floor((width * height) / 4500)))
      particles = Array.from({ length: count }, () => {
        const hub = Math.random() > 0.95
        return {
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.2,
          vy: (Math.random() - 0.5) * 0.2,
          hub,
          r: hub ? Math.random() * 2 + 2 : Math.random() * 1 + 0.5,
        }
      })
    }

    const onMove = (e: MouseEvent) => {
      const r = parent.getBoundingClientRect()
      mouse.x = e.clientX - r.left
      mouse.y = e.clientY - r.top
    }
    const onLeave = () => { mouse.x = -1; mouse.y = -1 }

    const draw = () => {
      ctx.clearRect(0, 0, width, height)
      // Move particles
      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > width) p.vx = -p.vx
        if (p.y < 0 || p.y > height) p.vy = -p.vy
      }
      // Inter-particle connection lines
      ctx.lineWidth = 0.5
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i]
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < 120 * 120) {
            const d = Math.sqrt(d2)
            ctx.strokeStyle = `rgba(255,255,255,${0.1 - d / 1200})`
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
        // Mouse pull-line (subtle interactive feel from Stitch)
        if (mouse.x >= 0) {
          const dx = a.x - mouse.x
          const dy = a.y - mouse.y
          const d2 = dx * dx + dy * dy
          if (d2 < 150 * 150) {
            const d = Math.sqrt(d2)
            ctx.strokeStyle = `rgba(255,255,255,${0.15 - d / 1000})`
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(mouse.x, mouse.y)
            ctx.stroke()
          }
        }
      }
      // Particles on top of lines
      for (const p of particles) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = p.hub ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.4)"
        ctx.fill()
      }
      raf = requestAnimationFrame(draw)
    }

    resize()
    draw()
    const ro = new ResizeObserver(resize)
    ro.observe(parent)
    parent.addEventListener("mousemove", onMove)
    parent.addEventListener("mouseleave", onLeave)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      parent.removeEventListener("mousemove", onMove)
      parent.removeEventListener("mouseleave", onLeave)
    }
  }, [])
  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 z-0" />
}

export function GraphTab({ api, workspaceId }: { api: MnemosyneAPI; workspaceId: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core>()
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>()
  const [overlay, setOverlay] = useState<Overlay[]>([])
  // Hover-to-spotlight: after 0.5s on a node, only it + its neighbourhood stay lit.
  const [spotlight, setSpotlight] = useState<string | null>(null)
  const [visibleIds, setVisibleIds] = useState<Set<string> | null>(null)
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
  const [search, setSearch] = useState("")
  // 2D constellation (cytoscape) vs 3D explorer (force-graph-3d) — daily-driver
  // is 2D; 3D is a novelty mode for orbiting dense graphs.
  const [mode, setMode] = useState<"2d" | "3d">("2d")
  // Lifted graph data so 2D and 3D modes can share the same fetch result.
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[]; hubId: string | null } | null>(null)
  const reload = () => { setSelected(null); setEditing(false); setMoving(false); setSpotlight(null); setOverlay([]); setGraphData(null); setReloadKey((k) => k + 1) }

  // Fetch graph data once per workspace/reload. Both 2D and 3D modes consume
  // this state — cytoscape and force-graph-3d are downstream from it.
  useEffect(() => {
    let cancelled = false
    api.getGraph(workspaceId).then((data) => {
      if (cancelled) return
      const nodes = data.nodes as unknown as GraphNode[]
      const edges = data.edges as unknown as GraphEdge[]
      setEmpty(nodes.length === 0)
      setLegendTypes([...new Set(nodes.map((n) => n.type))])
      const hubId = nodes.length > 0
        ? nodes.reduce((a, b) => ((b.importance ?? 0) > (a.importance ?? 0) ? b : a), nodes[0]).id
        : null
      setGraphData({ nodes, edges, hubId })
    })
    return () => { cancelled = true }
  }, [api, workspaceId, reloadKey])

  // 2D constellation: cytoscape + cola layout. Only runs when we're actually
  // showing 2D *and* we have data — keeps the canvas off the DOM in 3D mode.
  useEffect(() => {
    if (mode !== "2d") return
    if (!ref.current || !graphData || graphData.nodes.length === 0) return
    let cy: cytoscape.Core | undefined
    let raf = 0
    {
      const { nodes, edges, hubId } = graphData
      cy = cytoscape({
        container: ref.current,
        minZoom: 0.08,
        maxZoom: 2.5,
        wheelSensitivity: 0.25,
        elements: [
          ...nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, importance: n.importance ?? 0.5 } })),
          ...edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target } })),
        ],
        // Roomier layout so dozens of nodes don't pile up; spacing scales a little with count.
        layout: {
          name: "cola", animate: true, avoidOverlap: true, randomize: false,
          nodeSpacing: 90, edgeLength: 160 + Math.min(nodes.length, 60) * 2,
          maxSimulationTime: 3500,
        } as cytoscape.LayoutOptions,
        style: [
          {
            // Nodes are invisible in the canvas — the HTML overlay draws the
            // Stitch-style circles. We keep them sized so layout spacing +
            // edge endpoints are correct.
            selector: "node",
            style: {
              opacity: 0,
              width: (el: cytoscape.NodeSingular) => 16 + el.data("importance") * 28,
              height: (el: cytoscape.NodeSingular) => 16 + el.data("importance") * 28,
            },
          },
          {
            // Delicate white edges — visible against the starfield without
            // dominating the node colour or the hub glow.
            selector: "edge",
            style: {
              width: 0.7, "line-color": "#ffffff", "line-opacity": 0.22,
              "curve-style": "straight", "target-arrow-shape": "none",
            },
          },
        ],
      })
      cyRef.current = cy

      const cyc = cy
      const sync = () => {
        const zoom = cyc.zoom()
        setOverlay(
          cyc.nodes().map((n) => {
            const p = n.renderedPosition()
            const d = n.data()
            return {
              id: d.id, label: d.label, type: d.type, importance: d.importance,
              x: p.x, y: p.y, size: n.width() * zoom, hub: d.id === hubId,
            }
          }),
        )
      }
      // Only follow positions while the layout is animating (a self-stopping rAF
      // loop) and on explicit pan/zoom/resize — NOT on cytoscape's "render" event,
      // which fires on every mouse move and caused the whole overlay to re-render.
      const loop = () => { sync(); raf = requestAnimationFrame(loop) }
      const stopLoop = () => { if (raf) { cancelAnimationFrame(raf); raf = 0 } }
      loop()
      cy.on("layoutstop", () => { stopLoop(); cyc.fit(undefined, 40); sync() })
      cy.on("pan zoom resize", sync)
      cy.on("tap", (evt) => { if (evt.target === cyc) setSelected(null) }) // click background to deselect
      // Safety: stop the loop even if layoutstop is missed.
      setTimeout(() => { stopLoop(); sync() }, 5000)
    }
    return () => {
      if (raf) cancelAnimationFrame(raf)
      cyRef.current = undefined
      cy?.destroy()
    }
  }, [mode, graphData])

  // Apply the spotlight: compute the hovered node's neighbourhood, dim the rest.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    if (!spotlight) {
      cy.edges().stop().animate({ style: { "line-opacity": 0.22 } }, { duration: 300 })
      setVisibleIds(null)
      return
    }
    const node = cy.getElementById(spotlight)
    if (node.empty()) return
    const hood = node.closedNeighborhood()
    setVisibleIds(new Set<string>(hood.nodes().map((n) => n.id())))
    cy.edges().forEach((e) => {
      e.stop().animate({ style: { "line-opacity": hood.contains(e) ? 0.5 : 0.05 } }, { duration: 300 })
    })
  }, [spotlight, overlay.length])

  useEffect(() => () => clearTimeout(hoverTimer.current), [])

  const enterNode = (id: string) => {
    clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setSpotlight(id), 500)
  }
  const leaveNode = () => {
    clearTimeout(hoverTimer.current)
    setSpotlight(null)
  }

  const del = async () => {
    if (!selected) return
    await api.deleteNode(workspaceId, selected.id)
    reload()
  }
  const boost = async () => {
    if (!selected) return
    try {
      const r = (await api.boostNode(workspaceId, selected.id, 0.2)) as { importance_score?: number }
      showToast(`Boosted "${nodeLabel(selected.type)}"`, {
        sub: typeof r?.importance_score === "number" ? `Importance now ${Math.round(r.importance_score * 100)}%` : undefined,
      })
    } catch {
      showToast("Boost failed — is the engine running?", { error: true })
    }
    reload()
  }
  const addNode = async () => {
    if (!addText.trim()) return
    await api.createNode(workspaceId, { node_type: addType, content: addText.trim() })
    setAddText(""); setAdding(false); reload()
  }
  const startEdit = async () => {
    if (!selected) return
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
  const zoomBy = (factor: number) => {
    const cy = cyRef.current
    if (!cy) return
    const level = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), cy.zoom() * factor))
    cy.zoom({ level, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }
  const fitGraph = () => cyRef.current?.fit(undefined, 40)

  // Lowercased search query; nodes whose label doesn't contain it get dimmed.
  const q = search.trim().toLowerCase()

  return (
    <div className="relative min-h-0 flex-1 overflow-hidden" style={{ backgroundColor: "#1c1c1e" }}>
      {/* Ambient cosmic-web particle backdrop — 2D only. The 3D mode uses a
          plain solid backdrop; mounting the field behind a transparent WebGL
          canvas would let the DOM particles leak through. */}
      {mode === "2d" && <ParticleField />}

      {/* 3D mode: react-force-graph WebGL canvas (lazy-loaded) */}
      {mode === "3d" && !empty && graphData && (
        <div className="absolute inset-0 z-[1]">
          <Suspense fallback={
            <div className="flex h-full w-full items-center justify-center font-label-caps text-label-caps uppercase text-on-surface-variant">
              <span className="material-symbols-outlined mr-sm animate-spin text-[18px]">progress_activity</span>
              Loading 3D explorer…
            </div>
          }>
            <Graph3DMode
              nodes={graphData.nodes}
              edges={graphData.edges}
              hubId={graphData.hubId}
              search={search}
              onSelect={(s) => setSelected(s)}
            />
          </Suspense>
        </div>
      )}

      {/* 2D mode: cytoscape canvas (edges + layout + pan/zoom) */}
      <div ref={ref} className={`absolute inset-0 z-[1] h-full w-full ${mode === "3d" ? "hidden" : ""}`} />

      {/* Stitch node overlay (plain circles + labels), synced to cytoscape positions */}
      <div className={`pointer-events-none absolute inset-0 z-[2] ${mode === "3d" ? "hidden" : ""}`}>
        {overlay.map((n, i) => {
          const color = NODE_COLORS[n.type] ?? "#e4e4e7"
          const isSel = selected?.id === n.id
          // Keep a sensible minimum so dots stay clickable + labels stay legible
          // even when you zoom out. Hub gets a tiny bump so it reads as "alpha".
          const baseMin = n.hub ? 16 : 10
          const size = Math.max(baseMin, Math.min(28, n.size))
          const inHood = visibleIds?.has(n.id) ?? false
          // Label fade: hide labels of tiny non-spotlighted nodes to declutter.
          const labelOpacity = spotlight ? (inHood ? 1 : 0) : n.size >= 18 ? 1 : 0
          const matchesSearch = q === "" || n.label.toLowerCase().includes(q)
          const dimmed =
            (visibleIds && !visibleIds.has(n.id)) ||
            (q !== "" && !matchesSearch)
          return (
            <div
              key={n.id}
              className="absolute"
              style={{
                left: n.x, top: n.y, transform: "translate(-50%, -50%)",
                opacity: dimmed ? 0.12 : 1,
                filter: dimmed ? "blur(1px)" : "none",
                transition: "opacity 300ms ease, filter 300ms ease",
              }}>
              {/* Inner wrapper carries the float animation, desynced per node. */}
              <div
                className="mn-float flex flex-col items-center"
                style={{ animationDelay: `${-(i % 9) * 0.7}s`, animationDuration: `${5.5 + (i % 5) * 0.6}s` }}>
                <button
                  onMouseEnter={() => enterNode(n.id)}
                  onMouseLeave={leaveNode}
                  onClick={() => setSelected({ id: n.id, label: n.label, type: n.type, importance: n.importance })}
                  aria-label={n.label}
                  className="pointer-events-auto rounded-full transition-transform duration-300 hover:scale-125"
                  style={{
                    width: size, height: size,
                    // Radial-gradient gives each node a subtle spherical feel
                    // (highlight at upper-left, body color, darker rim) so the
                    // 2D canvas reads with the same depth as the 3D mode.
                    background: n.hub
                      ? "radial-gradient(circle at 30% 30%, #ffffff 0%, #f8f8ff 55%, #c8c8e0 100%)"
                      : `radial-gradient(circle at 30% 30%, ${color}ff 0%, ${color}cc 60%, ${color}88 100%)`,
                    outline: isSel ? "2px solid #c2c1ff" : "none",
                    outlineOffset: "3px",
                    boxShadow: n.hub
                      ? "0 0 22px 6px rgba(255,255,255,0.45), inset 0 0 6px rgba(255,255,255,0.6)"
                      : isSel
                        ? `0 0 14px ${color}aa, inset 0 0 4px ${color}88`
                        : `0 0 8px ${color}55`,
                  }}
                />
                <div
                  className="mt-xs flex flex-col items-center text-center"
                  style={{ width: Math.max(96, size * 4), opacity: labelOpacity, transition: "opacity 250ms ease" }}>
                  <span
                    className="line-clamp-2 font-code-md text-[10px] leading-tight text-on-surface-variant"
                    style={{ textShadow: "0 1px 4px #121317, 0 0 2px #121317" }}>
                    {n.label}
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Top-left controls: Add Memory, Refresh, 2D/3D toggle, Search */}
      <div className="absolute left-md top-md z-10 flex flex-col gap-sm">
        <div className="flex gap-xs">
          <button
            onClick={() => setAdding((v) => !v)}
            className="flex h-8 items-center gap-xs rounded border border-outline-variant bg-surface-container-high/80 px-md font-label-caps text-label-caps uppercase text-on-surface backdrop-blur-glass transition-colors hover:bg-surface-container-highest">
            <span className="material-symbols-outlined text-[16px]">add</span>
            Add Memory
          </button>
          <button
            onClick={reload}
            aria-label="Refresh"
            className="flex h-8 items-center gap-xs rounded border border-outline-variant bg-surface-container-high/80 px-sm font-label-caps text-label-caps uppercase text-on-surface backdrop-blur-glass transition-colors hover:bg-surface-container-highest">
            <span className="material-symbols-outlined text-[16px]">refresh</span>
          </button>
          <button
            onClick={() => setMode((m) => (m === "2d" ? "3d" : "2d"))}
            aria-label={`Switch to ${mode === "2d" ? "3D" : "2D"} view`}
            aria-pressed={mode === "3d"}
            title={mode === "2d" ? "Switch to 3D explorer" : "Switch to 2D constellation"}
            className={`flex h-8 items-center gap-xs rounded border px-md font-label-caps text-label-caps uppercase backdrop-blur-glass transition-colors ${
              mode === "3d"
                ? "border-primary/60 bg-primary/20 text-primary hover:bg-primary/30"
                : "border-outline-variant bg-surface-container-high/80 text-on-surface hover:bg-surface-container-highest"
            }`}>
            <span className="material-symbols-outlined text-[16px]" style={{ fontVariationSettings: mode === "3d" ? "'FILL' 1" : undefined }}>
              {mode === "2d" ? "deployed_code" : "grid_view"}
            </span>
            {mode === "2d" ? "3D" : "2D"}
          </button>
        </div>
        {!empty && (
          <div className="flex h-8 w-64 items-center rounded border border-outline-variant bg-surface-container-high/80 px-sm backdrop-blur-glass">
            <span className="material-symbols-outlined !text-[16px] text-outline mr-xs">search</span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search graph..."
              aria-label="Search graph"
              className="w-full border-none bg-transparent font-code-md text-body-sm text-on-surface placeholder:text-outline-variant focus:outline-none focus:ring-0"
            />
          </div>
        )}
      </div>

      {/* Add Memory popover */}
      {adding && (
        <div className="glass-panel absolute left-md top-[52px] z-20 w-72 space-y-md rounded-lg border border-outline-variant p-md shadow-2xl">
          <div className="flex items-center justify-between">
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">Injection Protocol</span>
            <button onClick={() => setAdding(false)} aria-label="Close" className="text-outline hover:text-on-surface">
              <span className="material-symbols-outlined !text-[16px]">close</span>
            </button>
          </div>
          <div className="space-y-xs">
            <label className="font-label-caps text-[10px] uppercase text-outline">Type</label>
            <select
              value={addType}
              onChange={(e) => setAddType(e.target.value)}
              className="w-full rounded border border-outline-variant bg-surface-container-lowest p-sm font-body-sm text-body-sm text-on-surface focus:border-primary focus:outline-none">
              {ADDABLE_TYPES.map((t) => <option key={t} value={t}>{nodeLabel(t)}</option>)}
            </select>
          </div>
          <div className="space-y-xs">
            <label className="font-label-caps text-[10px] uppercase text-outline">Content</label>
            <textarea
              value={addText}
              onChange={(e) => setAddText(e.target.value)}
              placeholder="Enter memory state or factual observation…"
              rows={4}
              className="w-full rounded border border-outline-variant bg-surface-container-lowest p-sm font-body-sm text-body-sm text-on-surface placeholder:text-outline-variant focus:border-primary focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-sm border-t border-outline-variant pt-sm">
            <button onClick={() => setAdding(false)} className="rounded px-md py-sm font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:bg-surface-container-high">Cancel</button>
            <button onClick={addNode} className="rounded bg-primary px-md py-sm font-label-caps text-label-caps uppercase text-on-primary transition-all hover:opacity-90 active:scale-[0.98]">Confirm</button>
          </div>
        </div>
      )}

      {/* Node detail drawer */}
      {selected && (
        <aside className="glass-panel absolute right-0 top-0 z-30 flex h-full w-80 flex-col border-l border-outline-variant">
          <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-low/80 p-md">
            <h2 className="font-label-caps text-label-caps uppercase tracking-widest text-primary">Node Details</h2>
            <button onClick={() => { setSelected(null); setEditing(false); setMoving(false) }} aria-label="Close" className="text-outline hover:text-on-surface">
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>

          <div className="flex-1 space-y-lg overflow-y-auto p-md">
            <div className="flex items-center justify-between">
              <span className="rounded bg-primary/10 px-xs py-[2px] font-code-md text-[11px] text-primary">ID: {shortId(selected.id)}</span>
              <span className="rounded bg-surface-container-highest px-xs py-[2px] font-label-caps text-[10px] uppercase text-on-surface-variant">{nodeLabel(selected.type)}</span>
            </div>

            {editing ? (
              <div className="space-y-sm">
                <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={5} className="w-full rounded border border-outline-variant bg-surface-container-lowest p-sm font-body-sm text-body-sm text-on-surface focus:border-primary focus:outline-none" />
                <div className="flex gap-sm">
                  <button onClick={saveEdit} className="flex-1 rounded bg-primary py-sm font-label-caps text-label-caps uppercase text-on-primary hover:opacity-90">Save</button>
                  <button onClick={() => setEditing(false)} className="rounded border border-outline-variant px-md py-sm font-label-caps text-label-caps uppercase text-on-surface-variant">Cancel</button>
                </div>
              </div>
            ) : moving ? (
              <div className="space-y-sm">
                <p className="font-body-sm text-body-sm text-on-surface-variant">Move this memory to:</p>
                <div className="grid grid-cols-1 gap-sm">
                  {otherWs.map((w) => (
                    <button key={w.id} onClick={() => doMove(w.id)} className="flex items-center gap-sm border border-outline-variant bg-surface-container-low px-sm py-sm text-left transition-all hover:border-primary hover:bg-primary/10">
                      <span className="material-symbols-outlined !text-[18px] text-outline">folder</span>
                      <span className="truncate font-body-sm text-body-sm text-on-surface">{w.name}</span>
                    </button>
                  ))}
                  {otherWs.length === 0 && <p className="font-body-sm text-[11px] text-outline">No other workspaces — create one first.</p>}
                </div>
                <button onClick={() => setMoving(false)} className="w-full rounded border border-outline-variant py-sm font-label-caps text-label-caps uppercase text-on-surface-variant">Cancel</button>
              </div>
            ) : (
              <>
                <div className="rounded-lg border border-outline-variant bg-surface-container-lowest p-sm">
                  <p className="font-body-sm text-body-sm leading-relaxed text-on-surface-variant">{selected.label}</p>
                </div>
                <div className="grid grid-cols-2 gap-sm">
                  <div className="rounded border border-outline-variant bg-surface-container-low p-xs">
                    <span className="mb-[2px] block font-label-caps text-[9px] uppercase text-outline">Importance</span>
                    <div className="flex items-center gap-xs">
                      <div className="h-1 flex-1 rounded bg-surface-container-highest">
                        <div className="h-full bg-primary" style={{ width: `${Math.round(selected.importance * 100)}%` }} />
                      </div>
                      <span className="font-code-md text-[11px] text-on-surface">{selected.importance.toFixed(2)}</span>
                    </div>
                  </div>
                  <div className="rounded border border-outline-variant bg-surface-container-low p-xs">
                    <span className="mb-[2px] block font-label-caps text-[9px] uppercase text-outline">Type</span>
                    <span className="font-code-md text-[11px] text-on-surface">{nodeLabel(selected.type)}</span>
                  </div>
                </div>
              </>
            )}
          </div>

          {!editing && !moving && (
            <div className="grid grid-cols-2 gap-sm border-t border-outline-variant bg-surface-container-low/80 p-md">
              <button onClick={startEdit} className="flex h-9 items-center justify-center gap-xs rounded border border-outline-variant bg-surface-container-highest font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:bg-surface-container-high">
                <span className="material-symbols-outlined text-[16px]">edit</span>Edit
              </button>
              <button onClick={boost} className="flex h-9 items-center justify-center gap-xs rounded border border-primary/40 bg-primary-container/20 font-label-caps text-label-caps uppercase text-primary transition-colors hover:bg-primary-container/40">
                <span className="material-symbols-outlined text-[16px]" style={{ fontVariationSettings: "'FILL' 1" }}>bolt</span>Boost
              </button>
              <button onClick={startMove} className="flex h-9 items-center justify-center gap-xs rounded border border-outline-variant bg-surface-container-highest font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:bg-surface-container-high">
                <span className="material-symbols-outlined text-[16px]">move_up</span>Move
              </button>
              <button onClick={del} className="flex h-9 items-center justify-center gap-xs rounded border border-error/30 bg-error-container/20 font-label-caps text-label-caps uppercase text-error transition-colors hover:bg-error-container/30">
                <span className="material-symbols-outlined text-[16px]">delete</span>Delete
              </button>
            </div>
          )}
        </aside>
      )}

      {/* Zoom controls — 2D only; react-force-graph has its own orbit controls. */}
      {!empty && mode === "2d" && (
        <div className="glass-panel absolute bottom-md right-md z-10 flex flex-col overflow-hidden rounded-lg border border-outline-variant">
          <button onClick={() => zoomBy(1.3)} aria-label="Zoom in" className="flex h-8 w-8 items-center justify-center text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary">
            <span className="material-symbols-outlined text-[18px]">add</span>
          </button>
          <button onClick={() => zoomBy(1 / 1.3)} aria-label="Zoom out" className="flex h-8 w-8 items-center justify-center border-t border-outline-variant text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary">
            <span className="material-symbols-outlined text-[18px]">remove</span>
          </button>
          <button onClick={fitGraph} aria-label="Fit graph to view" className="flex h-8 w-8 items-center justify-center border-t border-outline-variant text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary">
            <span className="material-symbols-outlined text-[18px]">fit_screen</span>
          </button>
        </div>
      )}

      {/* 3D orbit hint */}
      {!empty && mode === "3d" && (
        <div className="glass-panel absolute bottom-md right-md z-10 flex items-center gap-sm rounded-lg border border-outline-variant px-md py-xs font-code-md text-[10px] text-on-surface-variant">
          <span className="material-symbols-outlined !text-[14px]">3d_rotation</span>
          Drag · orbit · scroll-zoom
        </div>
      )}

      {/* Legend — plain circles, Stitch style */}
      {!empty && legendTypes.length > 0 && (
        <div className="glass-panel absolute bottom-md left-md z-10 min-w-[160px] rounded-lg border border-outline-variant p-sm">
          <h4 className="mb-sm font-label-caps text-[9px] uppercase tracking-widest text-outline">Legend</h4>
          <div className="space-y-base">
            {legendTypes.map((t) => (
              <div key={t} className="flex items-center gap-sm">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: NODE_COLORS[t] ?? "#918f9f" }} />
                <span className="font-body-sm text-[11px] text-on-surface-variant">{nodeLabel(t)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {empty && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center text-center">
          <div className="mb-md flex h-16 w-16 items-center justify-center rounded-full border-2 border-dashed border-outline-variant">
            <span className="material-symbols-outlined text-[32px] text-outline-variant">hub</span>
          </div>
          <h3 className="font-headline-md text-headline-md text-on-surface-variant">No memories in this workspace yet.</h3>
          <p className="mt-xs font-body-sm text-body-sm text-outline">Start building your agent's persistent state.</p>
          <button onClick={() => setAdding(true)} className="mt-lg rounded border border-primary px-md py-sm font-label-caps text-label-caps uppercase text-primary transition-colors hover:bg-primary/10">
            Add Memory
          </button>
        </div>
      )}
    </div>
  )
}
