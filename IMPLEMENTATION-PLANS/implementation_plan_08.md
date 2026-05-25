# Plan 08 — Memory Audit Dashboard

> Covers: Doc 09 §6 (Full Audit Page), Doc 02 F-006/F-009 (Memory Audit UI / Health Dashboard), Doc 12 UCs 10-13, 21-22 (Edit, Boost, Bulk Delete, Version History, Cross-Workspace Search, Privacy Audit), Doc 16 §5.3 (Engine Health)

---

## 1. DASHBOARD SCAFFOLD

The dashboard opens in a **new browser tab** (`chrome-extension://[id]/dashboard.html`). Min width: 1024px. Sidebar collapses to icon bar at < 1280px.

### dashboard/app.tsx — Root
```tsx
import ReviewPage from './pages/ReviewPage'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: '📊' },
  { path: '/graph', label: 'Graph Explorer', icon: '🕸' },
  { path: '/memory', label: 'Memory Browser', icon: '📝' },
  { path: '/review', label: 'Review', icon: '⚠️' },   // Doc 09 §6 — pending review workflow
  { path: '/timeline', label: 'Timeline', icon: '🕐' },
  { path: '/conflicts', label: 'Conflicts', icon: '⚡' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function DashboardApp() {
  const { workspaces, activeWorkspace, setActiveWorkspace } = useMnemosyneStore()

  return (
    <BrowserRouter>
      <div className="mn-flex mn-h-screen mn-bg-bg-primary mn-text-text-primary">
        {/* Left sidebar nav */}
        <aside className="mn-w-[220px] mn-border-r mn-border-border mn-flex mn-flex-col">
          <header className="mn-p-4 mn-border-b mn-border-border">
            <span className="mn-text-lg mn-font-semibold">🧠 Mnemosyne</span>
          </header>

          {/* Workspace selector */}
          <div className="mn-p-3 mn-border-b mn-border-border">
            <WorkspaceDropdown
              workspaces={workspaces}
              active={activeWorkspace}
              onChange={setActiveWorkspace}
            />
            <button className="mn-text-sm mn-text-accent mn-mt-2">+ New Workspace</button>
          </div>

          <nav className="mn-flex-1 mn-py-2">
            {NAV_ITEMS.map(item => (
              <NavLink key={item.path} to={item.path}
                className={({ isActive }) =>
                  `mn-flex mn-items-center mn-gap-3 mn-px-4 mn-py-2.5 mn-text-sm mn-transition
                   ${isActive ? 'mn-bg-bg-hover mn-text-accent mn-border-r-2 mn-border-accent'
                              : 'mn-text-text-secondary hover:mn-bg-bg-hover'}`
                }>
                <span>{item.icon}</span> {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Engine status footer */}
          <EngineStatusFooter />
        </aside>

        {/* Main content */}
        <main className="mn-flex-1 mn-overflow-y-auto">
         <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/graph" element={<GraphExplorerPage />} />
            <Route path="/memory" element={<MemoryBrowserPage />} />
            <Route path="/review" element={<ReviewPage />} />  {/* Doc 09 §6 */}
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/conflicts" element={<ConflictManagerPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

---

## 2. OVERVIEW PAGE (Doc 09 §6, Doc 02 F-009)

### dashboard/pages/Overview.tsx
```tsx
export default function OverviewPage() {
  const { activeWorkspace } = useMnemosyneStore()
  const [health, setHealth] = useState<WorkspaceHealth | null>(null)
  const [engineStatus, setEngineStatus] = useState<EngineHealth | null>(null)
  const [recentActivity, setRecentActivity] = useState<ActivityEvent[]>([])

  useEffect(() => {
    if (!activeWorkspace) return
    Promise.all([
      api.getWorkspaceHealth(activeWorkspace.id),
      api.getEngineHealth(),
      api.getRecentActivity(activeWorkspace.id, { limit: 20 }),
    ]).then(([h, e, a]) => { setHealth(h); setEngineStatus(e); setRecentActivity(a) })
  }, [activeWorkspace])

  return (
    <div className="mn-p-8 mn-max-w-6xl">
      <h1 className="mn-text-2xl mn-font-bold mn-mb-6">
        {activeWorkspace?.name || 'Select a workspace'}
      </h1>

      {/* Top stats row */}
      <div className="mn-grid mn-grid-cols-4 mn-gap-4 mn-mb-8">
        <StatCard label="Memory Health" value={`${health?.score ?? 0}%`}
          bar={health?.score} color={health?.score > 80 ? 'success' : 'warning'} />
        <StatCard label="Total Memories" value={health?.totalNodes ?? 0} />
        <StatCard label="Pending Review" value={health?.pendingCount ?? 0}
          highlight={health?.pendingCount > 0} link="/memory?filter=pending" />
        <StatCard label="Active Conflicts" value={health?.conflictCount ?? 0}
          highlight={health?.conflictCount > 0} link="/conflicts" />
      </div>

      {/* Two-column: breakdown + engine status */}
      <div className="mn-grid mn-grid-cols-2 mn-gap-6 mn-mb-8">
        {/* Memory breakdown by type */}
        <div className="mn-bg-bg-secondary mn-rounded-lg mn-p-5 mn-border mn-border-border">
          <h2 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-4">
            MEMORY BREAKDOWN
          </h2>
          {Object.entries(health?.byType ?? {}).map(([type, count]) => (
            <div key={type} className="mn-flex mn-justify-between mn-py-1.5 mn-text-sm">
              <span><NodeTypeBadge type={type} /> {TYPE_LABELS[type]}</span>
              <span className="mn-text-text-secondary">{count}</span>
            </div>
          ))}
        </div>

        {/* Engine health — Doc 16 §5.3 */}
        <div className="mn-bg-bg-secondary mn-rounded-lg mn-p-5 mn-border mn-border-border">
          <h2 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-4">
            SYSTEM STATUS
          </h2>
          <StatusRow label="Engine" status={engineStatus?.status} detail={`v${engineStatus?.version}`} />
          <StatusRow label="Database" status={engineStatus?.db_status} />
          <StatusRow label="Vector Store" status={engineStatus?.vector_status} />
          <StatusRow label="Extraction Queue" status="ok" detail={`${engineStatus?.queue_depth ?? 0} items`} />
          <StatusRow label="Decay Worker" status="ok" detail={`Next: ${engineStatus?.next_decay}`} />
          <StatusRow label="Disk Usage" detail={`${engineStatus?.disk_usage_mb ?? 0} MB`} />
        </div>
      </div>

      {/* Recent activity feed */}
      <div className="mn-bg-bg-secondary mn-rounded-lg mn-p-5 mn-border mn-border-border">
        <h2 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-4">
          RECENT ACTIVITY
        </h2>
        {recentActivity.map(event => (
          <ActivityRow key={event.id} event={event} />
        ))}
      </div>
    </div>
  )
}
```

---

## 3. MEMORY BROWSER PAGE (Doc 02 F-006, Doc 12 UCs 10-12)

Supports: edit node (UC-10), boost/permanent (UC-11), bulk delete (UC-12), version history (UC-13).

### dashboard/pages/MemoryBrowser.tsx
```tsx
export default function MemoryBrowserPage() {
  const { activeWorkspace } = useMnemosyneStore()
  const [nodes, setNodes] = useState<MemoryNode[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [filters, setFilters] = useState<NodeFilters>({ status: 'active', type: 'all', sort: 'importance' })
  const [searchQuery, setSearchQuery] = useState('')
  const [detailNode, setDetailNode] = useState<MemoryNode | null>(null)

  // Fetch nodes with filters
  useEffect(() => { /* fetch from api with filters */ }, [activeWorkspace, filters, searchQuery])

  async function handleBulkDelete(mode: 'soft' | 'hard') {
    await api.bulkDeleteNodes(activeWorkspace!.id, [...selectedIds], mode)
    setSelectedIds(new Set())
    refreshNodes()
  }

  return (
    <div className="mn-p-8 mn-max-w-6xl">
      <div className="mn-flex mn-items-center mn-justify-between mn-mb-6">
        <h1 className="mn-text-2xl mn-font-bold">Memory Browser</h1>
        {/* Bulk actions bar — visible when items selected */}
        {selectedIds.size > 0 && (
          <BulkActionsBar
            count={selectedIds.size}
            onDelete={() => handleBulkDelete('soft')}
            onHardDelete={() => handleBulkDelete('hard')}
            onSelectAll={() => setSelectedIds(new Set(nodes.map(n => n.id)))}
            onClear={() => setSelectedIds(new Set())}
          />
        )}
      </div>

      {/* Search + filters */}
      <div className="mn-flex mn-gap-3 mn-mb-4">
        <SearchInput value={searchQuery} onChange={setSearchQuery} placeholder="Search memories..." />
        <FilterDropdown label="Type" options={NODE_TYPES} value={filters.type}
          onChange={t => setFilters(f => ({...f, type: t}))} />
        <FilterDropdown label="Status" options={['active','archived','superseded']}
          value={filters.status} onChange={s => setFilters(f => ({...f, status: s}))} />
        <SortDropdown value={filters.sort}
          onChange={s => setFilters(f => ({...f, sort: s}))} />
      </div>

      {/* Node list */}
      <div className="mn-space-y-2">
        {nodes.map(node => (
          <MemoryNodeRow key={node.id} node={node}
            selected={selectedIds.has(node.id)}
            onSelect={(id) => toggleSelect(id)}
            onClick={() => setDetailNode(node)}
            onEdit={(id) => openEditModal(id)}
            onBoost={(id) => openBoostModal(id)}
            onDelete={(id) => handleSingleDelete(id)} />
        ))}
      </div>

      {/* Detail side panel (slides in from right) */}
      {detailNode && (
        <NodeDetailPanel node={detailNode}
          onClose={() => setDetailNode(null)}
          onEdit={() => openEditModal(detailNode.id)}
          onViewHistory={() => openVersionHistory(detailNode.id)} />
      )}

      {/* Modals */}
      <EditNodeModal />
      <BoostNodeModal />
      <VersionHistoryModal />
    </div>
  )
}
```

### dashboard/pages/ReviewPage.tsx

```tsx
// dashboard/pages/ReviewPage.tsx
// Doc 09 §6 — Pending Review page: approve/reject extraction candidates
// Accessible from dashboard nav as "/review"
// API endpoints: GET /workspaces/{id}/pending, POST /pending/{id}/approve, POST /pending/{id}/reject

import { useState, useEffect } from 'react'
import { useMnemosyneStore } from '../store/mnemosyneStore'
import { api } from '../lib/api'

interface PendingItem {
  id: string
  candidate_type: string
  candidate_content: string
  candidate_data: Record<string, unknown>
  candidate_confidence: number
  source_platform: string
  created_at: string
  expires_at: string
  source_context?: string
}

export default function ReviewPage() {
  const { activeWorkspace } = useMnemosyneStore()
  const [items, setItems] = useState<PendingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')

  useEffect(() => {
    if (!activeWorkspace) return
    setLoading(true)
    api.get(`/workspaces/${activeWorkspace.id}/pending`)
      .then(r => { setItems(r.data.items); setLoading(false) })
      .catch(() => setLoading(false))
  }, [activeWorkspace])

  const approve = async (item: PendingItem) => {
    const edits = editingId === item.id && editContent
      ? { content: editContent }
      : undefined
    await api.post(`/workspaces/${activeWorkspace!.id}/pending/${item.id}/approve`,
      { edits })
    setItems(prev => prev.filter(i => i.id !== item.id))
    setEditingId(null)
  }

  const reject = async (item: PendingItem) => {
    await api.post(`/workspaces/${activeWorkspace!.id}/pending/${item.id}/reject`,
      { reason: 'inaccurate' })
    setItems(prev => prev.filter(i => i.id !== item.id))
  }

  if (!activeWorkspace) return (
    <div className="mn-p-8 mn-text-text-secondary">Select a workspace to review extractions.</div>
  )

  if (loading) return (
    <div className="mn-p-8 mn-text-text-secondary">Loading pending extractions...</div>
  )

  return (
    <div className="mn-p-6">
      <h1 className="mn-text-xl mn-font-semibold mn-mb-1">Pending Review</h1>
      <p className="mn-text-sm mn-text-text-secondary mn-mb-6">
        {items.length} extraction{items.length !== 1 ? 's' : ''} awaiting your approval.
        Low-confidence extractions are held here before being committed to memory.
      </p>

      {items.length === 0 && (
        <div className="mn-text-text-secondary mn-text-sm mn-p-8 mn-text-center
                        mn-border mn-border-border mn-rounded-lg">
          ✅ Nothing to review — all extractions are up to date.
        </div>
      )}

      <div className="mn-flex mn-flex-col mn-gap-4">
        {items.map(item => (
          <div key={item.id}
               className="mn-border mn-border-border mn-rounded-lg mn-p-4 mn-bg-bg-secondary">

            {/* Header row */}
            <div className="mn-flex mn-items-center mn-justify-between mn-mb-2">
              <span className="mn-text-xs mn-font-mono mn-bg-bg-primary mn-px-2 mn-py-0.5
                               mn-rounded mn-text-accent mn-uppercase">
                {item.candidate_type}
              </span>
              <span className="mn-text-xs mn-text-text-secondary">
                Confidence: {Math.round(item.candidate_confidence * 100)}%
                &nbsp;·&nbsp;{item.source_platform}
              </span>
            </div>

            {/* Content — editable */}
            {editingId === item.id ? (
              <textarea
                className="mn-w-full mn-bg-bg-primary mn-border mn-border-border mn-rounded
                           mn-p-2 mn-text-sm mn-text-text-primary mn-mb-3"
                rows={3}
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
              />
            ) : (
              <p className="mn-text-sm mn-text-text-primary mn-mb-3
                            mn-cursor-pointer mn-hover:mn-underline"
                 onClick={() => { setEditingId(item.id); setEditContent(item.candidate_content) }}
                 title="Click to edit before approving">
                {item.candidate_content}
              </p>
            )}

            {/* Source context (if available) */}
            {item.source_context && (
              <p className="mn-text-xs mn-text-text-secondary mn-italic mn-mb-3
                            mn-border-l-2 mn-border-border mn-pl-2">
                "{item.source_context}"
              </p>
            )}

            {/* Actions */}
            <div className="mn-flex mn-gap-2">
              <button
                onClick={() => approve(item)}
                className="mn-text-sm mn-px-3 mn-py-1.5 mn-rounded mn-bg-success
                           mn-text-white mn-font-medium mn-hover:mn-opacity-90">
                ✓ Approve{editingId === item.id ? ' (edited)' : ''}
              </button>
              <button
                onClick={() => reject(item)}
                className="mn-text-sm mn-px-3 mn-py-1.5 mn-rounded mn-bg-bg-primary
                           mn-border mn-border-border mn-text-text-secondary
                           mn-hover:mn-text-error">
                ✕ Reject
              </button>
              {editingId !== item.id && (
                <button
                  onClick={() => { setEditingId(item.id); setEditContent(item.candidate_content) }}
                  className="mn-text-sm mn-px-3 mn-py-1.5 mn-rounded mn-bg-bg-primary
                             mn-border mn-border-border mn-text-text-secondary">
                  ✎ Edit
                </button>
              )}
              {editingId === item.id && (
                <button
                  onClick={() => setEditingId(null)}
                  className="mn-text-sm mn-px-3 mn-py-1.5 mn-text-text-secondary">
                  Cancel
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

### Key Sub-Components

**NodeDetailPanel** — Right slide-in panel showing:
- Node type badge, content, structured data
- Confidence bar, importance bar
- Created date, source platform, session ID
- Connected nodes list (edges)
- Version indicator (`v3 — 2 previous versions`)
- Actions: Edit, Boost, Mark Permanent, Delete
- Version History tab (UC-13): shows all versions with diffs, timestamps, changed_by

**EditNodeModal** — Modal for editing node content/structured data:
- Content textarea (pre-filled)
- Structured data JSON editor
- Node type selector
- Save creates new version (old version archived with `valid_until`)
- Sets `user_verified = true`

**BoostNodeModal** — Modal for UC-11:
- Importance slider (0.0–1.0)
- "Mark as Permanent" checkbox (`is_permanent = true`)
- Preview of impact on retrieval ranking

**VersionHistoryModal** — Timeline of all node versions (UC-13):
- Each version shows: content, timestamp, changed_by (user/system), source
- Diff highlighting between versions
- Option to "Restore this version"

---

## 4. GRAPH EXPLORER PAGE (Doc 09 §4.3, expanded)

Full-page version of the sidebar graph with enhanced controls.

### dashboard/pages/GraphExplorer.tsx
```tsx
export default function GraphExplorerPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const { activeWorkspace } = useMnemosyneStore()
  const [filters, setFilters] = useState<GraphFilters>({ types: Object.values(NodeType) })
  const [selectedNode, setSelectedNode] = useState<string | null>(null)

  // Same Cytoscape setup as sidebar GraphTab but with:
  // - Larger canvas (full page)
  // - Filter checkboxes for each node type
  // - Search bar that highlights matching nodes
  // - Click node → detail panel (reuse NodeDetailPanel)
  // - Minimap overlay (bottom-right)
  // - Export graph as PNG button
  // - Layout switcher: cola / concentric / breadthfirst

  return (
    <div className="mn-flex mn-h-full">
      {/* Left controls panel */}
      <div className="mn-w-[240px] mn-p-4 mn-border-r mn-border-border mn-space-y-4">
        <SearchInput placeholder="Find in graph..." onChange={highlightNodes} />

        <div>
          <h3 className="mn-text-xs mn-font-semibold mn-text-text-tertiary mn-mb-2">NODE TYPES</h3>
          {Object.values(NodeType).map(type => (
            <label key={type} className="mn-flex mn-items-center mn-gap-2 mn-py-1 mn-text-sm">
              <input type="checkbox" checked={filters.types.includes(type)}
                onChange={() => toggleTypeFilter(type)} />
              <NodeTypeBadge type={type} /> {TYPE_LABELS[type]}
            </label>
          ))}
        </div>

        <div>
          <h3 className="mn-text-xs mn-font-semibold mn-text-text-tertiary mn-mb-2">LAYOUT</h3>
          <select onChange={e => changeLayout(e.target.value)}>
            <option value="cola">Force-Directed</option>
            <option value="concentric">Concentric</option>
            <option value="breadthfirst">Hierarchical</option>
          </select>
        </div>

        <button onClick={exportGraphPNG}>📷 Export as PNG</button>
        <button onClick={() => cyRef.current?.fit()}>⊞ Fit to Screen</button>
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="mn-flex-1" />

      {/* Node detail (if selected) */}
      {selectedNode && <NodeDetailPanel nodeId={selectedNode} onClose={() => setSelectedNode(null)} />}
    </div>
  )
}
```

---

## 5. TIMELINE PAGE (Doc 02 F-006)

Chronological view of all memory events.

### dashboard/pages/Timeline.tsx
```tsx
export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [dateRange, setDateRange] = useState<DateRange>({ from: daysAgo(30), to: now() })

  // Fetch: node creates, updates, deletions, conflict resolutions, decay events
  // Grouped by date

  return (
    <div className="mn-p-8 mn-max-w-4xl">
      <h1 className="mn-text-2xl mn-font-bold mn-mb-6">Timeline</h1>
      <DateRangePicker value={dateRange} onChange={setDateRange} />

      <div className="mn-mt-6 mn-border-l-2 mn-border-border mn-pl-6 mn-space-y-4">
        {groupByDate(events).map(([date, dayEvents]) => (
          <div key={date}>
            <h2 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-2">{date}</h2>
            {dayEvents.map(event => (
              <TimelineEventCard key={event.id} event={event} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// TimelineEventCard shows:
// - Icon by event type (created, updated, deleted, conflict, decay)
// - Node type badge + content preview
// - Timestamp
// - Click to open node detail
```

---

## 6. CONFLICT MANAGER PAGE (Doc 12 UCs 14-15, Doc 05)

Dedicated conflict resolution view (expanded from sidebar AuditTab).

### dashboard/pages/ConflictManager.tsx
```tsx
export default function ConflictManagerPage() {
  const [pending, setPending] = useState<ConflictCandidate[]>([])
  const [resolved, setResolved] = useState<ConflictCandidate[]>([])
  const [tab, setTab] = useState<'pending' | 'resolved'>('pending')

  return (
    <div className="mn-p-8 mn-max-w-5xl">
      <h1 className="mn-text-2xl mn-font-bold mn-mb-6">Conflict Manager</h1>

      <div className="mn-flex mn-gap-4 mn-mb-6">
        <TabButton active={tab === 'pending'} onClick={() => setTab('pending')}>
          Pending ({pending.length})
        </TabButton>
        <TabButton active={tab === 'resolved'} onClick={() => setTab('resolved')}>
          Resolved ({resolved.length})
        </TabButton>
      </div>

      {tab === 'pending' && pending.map(c => (
        <ConflictResolutionCard key={c.id} conflict={c}
          onResolve={(winner, custom) => handleResolve(c.id, winner, custom)} />
      ))}

      {tab === 'resolved' && resolved.map(c => (
        <ResolvedConflictCard key={c.id} conflict={c} />
      ))}
    </div>
  )
}

// ConflictResolutionCard: side-by-side nodes A vs B
// - Shows content, metadata, confidence, created_at for each
// - Radio options: "Keep A", "Keep B", "Both valid", "Custom resolution"
// - Custom resolution textarea
// - [Resolve] button
// Matches UC-15 exactly

// Entity Disambiguation Card (Gap fix — Doc 05 §2 Type 6):
// For ENTITY_DISAMBIGUATION conflicts, show different UI:
// - Shows entity name + the two different interpretations
// - Options: "Split (create separate nodes)", "Merge (same entity)", "Rename one"
// - Split mode: shows two text fields for disambiguation tags
```

### Conflict Metrics Summary (Gap fix — Doc 05 §8)

> Positioned at the top of the Conflict Manager page, above the tabs.

```tsx
function ConflictMetrics({ workspaceId }: { workspaceId: string }) {
  const [metrics, setMetrics] = useState<ConflictMetricsData | null>(null)

  useEffect(() => {
    api.getConflictMetrics(workspaceId).then(setMetrics)
  }, [workspaceId])

  if (!metrics) return null

  return (
    <div className="mn-grid mn-grid-cols-5 mn-gap-4 mn-mb-8">
      <MetricCard
        label="Auto-Resolve Rate"
        value={`${metrics.autoResolveRate}%`}
        target="> 70%"
        alert={metrics.autoResolveRate < 50}
        alertColor="danger"
      />
      <MetricCard
        label="Review Queue Depth"
        value={metrics.queueDepth}
        target="< 10 items"
        alert={metrics.queueDepth > 25}
        alertColor="warning"
      />
      <MetricCard
        label="False Positive Rate"
        value={`${metrics.falsePositiveRate}%`}
        target="< 15%"
        alert={metrics.falsePositiveRate > 25}
        alertColor="danger"
      />
      <MetricCard
        label="Resolution Latency"
        value={`${metrics.avgResolutionMs}ms`}
        target="< 100ms"
        alert={metrics.avgResolutionMs > 500}
        alertColor="warning"
      />
      <MetricCard
        label="Oldest Unresolved"
        value={`${metrics.oldestUnresolvedDays}d`}
        target="< 7 days"
        alert={metrics.oldestUnresolvedDays > 14}
        alertColor="danger"
      />
    </div>
  )
}

// MetricCard component: shows value, target badge, optional alert ring
function MetricCard({ label, value, target, alert, alertColor }: MetricCardProps) {
  return (
    <div className={`mn-bg-bg-secondary mn-rounded-lg mn-p-4 mn-border
      ${alert ? `mn-border-${alertColor}` : 'mn-border-border'}`}>
      <p className="mn-text-xs mn-text-text-tertiary mn-mb-1">{label}</p>
      <p className={`mn-text-xl mn-font-bold ${alert ? `mn-text-${alertColor}` : ''}`}>
        {value}
      </p>
      <p className="mn-text-xs mn-text-text-secondary mn-mt-1">Target: {target}</p>
    </div>
  )
}

interface ConflictMetricsData {
  autoResolveRate: number        // % of conflicts auto-resolved (target: >70%)
  queueDepth: number             // pending conflicts (target: <10)
  falsePositiveRate: number      // % conflicts dismissed as non-conflicts (target: <15%)
  avgResolutionMs: number        // avg auto-resolution latency (target: <100ms)
  oldestUnresolvedDays: number   // age of oldest pending conflict (target: <7 days)
}
```

Backend endpoint for metrics (add to `backend/routes/conflict_routes.py`):

```python
@router.get("/workspaces/{workspace_id}/conflicts/metrics")
async def conflict_metrics(workspace_id: str) -> dict:
    """Conflict health metrics per Doc 05 §8."""
    all_conflicts = await conflict_repo.get_all(workspace_id)
    pending = [c for c in all_conflicts if c.resolution_status == "pending"]
    resolved = [c for c in all_conflicts if c.resolution_status != "pending"]
    auto_resolved = [c for c in resolved if c.resolved_by == "system"]
    dismissed = [c for c in resolved if c.resolution_status == "dismissed"]

    return {
        "autoResolveRate": round(len(auto_resolved) / max(len(resolved), 1) * 100, 1),
        "queueDepth": len(pending),
        "falsePositiveRate": round(len(dismissed) / max(len(resolved), 1) * 100, 1),
        "avgResolutionMs": compute_avg_resolution_latency(resolved),
        "oldestUnresolvedDays": compute_oldest_unresolved_age(pending),
    }
```

---

## 7. SETTINGS PAGE (Doc 02 F-007, Doc 13, Doc 12 UC-22)

### dashboard/pages/Settings.tsx
```tsx
export default function SettingsPage() {
  return (
    <div className="mn-p-8 mn-max-w-3xl mn-space-y-8">
      <h1 className="mn-text-2xl mn-font-bold">Settings</h1>

      {/* Capture Settings */}
      <SettingsSection title="Capture">
        <ToggleRow label="Global capture enabled" setting="capture_enabled" />
        <ToggleRow label="Claude.ai" setting="platform_claude_enabled" />
        <ToggleRow label="ChatGPT" setting="platform_chatgpt_enabled" />
        <ToggleRow label="Gemini" setting="platform_gemini_enabled" />
      </SettingsSection>

      {/* Context Injection */}
      <SettingsSection title="Context Injection">
        <SliderRow label="Token budget" setting="token_budget" min={500} max={4000} default={2000} />
        <ToggleRow label="Auto-inject on session start" setting="auto_inject" />
      </SettingsSection>

      {/* Privacy (Doc 13, UC-22) */}
      <SettingsSection title="Privacy & Security">
        <InfoRow label="Encryption" value="AES-256 (SQLCipher)" />
        <InfoRow label="External API calls" value="0 (local only)" />
        <ToggleRow label="Cloud LLM fallback" setting="cloud_fallback_enabled" warning />
        <button onClick={openAuditLog}>View Full Audit Log</button>
        <button onClick={verifyIntegrity}>Verify Audit Log Integrity</button>
        <button onClick={openNetworkLog}>View Network Activity (UC-22)</button>
      </SettingsSection>

      {/* Custom blocked terms (Doc 13 §4.2) */}
      <SettingsSection title="Custom Blocked Terms">
        <TagInput setting="custom_blocked_terms"
          placeholder="Add terms to always block..." />
      </SettingsSection>

      {/* Danger zone */}
      <SettingsSection title="Danger Zone" danger>
        <button onClick={exportAllWorkspaces}>Export All Workspaces</button>
        <button onClick={purgeWorkspace} className="mn-text-danger">
          Purge Current Workspace
        </button>
        <button onClick={deleteEverything} className="mn-text-danger">
          Delete Everything
        </button>
      </SettingsSection>
    </div>
  )
}
```

### Privacy Audit Log View (UC-22)
```tsx
// Standalone modal/page showing network activity log
// Filters: "Network Activity", "All Actions", "Data Changes"
// Columns: Timestamp, Destination, Type (INTERNAL/EXTERNAL), Details
// Shows "External API calls: 0 | Data transmitted externally: 0 bytes"
// Verify Integrity button: validates chain_hash on entire audit log
```

---

## 8. CROSS-WORKSPACE SEARCH (Doc 02 F-011, Doc 12 UC-21)

Accessible from the dashboard header or a dedicated button.

```tsx
function CrossWorkspaceSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GroupedSearchResults>({})

  async function search(q: string) {
    if (q.length < 2) return
    const res = await api.globalSearch(q)
    // Group by workspace
    setResults(groupBy(res, r => r.workspace_name))
  }

  return (
    <div className="mn-p-8 mn-max-w-4xl">
      <SearchInput value={query} onChange={q => { setQuery(q); debouncedSearch(q) }}
        placeholder="Search across all workspaces..." />

      {Object.entries(results).map(([wsName, nodes]) => (
        <div key={wsName} className="mn-mt-6">
          <h3 className="mn-text-sm mn-font-semibold mn-text-text-secondary mn-mb-2">
            [{wsName}]
          </h3>
          {nodes.map(n => <MemoryNodeCard key={n.id} node={n} compact />)}
        </div>
      ))}
    </div>
  )
}
```

---

## 9. MY ADDITIONS FOR DASHBOARD

### 9A. Graph Diff View
When user opens the dashboard, show a "Changes since last visit" summary:
- New nodes (green)
- Updated nodes (blue)
- Archived/decayed nodes (gray)
- New conflicts (red)
Implemented as a diff overlay on the graph or a dedicated "What's New" card on Overview.

### 9B. Memory Snapshots Export
"Export as Markdown" button on Overview page — generates a human-readable snapshot:
```markdown
# Workspace: Blind Navigation Startup
## Exported: 2025-06-07

### Active Goals
- Submit hackathon demo by Sunday [HIGH]

### Recent Decisions
- Removed offline mode (Jun 3) — scope too large
...
```

### 9C. Workspace Merge
Settings → Danger Zone → "Merge Another Workspace Into This One"
- Select source workspace
- Preview: shows node counts, potential conflicts
- Merge: copies all nodes/edges, re-indexes vectors, runs conflict detection
- Source workspace archived after merge

---

## Files Summary

| File | Purpose |
|------|---------|
| `dashboard/index.html` | Dashboard entry point |
| `dashboard/app.tsx` | Root layout + routing |
| `dashboard/pages/Overview.tsx` | Health, stats, activity feed |
| `dashboard/pages/GraphExplorer.tsx` | Full-page graph with controls |
| `dashboard/pages/MemoryBrowser.tsx` | Node list, search, filter, bulk ops |
| `dashboard/pages/Timeline.tsx` | Chronological event view |
| `dashboard/pages/ConflictManager.tsx` | Conflict resolution UI |
| `dashboard/pages/Settings.tsx` | All settings + privacy audit |
| `dashboard/components/NodeDetailPanel.tsx` | Slide-in node detail |
| `dashboard/components/EditNodeModal.tsx` | Edit node modal |
| `dashboard/components/BoostNodeModal.tsx` | Boost/permanent modal |
| `dashboard/components/VersionHistoryModal.tsx` | Version timeline |
| `dashboard/components/CrossWorkspaceSearch.tsx` | Global search |
| `dashboard/components/BulkActionsBar.tsx` | Bulk select actions |
| `dashboard/components/TimelineEventCard.tsx` | Timeline entry |
| `dashboard/components/ResolvedConflictCard.tsx` | Past conflict display |
| `dashboard/components/EngineStatusFooter.tsx` | Engine health footer |
| `dashboard/components/DateRangePicker.tsx` | Date range filter |
| `dashboard/styles/dashboard.css` | Dashboard-specific styles |

**Total: ~19 files.**

---

> **Next: Plan 09 — Onboarding & Cold Start**
