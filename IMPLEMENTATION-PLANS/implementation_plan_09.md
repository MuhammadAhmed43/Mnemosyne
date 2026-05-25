# Plan 09 — Onboarding & Cold Start

> Covers: Doc 17 (Cold Start — full), Doc 02 §4 Flow 1 (First-Time Setup), Doc 12 UC-16/UC-17 (First Install / Discovering Injection), Doc 09 §10 (Empty States)

---

## 1. ONBOARDING PAGE (extension/onboarding/)

Full-page onboarding flow opened on first install. Multi-step wizard — no back buttons on early screens (linear flow).

### extension/onboarding/index.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Welcome to Mnemosyne</title>
  <link rel="stylesheet" href="../styles/design-system.css" />
  <link rel="stylesheet" href="./onboarding.css" />
</head>
<body class="mn-bg-bg-primary mn-text-text-primary">
  <div id="onboarding-root"></div>
  <script src="./app.tsx" type="module"></script>
</body>
</html>
```

### extension/onboarding/app.tsx — Wizard Root
```tsx
const STEPS = ['welcome', 'engine', 'workspace', 'ready'] as const
type Step = typeof STEPS[number]

export default function OnboardingApp() {
  const [step, setStep] = useState<Step>('welcome')
  const [engineStatus, setEngineStatus] = useState<'checking' | 'found' | 'not_found'>('checking')
  const [workspace, setWorkspace] = useState<{ name: string; description: string } | null>(null)

  // On mount: log install_complete event
  useEffect(() => {
    api.logOnboardingEvent('install_complete')
  }, [])

  return (
    <div className="mn-min-h-screen mn-flex mn-items-center mn-justify-center">
      <div className="mn-w-[520px] mn-mx-auto">
        {step === 'welcome' && <WelcomeScreen onNext={() => setStep('engine')} />}
        {step === 'engine' && (
          <EngineCheckScreen
            status={engineStatus}
            setStatus={setEngineStatus}
            onNext={() => setStep('workspace')}
          />
        )}
        {step === 'workspace' && (
          <WorkspaceCreateScreen
            onCreated={(ws) => { setWorkspace(ws); setStep('ready') }}
          />
        )}
        {step === 'ready' && <ReadyScreen workspace={workspace!} />}
      </div>
    </div>
  )
}
```

---

## 2. SCREEN 1 — WELCOME (Doc 17 §3 Step 1)

```tsx
function WelcomeScreen({ onNext }: { onNext: () => void }) {
  return (
    <div className="mn-text-center mn-space-y-6 mn-animate-fadeSlideIn">
      <div className="mn-text-5xl">🧠</div>
      <h1 className="mn-text-3xl mn-font-bold">Mnemosyne</h1>
      <p className="mn-text-lg mn-text-text-secondary mn-max-w-md mn-mx-auto">
        AI that remembers everything you build.
      </p>
      <div className="mn-border-t mn-border-border mn-my-6" />
      <p className="mn-text-text-secondary">
        You explain your project once.<br />
        Every AI conversation after that starts with full context — automatically.
      </p>
      <button onClick={onNext}
        className="mn-bg-accent mn-text-white mn-px-8 mn-py-3 mn-rounded-lg
                   mn-font-medium mn-text-lg hover:mn-bg-accent-hover mn-transition">
        Get Started →
      </button>
    </div>
  )
}
```

**Rules from Doc 17:** No feature list, no screenshots, no marketing. One sentence value prop. Single CTA only.

---

## 3. SCREEN 2 — ENGINE CHECK (Doc 17 §3 Step 2)

```tsx
function EngineCheckScreen({ status, setStatus, onNext }) {
  const [platform, setPlatform] = useState<'macos' | 'windows' | 'linux'>('windows')

  // Poll localhost:7432/health every 3 seconds
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('https://localhost:7432/health')
        if (res.ok) {
          setStatus('found')
          api.logOnboardingEvent('engine_install_complete')
          clearInterval(interval)
        }
      } catch { setStatus('not_found') }
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  if (status === 'checking') return <SkeletonLoader lines={4} />

  if (status === 'found') {
    return (
      <div className="mn-text-center mn-space-y-4 mn-animate-fadeSlideIn">
        <div className="mn-text-4xl">✓</div>
        <h2 className="mn-text-xl mn-font-semibold">Engine running · v1.0.0</h2>
        <p className="mn-text-text-secondary">
          Your data is stored locally at:<br />
          <code className="mn-text-sm mn-bg-bg-tertiary mn-px-2 mn-py-1 mn-rounded">
            {platform === 'windows' ? '%APPDATA%\\Mnemosyne\\' : '~/.mnemosyne/'}
          </code>
        </p>
        <button onClick={onNext} className="mn-bg-accent mn-text-white mn-px-8 mn-py-3 mn-rounded-lg">
          Continue →
        </button>
      </div>
    )
  }

  // Engine not found — show download
  return (
    <div className="mn-text-center mn-space-y-4 mn-animate-fadeSlideIn">
      <h2 className="mn-text-xl mn-font-semibold">One more thing — install the local engine.</h2>
      <p className="mn-text-text-secondary">
        Mnemosyne runs entirely on your machine.<br />
        No cloud. No subscription. Your data never leaves your device.
      </p>

      <a href={DOWNLOAD_URLS[platform]}
        className="mn-inline-block mn-bg-accent mn-text-white mn-px-8 mn-py-3 mn-rounded-lg">
        ↓ Download Mnemosyne Engine ({PLATFORM_LABELS[platform]})
        <span className="mn-block mn-text-xs mn-opacity-70">Version 1.0.0 · 78 MB</span>
      </a>

      <div className="mn-flex mn-justify-center mn-gap-3 mn-text-sm mn-text-text-secondary">
        {(['macos', 'windows', 'linux'] as const).filter(p => p !== platform).map(p => (
          <button key={p} onClick={() => setPlatform(p)} className="mn-underline">{PLATFORM_LABELS[p]}</button>
        ))}
      </div>

      <p className="mn-text-sm mn-text-text-tertiary mn-mt-4">
        After install, come back here. This page will update automatically.
      </p>

      {/* Animated polling indicator */}
      <div className="mn-flex mn-items-center mn-justify-center mn-gap-2 mn-text-sm mn-text-text-tertiary">
        <span className="mn-animate-pulse mn-w-2 mn-h-2 mn-bg-accent mn-rounded-full" />
        Waiting for engine...
      </div>
    </div>
  )
}

