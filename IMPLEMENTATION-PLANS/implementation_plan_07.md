# Plan 07 — Extension UI: Sidebar & Popup

> Covers: Doc 09 (Frontend Design), Doc 12 (Use Cases), Doc 17 (Cold Start / Empty States)

---

## 1. SIDEBAR (Injected as side panel, 380px wide)

### sidebar/index.tsx — Root
```tsx
import { useMnemosyneStore } from "../stores/mnemosyneStore"

const TABS = [
  { id: 'memory', label: 'Memory', icon: '🧠' },
  { id: 'graph', label: 'Graph', icon: '🕸️' },
  { id: 'audit', label: 'Audit', icon: '📋' },
  { id: 'search', label: 'Search', icon: '🔍' },
]

export default function Sidebar() {
  const { activeTab, setActiveTab, activeWorkspace, engineOnline } = useMnemosyneStore()

  if (!engineOnline) return <OfflineState />
  if (!activeWorkspace) return <NoWorkspaceState />

  return (
    <div className="mn-flex mn-flex-col mn-h-full mn-bg-surface mn-text-text-primary">
      {/* Header */}
      <header className="mn-px-4 mn-py-3 mn-border-b mn-border-surface-border">
        <WorkspaceSelector />
      </header>

      {/* Tab bar */}
      <nav className="mn-flex mn-border-b mn-border-surface-border">
        {TABS.map(tab => (
          <button key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`mn-flex-1 mn-py-2 mn-text-sm mn-transition
              ${activeTab === tab.id ? 'mn-text-accent mn-border-b-2 mn-border-accent' : 'mn-text-text-secondary'}`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <main className="mn-flex-1 mn-overflow-y-auto">
        {activeTab === 'memory' && <MemoryTab />}
        {activeTab === 'graph' && <GraphTab />}
        {activeTab === 'audit' && <AuditTab />}
        {activeTab === 'search' && <SearchTab />}
      </main>

      {/* Command palette trigger */}
      <CommandPalette />
    </div>
  )
}
```

### sidebar/MemoryTab.tsx
```tsx
export default function MemoryTab() {
  const [nodes, setNodes] = useState<MemoryNode[]>([])
  const [filter, setFilter] = useState<NodeType | 'all'>('all')
  const { activeWorkspace } = useMnemosyneStore()

  useEffect(() => {
    api.getNodes(activeWorkspace.id, { status: 'active', type: filter !== 'all' ? filter : undefined })
      .then(setNodes)
  }, [activeWorkspace, filter])

  if (nodes.length === 0) return <EmptyMemoryState />

  // Group by type
  const groups = groupBy(nodes, n => n.node_type)

  return (
    <div className="mn-p-3 mn-space-y-4">
      {/* Type filter chips */}
      <div className="mn-flex mn-gap-2 mn-flex-wrap">
        <FilterChip label="All" active={filter === 'all'} onClick={() => setFilter('all')} />
        {Object.values(NodeType).map(t => (
          <FilterChip key={t} label={t} active={filter === t} onClick={() => setFilter(t)}
            count={groups[t]?.length || 0} />
        ))}
      </div>

      {/* Node cards grouped by type */}
      {Object.entries(groups).map(([type, items]) => (
        <section key={type}>
          <h3 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-2 mn-uppercase">
            <NodeTypeBadge type={type as NodeType} /> {TYPE_LABELS[type]} ({items.length})
          </h3>
          {items.map(node => (
            <MemoryNodeCard key={node.id} node={node}
              onEdit={(id) => openEditModal(id)}
              onBoost={(id) => handleBoost(id)}
              onDelete={(id) => handleDelete(id)} />
          ))}
        </section>
      ))}
    </div>
  )
}
```

