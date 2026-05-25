# FIX — Plan 08: Dashboard App (Memory Audit UI)
## Fix for C-08
---

## HOW TO USE THIS FILE
Three changes: add to NAV_ITEMS, add a Route, create a new ReviewPage component.
Apply them in order.

---

## FIX C-08 — Dashboard nav missing "Review" (Pending Review) page
**Files to edit:** `dashboard/app.tsx`
**New file to create:** `dashboard/pages/ReviewPage.tsx`

### Change 1 — Add Review to NAV_ITEMS in `dashboard/app.tsx`

**Find:**
```tsx
const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: '📊' },
  { path: '/graph', label: 'Graph Explorer', icon: '🕸' },
  { path: '/memory', label: 'Memory Browser', icon: '📝' },
  { path: '/timeline', label: 'Timeline', icon: '🕐' },
  { path: '/conflicts', label: 'Conflicts', icon: '⚡' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]
```

**Replace with:**
```tsx
const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: '📊' },
  { path: '/graph', label: 'Graph Explorer', icon: '🕸' },
  { path: '/memory', label: 'Memory Browser', icon: '📝' },
  { path: '/review', label: 'Review', icon: '⚠️' },   // Doc 09 §6 — pending review workflow
  { path: '/timeline', label: 'Timeline', icon: '🕐' },
  { path: '/conflicts', label: 'Conflicts', icon: '⚡' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]
```

### Change 2 — Add Route in `dashboard/app.tsx`

**Find the Routes block:**
```tsx
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/graph" element={<GraphExplorerPage />} />
            <Route path="/memory" element={<MemoryBrowserPage />} />
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/conflicts" element={<ConflictManagerPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
```

**Replace with:**
```tsx
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/graph" element={<GraphExplorerPage />} />
            <Route path="/memory" element={<MemoryBrowserPage />} />
            <Route path="/review" element={<ReviewPage />} />  {/* Doc 09 §6 */}
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/conflicts" element={<ConflictManagerPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
```

**Also add the import at the top of `dashboard/app.tsx`:**
```tsx
import ReviewPage from './pages/ReviewPage'
```

### Change 3 — Create `dashboard/pages/ReviewPage.tsx`

**Create this new file:**

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

**Why:** Doc 09 §6 explicitly lists the full audit page sidebar navigation with these items:
Overview, Graph, Memory, **Review**, Timeline, Conflicts, Settings. The "Review" entry is the
pending review workflow — where users approve or reject low-confidence extractions before they
are committed to the knowledge graph. Without this page being reachable from the dashboard,
the pending review queue is only accessible from the sidebar inside the AI platform tab.
This defeats the purpose of the full audit UI and breaks the workflow documented in
Doc 02 Flow 3. (Ref: Doc 09 §6, Doc 02 Flow 3, C-08 conflict report)

---

## No other changes needed in Plan 08.