const DOWNLOAD_URLS = {
  macos: 'https://github.com/mnemosyne/engine/releases/latest/download/Mnemosyne.pkg',
  windows: 'https://github.com/mnemosyne/engine/releases/latest/download/MnemosyneSetup.exe',
  linux: 'https://github.com/mnemosyne/engine/releases/latest/download/mnemosyne.deb',
}
```

**Key behavior:** Page auto-transitions when engine responds — user clicks nothing.

---

## 4. SCREEN 3 — FIRST WORKSPACE (Doc 17 §3 Step 3)

```tsx
function WorkspaceCreateScreen({ onCreated }) {
  const [description, setDescription] = useState('')
  const [name, setName] = useState('')
  const [suggesting, setSuggesting] = useState(false)

  // Auto-suggest name after 600ms pause (Doc 17 §3)
  const suggestName = useDebouncedCallback(async (desc: string) => {
    if (desc.length < 10) return
    setSuggesting(true)
    const suggested = await api.suggestWorkspaceName(desc)
    setName(suggested)
    setSuggesting(false)
  }, 600)

  async function handleCreate() {
    const ws = await api.createWorkspace({ name, description })
    await api.logOnboardingEvent('first_workspace_created', { workspace_id: ws.id })
    onCreated(ws)
  }

  return (
    <div className="mn-space-y-6 mn-animate-fadeSlideIn">
      <h2 className="mn-text-xl mn-font-semibold">What are you working on right now?</h2>

      <div>
        <textarea value={description}
          onChange={e => { setDescription(e.target.value); suggestName(e.target.value) }}
          placeholder='e.g. "a blind navigation startup", "my ML research", "client project X"'
          className="mn-w-full mn-h-24 mn-px-4 mn-py-3 mn-bg-bg-tertiary mn-border mn-border-border
                     mn-rounded-lg mn-resize-none" />
      </div>

      <div>
        <label className="mn-text-sm mn-text-text-secondary">Give it a name</label>
        <input value={name} onChange={e => setName(e.target.value)}
          placeholder={suggesting ? 'Suggesting...' : 'Workspace name'}
          className="mn-w-full mn-mt-1 mn-px-4 mn-py-3 mn-bg-bg-tertiary mn-border mn-border-border mn-rounded-lg" />
      </div>

      <button onClick={handleCreate} disabled={!name.trim()}
        className="mn-w-full mn-bg-accent mn-text-white mn-py-3 mn-rounded-lg mn-font-medium
                   disabled:mn-opacity-40">
        Create Workspace →
      </button>

      <p className="mn-text-sm mn-text-text-tertiary mn-text-center">
        You can have up to 50 workspaces. Create more anytime.
      </p>
    </div>
  )
}
```

---

## 5. SCREEN 4 — READY / REDIRECT (Doc 17 §3 Step 4)

```tsx
function ReadyScreen({ workspace }) {
  // Auto-redirect after 5 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      window.open('https://claude.ai', '_blank')
    }, 5000)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="mn-text-center mn-space-y-6 mn-animate-fadeSlideIn">
      <div className="mn-text-4xl">✓</div>
      <h2 className="mn-text-xl mn-font-semibold">"{workspace.name}" ready</h2>
      <p className="mn-text-text-secondary">
        Now go talk to your AI. Mnemosyne will learn in the background.
      </p>

      <a href="https://claude.ai" target="_blank"
        className="mn-inline-block mn-bg-accent mn-text-white mn-px-8 mn-py-3 mn-rounded-lg mn-font-medium">
        → Open Claude.ai
      </a>

      <div className="mn-flex mn-justify-center mn-gap-4 mn-text-sm">
        <a href="https://chat.openai.com" target="_blank" className="mn-text-text-secondary hover:mn-text-accent">ChatGPT</a>
        <a href="https://gemini.google.com" target="_blank" className="mn-text-text-secondary hover:mn-text-accent">Gemini</a>
      </div>
    </div>
  )
}
```

---

## 6. QUICK-ADD FORM (Doc 17 §6)

Shown inside sidebar immediately after first workspace creation.

### extension/sidebar/QuickAddForm.tsx
```tsx
export default function QuickAddForm({ workspaceId, onComplete, onSkip }) {
  const [goal, setGoal] = useState('')
  const [techStack, setTechStack] = useState('')
  const [keyPerson, setKeyPerson] = useState('')

  async function handleSubmit() {
    await api.quickAdd(workspaceId, { goal, tech_stack: techStack, key_person: keyPerson })
    await api.logOnboardingEvent('quick_add_submitted')
    onComplete()
  }

  return (
    <div className="mn-p-4 mn-space-y-4 mn-animate-fadeSlideIn">
      <h3 className="mn-text-sm mn-font-semibold">Jump-start your workspace (optional)</h3>
      <p className="mn-text-xs mn-text-text-secondary">Tell Mnemosyne a few things to start:</p>

      <LabeledInput label="Current goal" value={goal} onChange={setGoal}
        placeholder="e.g. Ship MVP by Friday" />
      <LabeledInput label="Tech stack" value={techStack} onChange={setTechStack}
        placeholder="e.g. Python, FastAPI, PostgreSQL" />
      <LabeledInput label="Key person" value={keyPerson} onChange={setKeyPerson}
        placeholder="e.g. Dr. Chen (mentor)" />

      <div className="mn-flex mn-gap-3">
        <button onClick={handleSubmit}
          className="mn-flex-1 mn-bg-accent mn-text-white mn-py-2 mn-rounded-lg mn-text-sm">
          Save & Start
        </button>
        <button onClick={() => { api.logOnboardingEvent('quick_add_skipped'); onSkip() }}
          className="mn-flex-1 mn-py-2 mn-rounded-lg mn-text-sm mn-text-text-secondary
                     mn-border mn-border-border">
          Skip — I'll let it learn
        </button>
      </div>
    </div>
  )
}
```

Nodes created from quick-add: `user_verified=true`, `extraction_confidence=1.0`, `source_platform="manual"`, high importance. Immediately visible in graph and included in first context injection.

---

## 7. FIRST CAPTURE NOTIFICATION (Doc 17 §3 Step 5)

### extension/background.ts — Notification Logic
```typescript
// After 3+ extractions from first session, fire notification
async function checkFirstCaptureNotification(extractionCount: number, nodes: ExtractedNode[]) {
  const state = await getOnboardingState()
  if (state.first_notification_sent) return
  if (extractionCount < 3) return

  // Show Chrome notification with actual content (Doc 17 rule: never generic)
  const items = nodes.slice(0, 4).map(n =>
    `• ${TYPE_LABELS[n.node_type]}: ${truncate(n.content, 50)}`
  ).join('\n')

  chrome.notifications.create('first-capture', {
    type: 'basic',
    iconUrl: 'icons/icon-128.png',
    title: `🧠 Mnemosyne captured ${extractionCount} things`,
    message: items,
    buttons: [{ title: 'Review' }, { title: 'Dismiss' }],
  })

  await setOnboardingState({ first_notification_sent: true })
  await api.logOnboardingEvent('first_extraction_completed', { count: extractionCount })
}

