# DOCUMENT 17 — COLD START
## Day 0 Experience, Onboarding, Value Curve
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. WHY COLD START IS THE HARDEST UX PROBLEM

Mnemosyne is a memory system. A memory system with no memories is, by definition, useless.

Every new user goes through a trough between installation and the moment they experience value. If that trough is too deep, too long, or too confusing — they uninstall. This document is the engineering and design spec for making that trough as shallow and short as possible.

**The cold start problem for Mnemosyne has three dimensions:**

| Dimension | The Challenge |
|-----------|--------------|
| Empty State | Nothing to show — no nodes, no graph, no context |
| Trust Deficit | User doesn't know what the system is doing or why |
| Delayed Payoff | Value only appears after real usage — can't be faked |

All three must be solved simultaneously.

---

## 2. THE VALUE CURVE

Understanding when users experience value is the foundation of onboarding design.

```
Perceived Value
     │
     │                                              ╭──────────── ONGOING VALUE
  Hi │                                        ╭────╯
     │                                  ╭─────╯
     │                            ╭─────╯
     │                      ╭─────╯    ← "Aha moment" (first real injection)
     │                ╭─────╯
  Lo │────────────────╯
     └──────────────────────────────────────────────────────
          Install   Setup   Session 1   Session 2   Session 3+
          (0 min)  (5 min)  (Day 0)     (Day 1)     (Day 2+)
```

### The "Aha Moment" Target

**Goal:** First meaningful context injection by end of Session 1.

This is the moment a user opens a second AI conversation on the same project and sees their goals, decisions, and context already waiting for them — without typing a word.

Everything in the cold start design serves this one moment.

### Why Not Fake It With Seed Data

We do NOT pre-populate the workspace with fake or example memories. Reasons:

1. Fake memories that look real destroy trust the moment they're noticed
2. Users need to see their own project reflected back — generic examples mean nothing
3. The correct approach is to make real extraction happen faster and more visibly

---

## 3. ONBOARDING FLOW — STEP BY STEP

### Step 1: Extension Install (0–60 seconds)

**Trigger:** User installs from Chrome Web Store.

**What happens:**
```
Chrome Web Store install
         ↓
Extension background worker starts
         ↓
First-run flag detected → open onboarding tab
         ↓
Tab opens: chrome-extension://[id]/onboarding.html
         ↓
Simultaneously: native installer prompt (if engine not detected)
```

**Onboarding Tab — Screen 1 (Welcome):**
```
┌──────────────────────────────────────────────────┐
│                                                  │
│              🧠 Mnemosyne                        │
│                                                  │
│    AI that remembers everything you build.       │
│                                                  │
│    ─────────────────────────────────────────     │
│                                                  │
│    You explain your project once.                │
│    Every AI conversation after that starts       │
│    with full context — automatically.            │
│                                                  │
│              [ Get Started → ]                   │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Design rules:**
- No feature list, no screenshots, no marketing copy
- One sentence explaining the value
- Single CTA only — never two buttons on the first screen

---

### Step 2: Engine Installation Check (30–120 seconds)

**What happens:**
```
Extension checks: GET localhost:7432/health
      ↓
Engine responds? → Skip to Step 3
Engine not found? → Show install prompt
```

**Screen 2A: Engine Not Found (needs install)**
```
┌──────────────────────────────────────────────────┐
│                                                  │
│   One more thing — install the local engine.     │
│                                                  │
│   Mnemosyne runs entirely on your machine.       │
│   No cloud. No subscription. Your data           │
│   never leaves your device.                      │
│                                                  │
│   ┌──────────────────────────────────────────┐   │
│   │  ↓ Download Mnemosyne Engine (macOS)     │   │
│   │    Version 1.0.0 · 78 MB                 │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   [ Windows ] [ Linux ]  ←  other platforms      │
│                                                  │
│   ─────────────────────────────────────────      │
│   After install, come back here.                 │
│   This page will update automatically. ←─ polls  │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Technical behavior:**
- Page polls `localhost:7432/health` every 3 seconds
- When engine responds, page automatically transitions to Step 3
- User does not click anything — the transition is automatic