### sidebar/GraphTab.tsx
```tsx
import cytoscape from 'cytoscape'
import cola from 'cytoscape-cola'

cytoscape.use(cola)

// Node colors by type (from Doc 09)
const NODE_COLORS: Record<string, string> = {
  goal: '#22C55E',
  decision: '#3B82F6',
  technical_fact: '#8B5CF6',
  entity: '#F59E0B',
  problem: '#EF4444',
  preference: '#EC4899',
  task: '#06B6D4',
  insight: '#10B981',
}

export default function GraphTab() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const { activeWorkspace } = useMnemosyneStore()

  useEffect(() => {
    if (!containerRef.current || !activeWorkspace) return
    loadGraph()
  }, [activeWorkspace])

  async function loadGraph() {
    const data = await api.getGraph(activeWorkspace!.id)
    if (data.nodes.length === 0) {
      // Show empty graph state
      return
    }

    const elements = [
      ...data.nodes.map(n => ({
        data: {
          id: n.id, label: truncate(n.content, 30),
          type: n.node_type, importance: n.importance_score,
        }
      })),
      ...data.edges.map(e => ({
        data: {
          id: e.id, source: e.source_node_id,
          target: e.target_node_id, type: e.edge_type,
        }
      })),
    ]

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements,
      layout: { name: 'cola', nodeSpacing: 40, animate: true, maxSimulationTime: 2000 },
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': (el) => NODE_COLORS[el.data('type')] || '#7C3AED',
            'width': (el) => 20 + el.data('importance') * 30,
            'height': (el) => 20 + el.data('importance') * 30,
            'font-size': '10px', 'color': '#E4E4E7',
            'text-wrap': 'wrap', 'text-max-width': '80px',
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 1.5, 'line-color': '#3A3A4E',
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#3A3A4E',
          }
        },
        {
          selector: 'node:selected',
          style: { 'border-width': 3, 'border-color': '#7C3AED' }
        }
      ],
    })

    // Click handler: show node detail panel
    cyRef.current.on('tap', 'node', (evt) => {
      const nodeId = evt.target.id()
      showNodeDetail(nodeId)
    })
  }

  return (
    <div className="mn-relative mn-h-full">
      <div ref={containerRef} className="mn-w-full mn-h-full" />
      {/* Graph controls overlay */}
      <div className="mn-absolute mn-top-2 mn-right-2 mn-flex mn-gap-1">
        <button onClick={() => cyRef.current?.fit()} title="Fit">⊞</button>
        <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)} title="Zoom In">+</button>
        <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() / 1.2)} title="Zoom Out">−</button>
      </div>
    </div>
  )
}
```

### sidebar/AuditTab.tsx
```tsx
export default function AuditTab() {
  const [pendingReviews, setPending] = useState<PendingReview[]>([])
  const [conflicts, setConflicts] = useState<ConflictCandidate[]>([])

  useEffect(() => {
    Promise.all([
      api.getPending(activeWorkspace.id),
      api.getConflicts(activeWorkspace.id, { status: 'pending' }),
    ]).then(([p, c]) => { setPending(p); setConflicts(c) })
  }, [])

  return (
    <div className="mn-p-3 mn-space-y-4">
      {/* Pending Reviews */}
      <section>
        <h3 className="mn-text-sm mn-font-semibold mn-text-text-secondary">
          Pending Reviews ({pendingReviews.length})
        </h3>
        {pendingReviews.length === 0 ? <EmptyPendingState /> :
          pendingReviews.map(r => (
            <PendingReviewCard key={r.id} review={r}
              onApprove={(id, edited) => handleApprove(id, edited)}
              onReject={(id) => handleReject(id)} />
          ))
        }
      </section>

      {/* Active Conflicts */}
      <section>
        <h3 className="mn-text-sm mn-font-semibold mn-text-text-secondary">
          Conflicts ({conflicts.length})
        </h3>
        {conflicts.map(c => (
          <ConflictCard key={c.id} conflict={c}
            onResolve={(id, winner, custom) => handleResolve(id, winner, custom)} />
        ))}
      </section>
    </div>
  )
}
```