// Handle notification button clicks
chrome.notifications.onButtonClicked.addListener((id, btnIdx) => {
  if (id === 'first-capture' && btnIdx === 0) {
    chrome.sidePanel.open({})  // Open sidebar to review
  }
  chrome.notifications.clear(id)
})
```

**Rules:** Shows as Chrome notification (never modal inside AI platform). Shows actual extracted content. Dismiss = never re-show.

---

## 8. NUDGE SCHEDULE (Doc 17 §13)

### backend/services/onboarding_service.py
```python
class OnboardingService:
    NUDGE_SCHEDULE = [
        # (trigger_check, nudge_type, message)
        ('first_extraction_count >= 3', 'first_capture', 'captured {count} things'),
        ('day >= 2 and pending_count >= 3', 'pending_review', '{count} captures waiting for review'),
        ('day >= 5 and node_count >= 20', 'graph_growing', 'Your knowledge graph is growing'),
        ('day >= 7 and active', 'health_check', 'Memory health: {score}%'),
        ('day >= 14 and pending_count > 5', 'pending_urgent', '{count} unreviewed — some may expire'),
    ]

    async def check_nudges(self, workspace_id: str) -> Optional[NudgeEvent]:
        state = await self.repo.get_onboarding_state()

        # Rule: max 1 nudge per day
        if state.last_nudge_at and (now() - state.last_nudge_at).days < 1:
            return None

        # Rule: never nudge if user active in last 2 hours
        if state.last_active_at and (now() - state.last_active_at).seconds < 7200:
            return None

        for trigger, nudge_type, template in self.NUDGE_SCHEDULE:
            if self._evaluate_trigger(trigger, state) and not state.dismissed_nudges.get(nudge_type):
                # Rule: stop nudging about a feature once used
                if self._feature_already_used(nudge_type, state):
                    continue
                return NudgeEvent(type=nudge_type, message=template.format(**state.metrics))

        return None

    async def dismiss_nudge(self, nudge_type: str, permanent: bool = True):
        """Every nudge is dismissible permanently per type."""
        await self.repo.set_nudge_dismissed(nudge_type, permanent)