**Screen 2B: Engine Found (already installed)**
```
┌──────────────────────────────────────────────────┐
│                                                  │
│   ✓ Engine running  · v1.0.0                     │
│                                                  │
│   Your data is stored locally at:                │
│   ~/.mnemosyne/                                  │
│                                                  │
│              [ Continue → ]                      │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

### Step 3: First Workspace — Guided Creation (60–90 seconds)

This is the most important screen. We need to get the user to name and describe their first project without calling it "workspace configuration."

**Screen 3: First Workspace**
```
┌──────────────────────────────────────────────────┐
│                                                  │
│   What are you working on right now?             │
│                                                  │
│   ┌──────────────────────────────────────────┐   │
│   │  e.g. "a blind navigation startup",      │   │
│   │  "my ML research", "client project X"    │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   Give it a name                                 │
│   ┌──────────────────────────────────────────┐   │
│   │  Blind Navigation Startup                │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   [ Create Workspace → ]                         │
│                                                  │
│   ─────────────────────────────────────────      │
│   You can have up to 50 workspaces.              │
│   Create more anytime.                           │
│                                                  │
└──────────────────────────────────────────────────┘
```

**Auto-name generation:**
When the user types in the description field and pauses for 600ms, the engine suggests a name:
```python
async def suggest_workspace_name(description: str) -> str:
    """
    Convert free-text description to a concise workspace name.
    Runs local LLM (phi4-mini) — no network call.
    """
    prompt = f"""
    Convert this description to a short workspace name (2-5 words, title case):
    "{description}"
    
    Examples:
    "building a mobile app for blind navigation" → "Blind Navigation App"
    "phd research on transformer interpretability" → "Transformer Interpretability"
    "client work for a fintech startup" → "Fintech Client Project"
    
    Return ONLY the name, nothing else.
    """
    return await local_llm.complete(prompt, max_tokens=20)
```

**Workspace is created immediately** when user clicks "Create Workspace" — they enter the app without waiting.

---

### Step 4: Redirect to First AI Session (5 seconds)

After workspace creation, the onboarding screen transitions to a "ready" state and redirects to Claude.ai (or whichever platform the user uses most, detected from browser history heuristics):

**Screen 4: Ready**
```
┌──────────────────────────────────────────────────┐
│                                                  │
│   ✓ "Blind Navigation Startup" ready             │
│                                                  │
│   Now go talk to your AI.                        │
│   Mnemosyne will learn in the background.        │
│                                                  │
│   ┌──────────────────────────────────────────┐   │
│   │  → Open Claude.ai                        │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│   [ ChatGPT ]  [ Gemini ]  [ Other ]             │
│                                                  │
└──────────────────────────────────────────────────┘
```

Auto-redirect fires after 5 seconds if user doesn't click.

---

### Step 5: First Capture — The Invisible Moment (During Session 1)

**The user starts talking to their AI. Mnemosyne silently captures.**

What the user sees in the Chrome extension badge:
- Badge turns from gray to indigo — capture is live
- After the first message pair is captured and processed: badge shows a small `1` dot
- No interruption. No modal. No toast. Just the badge.

**First extraction notification (fires after 3+ extractions):**

This is the first moment the user sees that Mnemosyne is working. It must be:
- Non-blocking
- Concise
- Specific (not generic)

```
┌────────────────────────────────────────────────┐
│  🧠 Mnemosyne captured 4 things               │
│                                                │
│  • Goal: Submit demo by Sunday                │
│  • Decision: Removed offline mode from MVP    │
│  • Fact: Stack is Python + FastAPI            │
│  • Person: Dr. Chen (mentor)                  │
│                                                │
│  [ Review ]   [ Dismiss ]                     │
└────────────────────────────────────────────────┘
```

**Critical rules for this notification:**
- Shows actual content — never generic "we captured some things"
- Appears as a Chrome notification, NOT a modal inside Claude.ai
- Review button opens the sidebar, does not navigate away
- User can dismiss — we NEVER re-show what they dismissed

---

### Step 6: First Context Injection — The Aha Moment (Start of Session 2)

When the user opens a new Claude.ai tab after having had at least one session:

```
Mnemosyne detects tab URL: claude.ai
         ↓
Identifies active workspace (Blind Navigation Startup)
         ↓
Retrieves context (< 300ms)
         ↓
Injects into system prompt
         ↓