### sidebar/SearchTab.tsx
```tsx
export default function SearchTab() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryNode[]>([])
  const [scope, setScope] = useState<'workspace' | 'global'>('workspace')

  const debouncedSearch = useDebouncedCallback(async (q: string) => {
    if (q.length < 2) return setResults([])
    const endpoint = scope === 'global' ? api.globalSearch(q) :
                     api.search(activeWorkspace.id, q)
    setResults(await endpoint)
  }, 300)

  return (
    <div className="mn-p-3">
      <input value={query}
        onChange={e => { setQuery(e.target.value); debouncedSearch(e.target.value) }}
        placeholder="Search memories..."
        className="mn-w-full mn-px-3 mn-py-2 mn-bg-surface-hover mn-border mn-border-surface-border
                   mn-rounded-lg mn-text-text-primary mn-placeholder-text-secondary" />
      <div className="mn-flex mn-gap-2 mn-mt-2">
        <button onClick={() => setScope('workspace')}
          className={scope === 'workspace' ? 'mn-text-accent' : ''}>This Workspace</button>
        <button onClick={() => setScope('global')}
          className={scope === 'global' ? 'mn-text-accent' : ''}>All Workspaces</button>
      </div>
      <div className="mn-mt-3 mn-space-y-2">
        {results.map(n => <MemoryNodeCard key={n.id} node={n} compact />)}
      </div>
    </div>
  )
}
```

---

## 2. POPUP (400×600, extension icon click)

### popup/index.tsx
```tsx
export default function Popup() {
  const { engineOnline, activeWorkspace, captureEnabled, pendingReviewCount,
          toggleCapture } = useMnemosyneStore()

  return (
    <div className="mn-w-[400px] mn-h-[600px] mn-bg-surface mn-text-text-primary mn-p-4">
      {/* Engine status */}
      <div className="mn-flex mn-items-center mn-gap-2 mn-mb-4">
        <span className={`mn-w-2 mn-h-2 mn-rounded-full
          ${engineOnline ? 'mn-bg-success' : 'mn-bg-danger'}`} />
        <span className="mn-text-sm">
          {engineOnline ? `Engine v${engineVersion}` : 'Engine offline'}
        </span>
        {!engineOnline && <button className="mn-text-accent mn-text-sm">Restart</button>}
      </div>

      {/* Active workspace */}
      <WorkspaceSelector />

      {/* Quick stats */}
      {activeWorkspace && (
        <div className="mn-grid mn-grid-cols-2 mn-gap-3 mn-mt-4">
          <StatCard label="Memories" value={activeWorkspace.node_count} />
          <StatCard label="Pending" value={pendingReviewCount}
            highlight={pendingReviewCount > 0} />
        </div>
      )}

      {/* Capture toggle — always one click (Doc 14) */}
      <button onClick={toggleCapture}
        className={`mn-w-full mn-mt-4 mn-py-3 mn-rounded-lg mn-font-medium mn-transition
          ${captureEnabled
            ? 'mn-bg-accent mn-text-white hover:mn-bg-accent-hover'
            : 'mn-bg-surface-hover mn-text-warning mn-border mn-border-warning'}`}>
        {captureEnabled ? '🔴 Capture Active — Click to Pause'
                        : '⏸ Capture Paused — Click to Resume'}
      </button>

      {/* Quick actions */}
      <div className="mn-mt-4 mn-space-y-2">
        <button onClick={openSidebar} className="mn-action-btn">Open Sidebar</button>
        <button onClick={openDashboard} className="mn-action-btn">Memory Audit</button>
        <button onClick={openSettings} className="mn-action-btn">Settings</button>
      </div>

      {/* Last injection info */}
      {lastInjection && (
        <div className="mn-mt-4 mn-p-3 mn-bg-surface-hover mn-rounded-lg mn-text-sm">
          <p className="mn-text-text-secondary">Last injection</p>
          <p>{lastInjection.workspace_name} · {lastInjection.node_count} items ·
             {lastInjection.token_count} tokens</p>
        </div>
      )}
    </div>
  )
}
```

---

## 3. REUSABLE COMPONENTS

### MemoryNodeCard.tsx
```tsx
// Displays a single memory node with type badge, content, confidence bar,
// importance indicator, edit/boost/delete actions.
// Compact mode for search results (no actions, smaller).
// Shows version indicator if version > 1.
// Shows lock icon if is_permanent.
// Shows ✓ if user_verified.
```