```

---

## 9. RETROSPECTIVE EXTRACTION (Doc 17 §12)

### extension/sidebar/RetroImport.tsx
```tsx
export default function RetroImportPanel({ workspaceId }) {
  const [text, setText] = useState('')
  const [platform, setPlatform] = useState<'claude' | 'chatgpt' | 'gemini'>('claude')
  const [result, setResult] = useState<RetroResult | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleExtract() {
    setLoading(true)
    const res = await api.retrospectiveExtraction(workspaceId, text, platform)
    setResult(res)
    setLoading(false)
  }

  return (
    <div className="mn-p-4 mn-space-y-4">
      <h3 className="mn-font-semibold">Import a past conversation</h3>
      <p className="mn-text-sm mn-text-text-secondary">
        Paste your conversation below. Mnemosyne will extract memory from it.
      </p>

      <textarea value={text} onChange={e => setText(e.target.value)}
        placeholder="[paste conversation text here]"
        className="mn-w-full mn-h-48 mn-bg-bg-tertiary mn-border mn-border-border mn-rounded-lg mn-p-3" />

      <div className="mn-flex mn-gap-3">
        <select value={platform} onChange={e => setPlatform(e.target.value)}>
          <option value="claude">Claude</option>
          <option value="chatgpt">ChatGPT</option>
          <option value="gemini">Gemini</option>
        </select>
      </div>

      <button onClick={handleExtract} disabled={!text.trim() || loading}
        className="mn-w-full mn-bg-accent mn-text-white mn-py-2 mn-rounded-lg">
        {loading ? 'Extracting...' : 'Extract Memory'}
      </button>

      <p className="mn-text-xs mn-text-text-tertiary">
        This processes locally. Nothing is sent anywhere.
      </p>

      {result && (
        <div className="mn-bg-bg-tertiary mn-rounded-lg mn-p-3 mn-text-sm">
          <p>Processed {result.turns_processed} turns</p>
          <p>{result.candidates_total} candidates → all sent to pending review</p>
        </div>
      )}
    </div>
  )
}
```

All retrospective extractions go to pending review (never auto-committed). Sensitive data filter runs on pasted text.

---

## 10. BACKEND ROUTES FOR ONBOARDING

### backend/routes/onboarding_routes.py
```python
router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