Shows injection indicator in page
```

**Injection indicator (injected into claude.ai DOM):**
```
┌─────────────────────────────────────────────────────────┐
│ 🧠 Mnemosyne — Blind Navigation Startup  [▼ Show] [✕]  │
│                                                         │
│ 3 goals · 2 decisions · 1 open problem injected        │
└─────────────────────────────────────────────────────────┘
```

Expanded view:
```
┌─────────────────────────────────────────────────────────┐
│ 🧠 MNEMOSYNE CONTEXT — Blind Navigation Startup         │
│                                                         │
│ Goals                                                   │
│   • Submit hackathon demo by Sunday [HIGH]              │
│   • Redesign retrieval to use hybrid search             │
│                                                         │
│ Recent Decisions                                        │
│   • Removed offline mode (Jun 3) — too much scope      │
│   • Switched to monocular depth (Jun 5) — latency      │
│                                                         │
│ Technical State                                         │
│   • Python 3.11, FastAPI, ML Kit, Gemini               │
│   • Open: scene understanding in low-light             │
│                                                         │
│ Key People: Dr. Chen (mentor), Amir (co-founder)       │
│                                                         │
│   [Edit Context]   [Disable for this session]          │
└─────────────────────────────────────────────────────────┘
```

**This is the aha moment.** The user's context is there, verbatim, before they typed a word. This is what every piece of onboarding engineering exists to create.

---

## 4. EMPTY STATE DESIGN

Every screen must be designed for zero data. An empty state that says "No memories yet" is a failure.

### 4.1 Empty Workspace Graph View

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│              Your knowledge graph                    │
│              starts here.                            │
│                                                      │
│    Mnemosyne extracts structure automatically        │
│    as you talk to your AI.                          │
│                                                      │
│    ┌──────────────────────────────────────────────┐  │
│    │  → Open Claude.ai and start a conversation  │  │
│    └──────────────────────────────────────────────┘  │
│                                                      │
│    Or add something manually:                        │
│    [ + Add goal ]  [ + Add decision ]  [ + Add fact ]│
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Rule:** Every empty state has exactly one primary CTA and at least one secondary path. Never a dead end.

### 4.2 Empty Pending Review

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│    ✓ Nothing to review                               │
│                                                      │
│    Auto-committed extractions appear here            │
│    for your review.                                  │
│                                                      │
│    Everything extracted so far was high-confidence   │
│    and committed automatically.                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 4.3 Empty Workspace List (First Launch)

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│    No workspaces yet.                                │
│                                                      │
│    Each workspace holds the memory for one           │
│    project, research area, or context.              │
│                                                      │
│         [ + Create your first workspace ]            │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 4.4 Empty State — Engine Offline

If the user opens the sidebar and the engine is not running:

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│    ⚠  Mnemosyne engine is not running.               │
│                                                      │
│    Your browser is still working normally.           │
│    No memory capture or injection is active.         │
│                                                      │
│         [ Restart Engine ]                           │
│                                                      │
│    Need help? → View troubleshooting guide           │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 5. PROGRESSIVE DISCLOSURE STRATEGY

We do not explain everything upfront. We introduce features as the user is ready for them.

### Disclosure Timeline

| Trigger | Feature Introduced |
|---------|-------------------|
| Install complete | Capture is live — badge indicator only |
| First 3 extractions | "We captured 4 things" notification |
| First session ends | "Review your captures" nudge in badge |
| Second session opens | Context injection, injection indicator |
| 3 pending reviews accumulate | Review nudge notification |
| First conflict detected | Conflict resolution UI surfaced |
| 7 days active | Memory health dashboard mentioned |
| 30 days active | Decay system explained (via health score) |
| Manual request only | Graph view, import/export, advanced settings |

**Rule:** We never explain decay, conflict resolution, or graph traversal to a user who has not yet experienced a basic extraction. Every feature earns its right to be explained.

---

## 6. MANUAL QUICK-ADD (SEED FOR DAY 0)

Even before the user has had their first AI conversation, they can manually seed their workspace with a few key facts. This is a shortcut to the aha moment.

**Quick-add prompt (shown inside sidebar immediately after workspace creation):**

```
┌──────────────────────────────────────────────────────┐
│  Jump-start your workspace (optional)               │
│                                                      │
│  Tell Mnemosyne a few things to start:              │
│                                                      │
│  Current goal:  [ _____________________________ ]   │
│  Tech stack:    [ _____________________________ ]   │
│  Key person:    [ _____________________________ ]   │
│                                                      │
│  [ Save & Start ]    [ Skip — I'll let it learn ]   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Technical behavior:**
```python
async def process_quick_add(
    workspace_id: str,
    goal: Optional[str],
    tech_stack: Optional[str],
    key_person: Optional[str]
) -> List[MemoryNode]:
    """
    Converts quick-add form input into properly structured
    memory nodes with user_verified=True and max importance.
    """
    nodes = []
    
    if goal:
        nodes.append(MemoryNode(
            node_type=NodeType.GOAL,
            content=goal,
            importance_score=0.9,
            user_verified=True,
            source_platform="manual",
            extraction_confidence=1.0  # User entered it directly
        ))
    
    if tech_stack:
        nodes.append(MemoryNode(
            node_type=NodeType.TECHNICAL_FACT,
            content=f"Tech stack: {tech_stack}",
            structured_data={"entity": "stack", "value": tech_stack},
            importance_score=0.85,
            user_verified=True,
            source_platform="manual",
            extraction_confidence=1.0
        ))
    
    if key_person:
        nodes.append(MemoryNode(
            node_type=NodeType.ENTITY,
            content=key_person,
            importance_score=0.75,
            user_verified=True,
            source_platform="manual",
            extraction_confidence=1.0
        ))
    
    return await store.commit_nodes(workspace_id, nodes)
```

Manually entered nodes are:
- Immediately visible in graph (no review queue)
- Marked `user_verified=True`
- Set `is_permanent=False` (but start with high importance and slow decay)
- Included in first context injection

---

## 7. FIRST-RUN ENGINE INITIALIZATION UX

The engine has a 60–120 second first-run initialization (downloads embedding model, sets up database, generates TLS cert). We must communicate this without losing users.

### Engine Installer Progress UI

The installer shows a native progress window (not browser-based):

```
Mnemosyne Engine Setup
──────────────────────────────────────────

✓ Creating data directory
✓ Generating auth token
✓ Setting up local database
✓ Generating TLS certificate

⟳ Downloading embedding model (BGE-M3)
  [████████████░░░░░░░░░░] 67%  382 MB / 567 MB

○ Checking Ollama (optional — for enhanced extraction)
○ Starting engine

This is a one-time setup. Takes ~2 minutes.
Everything runs on your machine. Nothing is sent to a server.
```

**Rules:**
- Real-time progress, not fake progress bars
- Explain WHY each step exists in plain English
- Repeat "local, no server" during the wait — this is the right moment to build trust
- The model download is the only potentially long step — show a real percentage

### Ollama Detection

If Ollama is not installed, we show an optional side-step:

```
○ Ollama not found

  Ollama is a free tool that enables enhanced AI extraction.
  Without it, Mnemosyne uses rule-based extraction (still useful).

  [ Install Ollama (2 min) ]    [ Skip for now ]
```

**Rule:** Ollama is never required. Always skip-able. We do not block first run on Ollama.

---

## 8. WORKSPACE AUTO-DETECTION DURING COLD START

After the first workspace exists but before the user has had any sessions, the workspace detection system has no behavioral signals to work from. We handle this explicitly.

### Auto-Detection Behavior — Session 1

On first ever session in Claude.ai:
1. Extension reads page title and URL
2. Checks if it matches any open workspace by name/description
3. If match confidence > 0.75 → silently activates workspace
4. If match confidence < 0.75 → shows workspace selector banner

**Workspace selector banner (non-blocking):**
```
┌──────────────────────────────────────────────────────────┐
│  🧠 Which workspace is this conversation for?           │
│                                                          │
│  [ Blind Navigation Startup ]  [ + New Workspace ]       │
│  [ Personal Research ]         [ None — don't capture ]  │
└──────────────────────────────────────────────────────────┘
```

After the user selects once, that tab URL pattern is remembered for future sessions via `platform_mappings` table.

---

## 9. TRUST BUILDING — FIRST 24 HOURS

Users who install Mnemosyne have a legitimate privacy concern: "What is this extension sending about my conversations?"

Cold start is the best moment to answer this question proactively, before they ask.

### Trust Signals to Surface in Onboarding

| Signal | Where | How |
|--------|-------|-----|
| "Runs locally" | Welcome screen | Headline statement |
| "Nothing leaves your machine" | Engine install step | During download wait |
| "See everything we know" | First extraction notification | "Review" CTA |
| "Delete anything" | First sidebar open | Shown as core feature |
| Audit log access | Day 1 nudge | "See what Mnemosyne recorded" |
| Network monitor note | Settings | "No outbound connections" indicator |

### What We Never Do

- Never hide what was captured
- Never say "we improve our AI" — that implies training on user data
- Never send telemetry without explicit opt-in (not even crash reports by default)
- Never make it hard to delete data
- Never auto-enable cloud features that weren't explicitly requested

---

## 10. COLD START METRICS

These metrics define whether cold start is working:

| Metric | Target | Failure Threshold |
|--------|--------|-------------------|
| Time from install to first capture | < 5 min | > 15 min |
| Time from install to first injection | < 24 hours | > 72 hours |
| Onboarding completion rate | > 80% | < 60% |
| Drop-off at engine install step | < 20% | > 40% |
| Quick-add usage rate | > 40% | < 20% |
| Day 7 retention | > 50% | < 30% |
| First injection → active weekly user conversion | > 65% | < 40% |

### Tracking Approach

We do not use external analytics (no network calls, local first). Cold start metrics are tracked locally:

```python
# Stored in global.db — onboarding_events table
async def log_onboarding_event(event_type: str, metadata: dict = {}):
    """
    Local-only onboarding event log.
    Used to compute cold-start metrics for debugging and UX iteration.
    Opt-in only: user can enable anonymous reporting separately.
    """
    await db.execute("""
        INSERT INTO onboarding_events (event_type, metadata, timestamp)
        VALUES (?, ?, ?)
    """, event_type, json.dumps(metadata), datetime.utcnow().isoformat())
```

**Events tracked locally:**
- `install_complete`
- `engine_install_started`
- `engine_install_complete`
- `first_workspace_created`
- `quick_add_submitted` / `quick_add_skipped`
- `first_capture_received`
- `first_extraction_completed`
- `first_injection_fired`
- `aha_moment_confirmed` (user expanded injection indicator)

---

## 11. FAILURE MODES AND RECOVERY

### Failure: Engine Install Fails

**Cause:** Download interrupted, permission error, conflicting port.

**Recovery:**
```
┌──────────────────────────────────────────────────────┐
│                                                      │
│   ⚠  Engine setup encountered a problem             │
│                                                      │
│   Error: Port 7432 already in use                    │
│                                                      │
│   What to try:                                       │
│   1. Close any other Mnemosyne instances             │
│   2. Restart your computer and try again             │
│   3. View full error log                             │
│                                                      │
│   [ Try Again ]   [ Change Port ]   [ Get Help ]     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

The extension must remain functional even if engine setup fails — it just shows "Engine not running" status and does not capture. It does not error on every tab.

### Failure: First Extraction Produces Nothing

Some conversations (very short, purely factual Q&A) will produce no extractions on the first turn. This is correct behavior. We do not force extractions.

What to show:
- Badge stays gray (no extractions)
- After 3 conversation turns with no extractions: subtle banner "Mnemosyne is listening — it extracts structure from project conversations, not quick questions."

This teaches the user what kind of content produces extractions, without alarming them.

### Failure: User Opens Extension with No Workspaces

If the user somehow reaches a state with no workspaces (e.g., deleted all), the extension popup shows:

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│   No workspaces.                                     │
│                                                      │
│   Create one to start capturing.                     │
│                                                      │
│         [ + Create Workspace ]                       │
│                                                      │
└──────────────────────────────────────────────────────┘
```

No error message. No "empty state" label. Just the clear next action.

---

## 12. RETROSPECTIVE EXTRACTION (CATCH-UP MODE)

When a user has already been having project conversations in Claude.ai before they installed Mnemosyne, they may want to extract memory from past conversations they didn't capture.

### Catch-Up Mode UI

Accessible via: Sidebar → Workspace → "Import past conversation"

```
┌──────────────────────────────────────────────────────────┐
│  Import a past conversation                              │
│                                                          │
│  Paste your conversation below.                          │
│  Mnemosyne will extract memory from it.                  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │  [paste conversation text here]                    │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Platform: [ Claude ▾ ]    Workspace: [ Startup ▾ ]      │
│                                                          │
│  [ Extract Memory ]                                      │
│                                                          │
│  Note: This processes locally. Nothing is sent anywhere. │
└──────────────────────────────────────────────────────────┘
```

**Technical behavior:**
```python
async def retrospective_extraction(
    raw_text: str,
    platform: str,
    workspace_id: str
) -> ExtractionResult:
    """
    Runs the full extraction pipeline on pasted conversation text.
    Identical to live capture pipeline but triggered manually.
    All results go to pending review (not auto-committed).
    Reason: lower confidence without timestamp context.
    """
    # Parse into turn pairs (heuristic-based, platform-aware)
    turns = conversation_parser.parse(raw_text, platform=platform)
    
    results = []
    for turn in turns:
        capture = CaptureRecord(
            session_id=f"retro_{uuid4()}",
            platform=platform,
            user_message=turn.user,
            ai_response=turn.assistant,
            workspace_id=workspace_id,
            metadata={"source": "retrospective"}
        )
        result = await extraction_pipeline.run(capture)
        results.append(result)
    
    # All retrospective extractions go to pending review
    # (not auto-committed, regardless of confidence)
    for r in results:
        for candidate in r.candidates:
            candidate.status = CandidateStatus.PENDING_REVIEW
    
    return ExtractionResult(
        turns_processed=len(turns),
        candidates_total=sum(len(r.candidates) for r in results),
        all_pending_review=True
    )
```

**Rules:**
- Retrospective extractions always go to pending review — never auto-committed
- Sensitive data filter runs on pasted text just like live capture
- User sees a review queue populated with the results

---

## 13. THE FIRST WEEK — NUDGE SCHEDULE

After day 0, a careful nudge schedule drives users toward habits that produce retention.

| Day | Event | Nudge |
|-----|-------|-------|
| Day 0 | First extraction | "Mnemosyne captured 4 things. [Review]" |
| Day 1 | Second AI session | Context injection fires (no nudge needed — the injection IS the nudge) |
| Day 2 | If pending reviews > 3 | "3 captures waiting for your review" badge |
| Day 3 | If no session since Day 0 | (No nudge — we do not spam inactive users) |
| Day 5 | First time graph has > 20 nodes | "Your knowledge graph is growing. [View Graph]" |
| Day 7 | If active | "Memory health: 94% — Mnemosyne is up to date" |
| Day 14 | If pending reviews not cleared | "8 unreviewed captures — some may expire soon" |

**Rules for nudges:**
- Maximum 1 nudge per day
- Never nudge if user has been active in last 2 hours
- Nudges appear in extension badge and Chrome notification — never inside AI platforms
- Every nudge is dismissible — permanently, per nudge type
- We stop nudging about a feature once the user has used it once

---

## 14. ONBOARDING DATABASE SCHEMA

```sql
-- global.db addition
CREATE TABLE onboarding_state (
    key                 TEXT PRIMARY KEY,
    value               TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Keys stored:
-- 'install_timestamp'       → ISO datetime of first install
-- 'onboarding_completed'    → 'true'/'false'
-- 'first_capture_at'        → ISO datetime
-- 'first_injection_at'      → ISO datetime
-- 'aha_moment_at'           → ISO datetime (injection expanded)
-- 'nudge_schedule_state'    → JSON object tracking sent nudges
-- 'quick_add_used'          → 'true'/'false'

CREATE TABLE onboarding_events (
    id                  TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,
    metadata            TEXT,               -- JSON
    timestamp           TEXT NOT NULL
);

CREATE INDEX idx_onboarding_events_type ON onboarding_events(event_type);
CREATE INDEX idx_onboarding_events_ts   ON onboarding_events(timestamp DESC);
```

---

## 15. COLD START ACCEPTANCE CRITERIA

| # | Criteria | Verification Method |
|---|----------|---------------------|
| CS-001 | User can complete full onboarding with no external documentation | Usability test: task completion rate > 80% |
| CS-002 | Time from Chrome Web Store install to first capture < 5 minutes | Automated timing in onboarding_events |
| CS-003 | First context injection fires within 24 hours of install for active users | onboarding_events: first_injection_at delta |
| CS-004 | Engine install progress is visible and accurate — no fake progress bars | Manual QA on all three platforms |
| CS-005 | Empty states on all views have a clear primary CTA | Design review checklist |
| CS-006 | Engine failure during install shows recovery instructions, not a blank screen | Integration test: port conflict simulation |
| CS-007 | Ollama absence does not block any part of onboarding | Integration test: no Ollama installed |
| CS-008 | Quick-add form creates correctly typed memory nodes | Unit test: `test_quick_add_node_typing` |
| CS-009 | Retrospective extraction sends all results to pending review | Unit test: `test_retrospective_all_pending` |
| CS-010 | Nudge frequency never exceeds 1 per day | Unit test: `test_nudge_rate_limiter` |
| CS-011 | First injection indicator is visible in Claude.ai DOM | E2E test: Playwright on claude.ai |
| CS-012 | "Nothing leaves your device" is verifiable via network monitor | Security test: zero outbound during capture |