### ConflictCard.tsx
```tsx
// Shows two conflicting nodes side-by-side with:
// - Node A content + metadata
// - Node B content + metadata
// - Radio options: "Keep A", "Keep B", "Both valid", "Custom resolution"
// - Custom resolution text input
// - [Resolve] button
// Matches UC-15 from Doc 12.
```

### ConfidenceBar.tsx
```tsx
// Horizontal bar showing confidence 0-100%.
// Colors: <60% red, 60-80% yellow, >80% green.
// Animated fill on mount.
```

### NodeTypeBadge.tsx
```tsx
// Colored pill showing node type.
// Colors match graph node colors from Doc 09.
const TYPE_COLORS = {
  goal: 'mn-bg-success/20 mn-text-success',
  decision: 'mn-bg-info/20 mn-text-info',
  technical_fact: 'mn-bg-accent/20 mn-text-accent',
  problem: 'mn-bg-danger/20 mn-text-danger',
  event: 'mn-bg-[#14B8A6]/20 mn-text-[#14B8A6]',     // Doc 09 §2.1: Teal
  entity: 'mn-bg-warning/20 mn-text-warning',
  preference: 'mn-bg-[#EC4899]/20 mn-text-[#EC4899]', // Doc 09 §2.1: Pink
  task: 'mn-bg-info/20 mn-text-info',
  // ...
}
```

### CommandPalette.tsx
```tsx
// Cmd+K / Ctrl+K fuzzy search across all actions.
// Actions: search memories, switch workspace, toggle capture,
// open dashboard, create manual node, etc.
// Doc 09: keyboard-first interactions.
```

### WorkspaceSelector.tsx
```tsx
// Dropdown showing active workspace + list of all workspaces.
// Shows workspace health indicator (colored dot).
// "Create New" option at bottom.
// Matches UC-07 workspace switching.
```

### SkeletonLoader.tsx
```tsx
// Animated placeholder while data loads.
// Used in all tabs during initial fetch.
// Must load <500ms per Doc 14.
```

---

## 4. EMPTY STATES (from Doc 17)

Each view has a designed empty state with a primary CTA:

| View | Empty State | CTA |
|------|-------------|-----|
| Memory Tab | "Your knowledge graph starts here." | → Open Claude.ai |
| Graph Tab | Single pulsing center node | → Start a conversation |
| Audit Tab | "✓ Nothing to review" | (no action needed) |
| Search Tab | Search prompt | (just type) |
| Popup (no workspace) | "No workspaces yet." | [+ Create Workspace] |
| Engine offline | "⚠ Engine not running" | [Restart Engine] |

---

## Files Summary

| File | Purpose |
|------|---------|
| `extension/sidebar/index.tsx` | Sidebar root + tabs |
| `extension/sidebar/MemoryTab.tsx` | Memory list by type |
| `extension/sidebar/GraphTab.tsx` | Cytoscape.js graph |
| `extension/sidebar/AuditTab.tsx` | Pending reviews + conflicts |
| `extension/sidebar/SearchTab.tsx` | FTS + global search |
| `extension/popup/index.tsx` | Extension popup |
| `extension/components/MemoryNodeCard.tsx` | Node display card |
| `extension/components/ConflictCard.tsx` | Conflict resolution UI |
| `extension/components/ConfidenceBar.tsx` | Confidence indicator |
| `extension/components/NodeTypeBadge.tsx` | Type color badge |
| `extension/components/CommandPalette.tsx` | Cmd+K palette |
| `extension/components/WorkspaceSelector.tsx` | Workspace dropdown |
| `extension/components/SkeletonLoader.tsx` | Loading placeholder |
| `extension/components/EmptyStates.tsx` | All empty state views |
| `extension/components/FilterChip.tsx` | Filter toggle chip |
| `extension/components/StatCard.tsx` | Stats display |
| `extension/components/PendingReviewCard.tsx` | Review card |
| `extension/styles/design-system.css` | Full design tokens |

**Total: ~18 files.**

---

> **Next: Plan 08 — Memory Audit Dashboard**