@router.post("/workspace/suggest-name")
async def suggest_workspace_name(body: SuggestNameRequest) -> SuggestNameResponse:
    """LLM-powered name suggestion from description (Doc 17 §3)."""
    name = await onboarding_service.suggest_name(body.description)
    return SuggestNameResponse(suggested_name=name)

@router.post("/quick-add")
async def quick_add(body: QuickAddRequest) -> QuickAddResponse:
    """Create manually-entered seed nodes (Doc 17 §6)."""
    nodes = await onboarding_service.process_quick_add(
        workspace_id=body.workspace_id,
        goal=body.goal, tech_stack=body.tech_stack, key_person=body.key_person
    )
    return QuickAddResponse(created_nodes=len(nodes), node_ids=[n.id for n in nodes])

@router.post("/retrospective")
async def retrospective_extraction(body: RetroRequest) -> RetroResponse:
    """Extract from pasted conversation text (Doc 17 §12)."""
    result = await onboarding_service.retrospective_extraction(
        raw_text=body.text, platform=body.platform, workspace_id=body.workspace_id
    )
    return RetroResponse(**result.dict())

@router.post("/event")
async def log_onboarding_event(body: OnboardingEventRequest):
    """Local-only onboarding event logging (Doc 17 §10)."""
    await onboarding_service.log_event(body.event_type, body.metadata)
    return {"ok": True}

