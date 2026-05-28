import { useEffect, useMemo, useRef, useState } from "react"
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d"
import * as THREE from "three"
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js"
import SpriteText from "three-spritetext"

import { NODE_COLORS, nodeLabel as nodeTypeLabel } from "~components/NodeTypeBadge"

export interface Graph3DNode { id: string; label: string; type: string; importance: number }
export interface Graph3DEdge { id: string; source: string; target: string }
export interface Graph3DSelected { id: string; label: string; type: string; importance: number }

interface Props {
  nodes: Graph3DNode[]
  edges: Graph3DEdge[]
  hubId: string | null
  search: string
  onSelect: (sel: Graph3DSelected) => void
}

interface RFGNode extends Graph3DNode { __hub: boolean }
interface RFGLink { id: string; source: string | RFGNode; target: string | RFGNode }

/** 3D "Explore" mode for the memory graph. Uses react-force-graph-3d (three.js
 * + d3-force-3d) to render the same nodes/edges from cytoscape's 2D mode in a
 * navigable 3D space. Spheres are sized by importance, coloured by node type;
 * the workspace's most-important node renders as the bright white "Alpha" hub
 * with extra emissive + halo. Labels float above each sphere as camera-facing
 * sprites so they stay readable while you orbit. */
export function Graph3DMode({ nodes, edges, hubId, search, onSelect }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods<RFGNode, RFGLink>>()
  const [size, setSize] = useState({ w: 0, h: 0 })

  // Track container size for the 3D canvas.
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      const w = Math.floor(r.width)
      const h = Math.floor(r.height)
      setSize((cur) => (cur.w === w && cur.h === h ? cur : { w, h }))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // react-force-graph expects { nodes, links }. Memoize so the force engine
  // doesn't reheat on every render — only when source data changes.
  const data = useMemo(() => ({
    nodes: nodes.map<RFGNode>((n) => ({ ...n, __hub: n.id === hubId })),
    links: edges.map<RFGLink>((e) => ({ id: e.id, source: e.source, target: e.target })),
  }), [nodes, edges, hubId])

  // Search filter: dim non-matching nodes (and edges that don't touch a match).
  const q = search.trim().toLowerCase()
  const matchesNode = (n: RFGNode) => q === "" || n.label.toLowerCase().includes(q)

  // Frame the graph once the force layout settles so the user isn't dropped
  // into the middle of a sphere or far off-camera.
  useEffect(() => {
    const t = setTimeout(() => fgRef.current?.zoomToFit(800, 80), 800)
    return () => clearTimeout(t)
  }, [data])

  // Continuous float effect on every data sphere. nodePositionUpdate only
  // fires during the active force tick — once the simulation cools, it stops
  // firing and the spheres freeze. Driving the float from our own raf loop
  // means the wobble survives indefinitely on top of the settled layout.
  useEffect(() => {
    type LiveNode = RFGNode & { x?: number; y?: number; z?: number; __threeObj?: THREE.Object3D }
    let raf = 0
    // Amplitude tuned to be clearly visible at the default zoomToFit camera
    // distance — the 2D mode uses a CSS float of several pixels, this needs
    // to read at a similar perceptual scale in world units.
    const amp = 4.5
    const tick = () => {
      const t = performance.now() * 0.001
      for (const n of data.nodes as LiveNode[]) {
        const obj = n.__threeObj
        if (!obj) continue
        const baseX = n.x ?? 0
        const baseY = n.y ?? 0
        const baseZ = n.z ?? 0
        const seed = ((n.id.charCodeAt(0) || 0) + (n.id.charCodeAt(1) || 0)) * 0.07
        obj.position.set(
          baseX + Math.sin(t * 0.7 + seed) * amp,
          baseY + Math.cos(t * 0.6 + seed * 1.3) * amp,
          baseZ + Math.sin(t * 0.8 + seed * 0.8) * amp,
        )
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [data])

  // Paint the obsidian backdrop directly in the WebGL canvas. The bloom pass
  // writes opaque pixels across the whole canvas, so setting clearColor +
  // scene.background is the only reliable way to keep the 3D view's backdrop
  // a clean solid colour. No starfield in 3D — the user wants just the real
  // data nodes here; the 2D mode keeps its DOM-level ParticleField.
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.renderer().setClearColor(0x1c1c1e, 1)
    const scene = fg.scene()
    scene.background = new THREE.Color(0x1c1c1e)
  }, [size.w, size.h])

  // Wire a bloom pass so emissive materials (especially the white hub) actually
  // glow instead of looking like flat-shaded balls. Run once the force-graph
  // instance is ready, and again on resize so the pass matches the canvas.
  useEffect(() => {
    if (size.w === 0 || size.h === 0) return
    const fg = fgRef.current
    if (!fg) return
    const composer = fg.postProcessingComposer()
    // strength / radius / threshold — softer bloom so the hub glows without
    // washing the rest of the scene or smothering edges and labels.
    const bloom = new UnrealBloomPass(new THREE.Vector2(size.w, size.h), 0.45, 0.6, 0.65)
    composer.addPass(bloom)
    return () => { composer.removePass(bloom); bloom.dispose() }
  }, [size.w, size.h])

  // Add a punchy point light at the hub so it visibly throws light onto its
  // neighbours — sells the "Alpha" node as a real light source, not just a
  // bright ball. Re-added whenever the hub identity changes.
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || !hubId) return
    const scene = fg.scene()
    // Moderate intensity so the hub clearly throws light onto neighbours
    // without bleaching their type colour into white.
    const light = new THREE.PointLight(0xffffff, 14, 160, 1.8)
    // force-graph mutates each node with x/y/z at runtime — our typed model
    // doesn't include those, so widen for the live position read.
    type WithCoords = { x?: number; y?: number; z?: number; id: string }
    const findHub = () => (data.nodes as unknown as WithCoords[]).find((n) => n.id === hubId)
    const hub = findHub()
    if (hub && typeof hub.x === "number" && typeof hub.y === "number" && typeof hub.z === "number") {
      light.position.set(hub.x, hub.y, hub.z)
    }
    light.name = "mn-hub-light"
    scene.add(light)
    // Keep it glued to the hub as the force layout settles.
    let raf = 0
    const follow = () => {
      const fresh = findHub()
      if (fresh && typeof fresh.x === "number" && typeof fresh.y === "number" && typeof fresh.z === "number") {
        light.position.set(fresh.x, fresh.y, fresh.z)
      }
      raf = requestAnimationFrame(follow)
    }
    follow()
    return () => {
      cancelAnimationFrame(raf)
      scene.remove(light)
      light.dispose()
    }
  }, [hubId, data])

  return (
    <div ref={wrapRef} className="h-full w-full">
      {size.w > 0 && size.h > 0 && (
        <ForceGraph3D<RFGNode, RFGLink>
          ref={fgRef}
          graphData={data}
          width={size.w}
          height={size.h}
          showNavInfo={false}
          nodeRelSize={4}
          nodeThreeObject={(raw) => {
            const n = raw as RFGNode
            const color = n.__hub ? "#ffffff" : NODE_COLORS[n.type] ?? "#c8c8c8"
            const radius = (n.__hub ? 6 : 3) + Math.max(0, Math.min(1, n.importance)) * 5
            const group = new THREE.Group()
            // StandardMaterial gives a real specular highlight + responds to
            // the hub PointLight, so non-hub spheres get lit by the Alpha.
            const sphere = new THREE.Mesh(
              new THREE.SphereGeometry(radius, 20, 20),
              new THREE.MeshStandardMaterial({
                color,
                // Emissive is unlit — it preserves the node's TYPE colour
                // even when the hub PointLight illuminates it. Pumped high
                // for non-hubs so each type stays visually distinct.
                emissive: n.__hub ? "#ffffff" : color,
                emissiveIntensity: n.__hub ? 1.5 : 1.0,
                roughness: n.__hub ? 0.35 : 0.7,
                metalness: 0.0,
                transparent: true,
                opacity: matchesNode(n) ? 1 : 0.12,
              }),
            )
            group.add(sphere)
            if (n.__hub) {
              // Two-stage additive halo: inner core blooms hot, outer wisp
              // catches the bloom pass and makes the hub feel luminescent.
              const innerHalo = new THREE.Mesh(
                new THREE.SphereGeometry(radius * 1.4, 24, 24),
                new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false }),
              )
              const outerHalo = new THREE.Mesh(
                new THREE.SphereGeometry(radius * 2.0, 24, 24),
                new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.07, blending: THREE.AdditiveBlending, depthWrite: false }),
              )
              group.add(innerHalo, outerHalo)
            }
            const labelText = n.label.length > 28 ? n.label.slice(0, 27) + "…" : n.label
            const sprite = new SpriteText(labelText)
            sprite.color = n.__hub ? "#ffffff" : "#e3e2e7"
            sprite.backgroundColor = "rgba(28,28,30,0.78)"
            sprite.padding = n.__hub ? 3 : 2
            sprite.borderRadius = 3
            sprite.textHeight = n.__hub ? 4 : 3
            // Float labels well clear of even the largest sphere + halo, and
            // render them on top so the hub's bright body can't eclipse them.
            const labelOffset = n.__hub ? radius * 2.6 + 6 : radius + 4
            sprite.position.set(0, labelOffset, 0)
            sprite.renderOrder = 999
            const sm = sprite.material as THREE.SpriteMaterial
            sm.depthTest = false
            sm.depthWrite = false
            if (!matchesNode(n)) sm.opacity = 0.15
            group.add(sprite)
            return group
          }}
          nodeLabel={(n) => `${(n as RFGNode).label}  ·  ${nodeTypeLabel((n as RFGNode).type)}`}
          linkColor={() => "rgba(255,255,255,0.55)"}
          linkWidth={0.8}
          linkOpacity={0.45}
          linkResolution={6}
          linkVisibility={(l) => {
            if (q === "") return true
            const s = typeof l.source === "object" ? (l.source as RFGNode) : nodes.find((n) => n.id === l.source) as Graph3DNode | undefined
            const t = typeof l.target === "object" ? (l.target as RFGNode) : nodes.find((n) => n.id === l.target) as Graph3DNode | undefined
            return !!(s && t && (matchesNode(s as RFGNode) || matchesNode(t as RFGNode)))
          }}
          enableNodeDrag={true}
          cooldownTicks={120}
          warmupTicks={40}
          onNodeClick={(n) => {
            const r = n as RFGNode
            onSelect({ id: r.id, label: r.label, type: r.type, importance: r.importance })
          }}
        />
      )}
    </div>
  )
}

export default Graph3DMode