@router.get("/nudge")
async def check_nudge() -> Optional[NudgeEvent]:
    """Check if a nudge should fire (Doc 17 §13)."""
    return await onboarding_service.check_nudges()
```

---

## 11. ONBOARDING DB SCHEMA (Doc 17 §14)

Already in global.db (defined in Plan 01 schema):

```sql
CREATE TABLE onboarding_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
-- Keys: install_timestamp, onboarding_completed, first_capture_at,
-- first_injection_at, aha_moment_at, nudge_schedule_state, quick_add_used

CREATE TABLE onboarding_events (
    id          TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    metadata    TEXT,  -- JSON
    timestamp   TEXT NOT NULL
);
CREATE INDEX idx_onboarding_events_type ON onboarding_events(event_type);
CREATE INDEX idx_onboarding_events_ts   ON onboarding_events(timestamp DESC);
```

---

## 12. EMPTY STATES (Doc 17 §4, Doc 09 §10)

### extension/components/EmptyStates.tsx
```tsx
// Each empty state: primary CTA + optional secondary path. Never a dead end.

export function EmptyMemoryState() {
  return (
    <EmptyContainer icon="🧠" title="Your knowledge graph starts here."
      description="Mnemosyne extracts structure automatically as you talk to your AI.">
      <PrimaryCTA href="https://claude.ai" label="Open Claude.ai and start a conversation" />
      <div className="mn-flex mn-gap-2 mn-mt-3">
        <SecondaryBtn label="+ Add goal" onClick={openQuickAddGoal} />
        <SecondaryBtn label="+ Add decision" onClick={openQuickAddDecision} />
        <SecondaryBtn label="+ Add fact" onClick={openQuickAddFact} />
      </div>
    </EmptyContainer>
  )
}

export function EmptyPendingState() {
  return (
    <EmptyContainer icon="✓" title="Nothing to review"
      description="Auto-committed extractions appear here for your review. Everything so far was high-confidence." />
  )
}

export function NoWorkspaceState() {
  return (
    <EmptyContainer icon="🧭" title="No workspaces yet."
      description="Each workspace holds the memory for one project, research area, or context.">
      <PrimaryCTA label="+ Create your first workspace" onClick={openCreateWorkspace} />
    </EmptyContainer>
  )
}

export function OfflineState() {
  return (
    <EmptyContainer icon="⚠" title="Mnemosyne engine is not running."
      description="Your browser is still working normally. No memory capture or injection is active.">
      <PrimaryCTA label="Restart Engine" onClick={restartEngine} />
      <a href="#" className="mn-text-sm mn-text-text-secondary mn-mt-2">
        Need help? → View troubleshooting guide
      </a>
    </EmptyContainer>
  )
}
```

---

## Files Summary

| File | Purpose |
|------|---------|
| `extension/onboarding/index.html` | Onboarding page entry |
| `extension/onboarding/app.tsx` | Wizard root + step router |
| `extension/onboarding/onboarding.css` | Onboarding-specific styles |
| `extension/onboarding/WelcomeScreen.tsx` | Step 1: welcome |
| `extension/onboarding/EngineCheckScreen.tsx` | Step 2: engine poll |
| `extension/onboarding/WorkspaceCreateScreen.tsx` | Step 3: first workspace |
| `extension/onboarding/ReadyScreen.tsx` | Step 4: redirect |
| `extension/sidebar/QuickAddForm.tsx` | Manual seed form |
| `extension/sidebar/RetroImport.tsx` | Retrospective extraction UI |
| `extension/components/EmptyStates.tsx` | All empty state views |
| `backend/services/onboarding_service.py` | Nudges, quick-add, retro, name suggest |
| `backend/repositories/onboarding_repo.py` | Onboarding state + events DB access |
| `backend/routes/onboarding_routes.py` | Onboarding API endpoints |

**Total: ~13 files.**

---

> **Next: Plan 10 — Testing & Benchmarks**
