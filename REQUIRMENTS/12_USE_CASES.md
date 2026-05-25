# DOCUMENT 12 — USE CASES
## 20+ Detailed Use Cases with Flows and Expected Behavior
**Project Mnemosyne**
**Version: 1.0.0**

---

## HOW TO READ THIS DOCUMENT

Each use case includes:
- **Persona** — which user type
- **Trigger** — what initiates this flow
- **Pre-conditions** — what must be true first
- **Flow** — step-by-step what happens
- **System behavior** — what Mnemosyne does internally
- **Expected output** — what the user sees
- **Edge cases** — what can go wrong

---

## SECTION A: DAILY USE FLOWS

---

### UC-01: Resume a Project After the Weekend

**Persona:** Dev Dana  
**Trigger:** Dana opens Claude on Monday morning to continue working on a backend service  
**Pre-conditions:** Dana has an active workspace "Payment Service Refactor" with 40 nodes

**Flow:**
1. Dana opens claude.ai
2. Dana types: "Let's continue with the payment service. I think we left off on the retry logic."

**System Behavior:**
- Extension detects claude.ai URL, identifies active workspace "Payment Service Refactor"
- Retrieval orchestrator pulls: active goals, recent decisions (last 14 days), open problems, tech stack
- Context string constructed (< 300ms)
- Extension injects context as system prompt prepend before first message renders

**Expected Output:**
- Injection indicator appears: `🧠 Mnemosyne: 14 items · 412 tokens`
- Claude's response already knows: the service uses FastAPI + PostgreSQL, the retry logic was last discussed on Thursday, there's an open problem with idempotency keys, and Dana prefers architecture-first discussion

**Edge Cases:**
- If retrieval takes > 500ms: inject partial context (goals + decisions only) and show "loading more context" indicator
- If workspace is ambiguous: show workspace selector popup before injection

---

### UC-02: Auto-Extraction of a Key Decision

**Persona:** Dev Dana  
**Trigger:** Dana and Claude discuss and reach a technical decision during a session  
**Pre-conditions:** Capture is enabled, workspace "Payment Service Refactor" is active

**Conversation:**
```
Dana: "Should we use idempotency keys at the API layer or in the payment processor?"
Claude: "Given your current architecture with multiple retry paths, I'd recommend implementing at the API layer — it gives you consistent protection regardless of which payment processor you use..."
Dana: "Yeah that makes sense. We'll put idempotency keys at the API gateway level."
```

**System Behavior:**
- Extension captures the turn pair
- Sensitive data filter: passes (no credentials)
- Rule-based pass: detects "We'll put... at the API gateway" → decision trigger
- NER pass: entities "idempotency keys", "API gateway", "payment processor"
- LLM pass: extracts structured decision with rationale
- Confidence score: 0.88 (above AUTO_COMMIT_THRESHOLD 0.80)
- Decision node committed to graph

**Expected Output:**
- Extension badge shows subtle "+" indicator (new extraction)
- Node committed: `{ type: "decision", content: "Idempotency keys implemented at API gateway layer", rationale: "Consistent protection across all payment processors", confidence: 0.88 }`
- No interruption to Dana's work

---

### UC-03: Low-Confidence Extraction Queued for Review

**Persona:** Research Riya  
**Trigger:** Riya discusses a research direction in a session  
**Pre-conditions:** Workspace "PhD Research: Attention Heads" is active

**Conversation:**
```
Riya: "I've been thinking that maybe the induction heads are responsible for most of the in-context learning."
Claude: "That's an interesting hypothesis. The work by Olsson et al. (2022) does suggest..."
```

**System Behavior:**
- Rule-based: no clear trigger patterns
- NER: extracts "induction heads", "in-context learning" as concepts
- LLM: extracts goal candidate: "Hypothesis: induction heads responsible for in-context learning" — but it's speculative, not confirmed
- Confidence score: 0.66 (below AUTO_COMMIT_THRESHOLD, above MIN_CONFIDENCE 0.60)
- Queued to `pending_reviews`

**Expected Output:**
- Extension badge shows yellow indicator: "1 item needs review"
- When Riya opens Audit tab: "HYPOTHESIS (66% confidence) — Induction heads responsible for most in-context learning. [Approve] [Edit] [Reject]"
- Riya clicks Edit: changes content to "Working hypothesis: investigating role of induction heads in ICL" → Approves
- Node committed with user_verified: true

---

### UC-04: Context Injection with Workspace Auto-Detection

**Persona:** Enterprise Erik  
**Trigger:** Erik opens a new ChatGPT session to work on Q3 roadmap  
**Pre-conditions:** Erik has 3 workspaces: "Q3 Roadmap", "Team OKRs", "Investor Deck"

**Flow:**
1. Erik is on chat.openai.com in a new session
2. He types: "Help me prioritize the features for Q3"

**System Behavior:**
- Extension detects chat.openai.com
- No workspace manually selected
- Intent analyzer: "Q3", "prioritize", "features" → embeds query
- Similarity scores: Q3 Roadmap 0.89, Team OKRs 0.71, Investor Deck 0.44
- Q3 Roadmap selected (above threshold 0.55)
- Context injected for Q3 Roadmap workspace

**Expected Output:**
- Injection indicator: `🧠 Mnemosyne: Q3 Roadmap · 18 items`
- ChatGPT already knows: current active goals for Q3, recent decisions about feature cuts, engineering constraints from last sprint, Erik's preference for impact/effort matrix scoring

---

### UC-05: Capture Pause for Sensitive Session

**Persona:** Dev Dana  
**Trigger:** Dana needs to share credentials with Claude to debug an API issue  
**Pre-conditions:** Mnemosyne capture is enabled

**Flow:**
1. Dana goes to extension popup
2. Clicks "Pause Capture" (single click, always visible)
3. Toggle shows "⏸ Capture Paused"
4. Dana pastes API keys, secrets, env vars into Claude
5. After debugging, Dana clicks "Resume Capture"

**System Behavior:**
- While paused: zero messages sent to extraction queue
- After resume: capture resumes from next message pair
- Audit log records: "Capture paused at 14:23:01, resumed at 14:37:45" with no content

**Expected Output:**
- Extension icon shows pause indicator
- No extraction during paused window
- On resume: badge shows normal state

**Alternative (auto-detection):**
If Dana forgets to pause and pastes an API key, the sensitive data filter catches it:
- Pattern match: `sk-[A-Za-z0-9]{32,}` → blocked
- That message pair not extracted
- If "show blocked" is enabled: faint indicator "1 message blocked for privacy"

---

## SECTION B: WORKSPACE MANAGEMENT FLOWS

---

### UC-06: Auto-Detected New Project, Workspace Creation Suggested

**Persona:** Dev Dana  
**Trigger:** Dana starts discussing a completely new project  
**Pre-conditions:** Dana has 2 existing workspaces; new conversation contains entities not in any workspace

**Conversation (new session):**
```
Dana: "I'm starting a new side project — a CLI tool for database schema diffing using Rust."
Claude: "Interesting! A Rust CLI for schema diffing. Let's talk about the design..."
```

**System Behavior:**
- Extension captures session
- Extraction: "Rust", "CLI", "database schema diffing" — new entities
- Workspace assignment: cosine similarity against all existing workspaces — max score 0.31 (below 0.55 threshold)
- Signal: NEEDS_NEW_WORKSPACE
- After 5 minutes of continued conversation: workspace suggestion fires

**Expected Output:**
- Subtle notification (not modal): `🧠 Looks like you're working on something new. Create workspace "Rust Schema Diff CLI"? [Create] [Rename] [Skip]`
- Dana clicks Create → workspace created
- Retrospective extraction runs on entire session → 12 nodes committed

---

### UC-07: Workspace Switching Between Projects

**Persona:** Dev Dana  
**Trigger:** Dana finishes one project conversation and starts another  
**Pre-conditions:** Two active workspaces: "Payment Service" and "Rust Schema Diff"

**Flow:**
1. Dana finishes Payment Service session
2. Opens new Claude tab
3. Starts discussing: "Let's work on the schema parser module today"
4. Extension auto-detects: high similarity to "Rust Schema Diff" workspace (0.82)
5. Dana sees injection indicator change: "Rust Schema Diff CLI · 8 items"

**Expected Output:**
- Correct workspace context injected automatically
- No action required from Dana
- Payment Service context is completely isolated — no bleed-through

---

### UC-08: Workspace Archival

**Persona:** Enterprise Erik  
**Trigger:** Q2 project is complete; Erik wants to archive the workspace  
**Pre-conditions:** "Q2 Product Launch" workspace has 230 nodes, status: active

**Flow:**
1. Erik opens Memory Audit page
2. Selects "Q2 Product Launch" workspace
3. Clicks "Archive Workspace"
4. Modal: "Archive this workspace? Memory will be preserved but no longer captured or injected. You can restore it anytime."
5. Erik confirms

**System Behavior:**
- Workspace status → ARCHIVED
- Capture disabled for this workspace
- Context injection disabled for this workspace
- Workspace excluded from workspace inference
- All nodes remain intact (not deleted)
- Decay rate multiplied by 0.2 (slow fade for archived content)

**Expected Output:**
- Workspace moves to "Archived" section in workspace list
- Memory intact, accessible via audit UI
- No longer appears in active workspace switcher

---

### UC-09: Workspace Export

**Persona:** Research Riya  
**Trigger:** Riya wants to export her PhD research workspace before switching laptops  
**Pre-conditions:** "PhD Research: Attention Heads" has 150 nodes spanning 8 months

**Flow:**
1. Riya opens Memory Audit, selects workspace
2. Clicks "Export" → "JSON Export"
3. File downloads: `phd_research_attention_heads_20250607.json`

**Expected Output (JSON structure):**
```json
{
  "workspace": {
    "name": "PhD Research: Attention Heads",
    "exported_at": "2025-06-07T12:00:00Z",
    "node_count": 150
  },
  "nodes": [
    {
      "id": "node_001",
      "type": "goal",
      "content": "...",
      "created_at": "...",
      "version_history": [...]
    }
  ],
  "edges": [...],
  "sessions": [...]
}
```

On new machine:
1. Install Mnemosyne
2. Import workspace from JSON
3. All nodes, edges, and version history restored
4. Vector embeddings regenerated automatically on first retrieval

---

## SECTION C: MEMORY AUDIT AND EDITING

---

### UC-10: Correcting an Incorrect Extraction

**Persona:** Dev Dana  
**Trigger:** Mnemosyne extracted the wrong technology from a hypothetical discussion  
**Pre-conditions:** Conversation contained "what if we used Cassandra?"  
**Problem:** Mnemosyne committed "Backend uses Cassandra" as TECHNICAL_FACT

**Flow:**
1. Dana opens sidebar → Memory tab → Tech Stack
2. Sees: "Backend uses Cassandra"
3. Clicks Edit
4. Changes content to: "Backend uses PostgreSQL 16 (Cassandra was briefly considered and rejected)"
5. Clicks Save

**System Behavior:**
- Old node version archived (valid_until = now)
- New version created (user_verified: true, changed_by: user)
- Audit log entry created
- Vector embedding regenerated for updated node

**Expected Output:**
- Memory immediately shows corrected content
- Version history preserved (user can see original extraction)
- Next context injection uses corrected fact

---

### UC-11: Boosting an Important Memory

**Persona:** Research Riya  
**Trigger:** Riya realizes a key insight from 2 months ago is being de-prioritized in retrieval  
**Pre-conditions:** Node "Attention heads in layer 8 show induction behavior" has decayed in importance

**Flow:**
1. Riya searches in sidebar: "induction behavior"
2. Finds the node — sees importance bar at 35%
3. Clicks "Boost" → selects "Mark as Permanent"
4. Optionally increases importance slider to 0.85

**System Behavior:**
- `is_permanent = true` — decay scheduler skips this node forever
- `importance_score = 0.85`
- `user_verified = true`
- Node moves to top of retrieval ranking

**Expected Output:**
- Node importance bar fills to 85%
- Lock icon appears (permanent)
- Next context injection includes this node prominently

---

### UC-12: Bulk Delete of Irrelevant Extractions

**Persona:** Dev Dana  
**Trigger:** Mnemosyne captured a session where Dana was testing the extraction system — lots of noise  
**Pre-conditions:** "Test Session" added 20 irrelevant nodes

**Flow:**
1. Dana opens Memory Audit
2. Filters by: "Created today" + "Source: Claude"
3. Reviews list — identifies 15 irrelevant nodes
4. Checks each (or "Select All Visible")
5. Clicks "Delete Selected" (15 items)
6. Confirmation: "Delete 15 memory nodes? This cannot be undone for hard deletes."
7. Dana selects "Soft delete (archive)" to be safe
8. Confirms

**System Behavior:**
- 15 nodes status → ARCHIVED
- Removed from retrieval
- Edges to/from archived nodes marked as inactive
- Audit log records bulk operation

---

### UC-13: Reviewing the Version History of a Node

**Persona:** Enterprise Erik  
**Trigger:** Erik wants to understand how a decision evolved over time  
**Pre-conditions:** "Mobile app launch date" node has been updated 3 times

**Flow:**
1. Erik opens Memory Audit
2. Searches "mobile launch"
3. Clicks node → Detail panel opens
4. Clicks "Version History" tab

**Expected Output:**
```
VERSION HISTORY: Mobile App Launch Date

v3 (current) — Nov 15, 2025
  "Mobile app launches November 15"
  Changed by: system (extraction)
  Source: Claude session, Nov 1

v2 — Oct 3, 2025
  "Mobile app launches October 31"
  Changed by: user (manual edit)
  Reason: "Board approval delayed"

v1 — Sep 15, 2025
  "Mobile app launches October 15"
  Changed by: system (extraction)
  Source: Claude session, Sep 15
```

---

## SECTION D: CONFLICT RESOLUTION

---

### UC-14: Auto-Resolved Direct Fact Conflict

**Persona:** Dev Dana  
**Trigger:** Two sessions contain contradictory database facts (different dates, obvious update)

**Nodes:**
- Node A (June 1): "Backend database: PostgreSQL"
- Node B (June 15): "Backend database: MongoDB (migrated from PostgreSQL)"

**System Behavior:**
- Extraction commits Node B
- Conflict detector: structural match on entity="backend database"
- Contradiction score: 0.91 (high)
- Neither node is user-verified
- Time difference: 14 days (> 24h threshold)
- Confidence gap: 0.05 (close, but auto-resolve applies)
- **Auto-resolved with temporal strategy:** Node A gets valid_until = June 15, status = SUPERSEDED
- SUPERSEDES edge created: Node B → Node A
- Resolution event logged

**Expected Output:**
- No user notification (auto-resolved)
- In Memory Audit → Resolved Conflicts: "Database fact updated June 15 (auto-resolved)"
- History preserved: "What was the database on June 1?" → returns PostgreSQL correctly

---

### UC-15: User-Resolved Ambiguous Conflict

**Persona:** Dev Dana  
**Trigger:** Two nodes conflict but auto-resolution can't determine winner

**Nodes:**
- Node A (June 1, user-verified): "Using SQLite for local storage"
- Node B (June 3, extracted): "Using IndexedDB for local storage"

**System Behavior:**
- Node A is user-verified → cannot auto-resolve
- Queued for user review

**Expected Output in Conflict UI:**
```
⚡ CONFLICT: Local Storage Technology

Node A (June 1, ✓ Verified):
"Using SQLite for local storage"

Node B (June 3):
"Using IndexedDB for local storage"

What happened?
● We use both — SQLite on backend, IndexedDB in extension
○ We switched to IndexedDB
○ Node B is wrong — still using SQLite
○ Write custom resolution: [__________]

[Resolve] [Skip]
```

Dana selects "We use both" → types: "SQLite for backend storage, IndexedDB for extension client storage" → custom resolution node created, both original nodes merged with disambiguation.

---

## SECTION E: FIRST-TIME AND ONBOARDING

---

### UC-16: First Install — Zero to First Capture (< 5 minutes)

**Persona:** Dev Dana (first-time user)  
**Trigger:** Dana installs the Chrome extension

**Flow:**
1. Extension installs from Chrome Web Store
2. Welcome screen: "What do you work on? (helps Mnemosyne get started)"
3. Dana types: "Mostly backend work — Python APIs, PostgreSQL, some ML projects"
4. System: creates first workspace "Python Backend / ML Projects" with tags
5. Dana opens Claude.ai
6. Extension detects platform, shows: "🧠 Mnemosyne active — capturing this session"
7. Dana has a 5-minute conversation about a FastAPI project
8. Extension badge: "4 extractions ready — review?"
9. Dana clicks → sees 4 cards in Audit tab
10. Approves 3, rejects 1 (a hypothetical she discussed)
11. Onboarding complete — next session gets context injection

**Expected Output:** Dana understands what the system does within 5 minutes, with zero documentation.

---

### UC-17: Onboarding — Discovering Context Injection

**Persona:** Dev Dana (day 2)  
**Trigger:** Dana opens Claude the next morning with memories from yesterday

**Flow:**
1. Dana opens Claude
2. Before she types anything, sees: `🧠 Mnemosyne injected context · 8 items · 276 tokens [▼]`
3. She expands it → sees goals, tech stack, recent decisions
4. She types: "Let's continue from yesterday"
5. Claude immediately references the FastAPI project, the endpoint design decisions, and the open problem about authentication

**Expected Output:** Dana experiences the "aha moment" — the AI already knows her project. No re-explaining.

---

## SECTION F: EDGE CASES AND FAILURE MODES

---

### UC-18: Engine Not Running (Daemon Crashed)

**Persona:** Any  
**Trigger:** Engine crashes, extension tries to inject context

**System Behavior:**
- Extension: `GET localhost:7432/health` → connection refused
- Extension switches to degraded mode

**Expected Output:**
- Injection indicator: `🧠 Mnemosyne offline — context not injected [Restart]`
- Extension badge: gray (offline)
- Capture: buffered to disk (in-browser storage) until engine restarts
- Clicking "Restart": triggers `launchctl start com.mnemosyne` (macOS) or equivalent
- On reconnect: buffered captures automatically sent

---

### UC-19: Very Long Conversation, Token Budget Exceeded

**Persona:** Research Riya  
**Trigger:** Workspace "PhD Research" has 400 nodes; token budget is 2000

**System Behavior:**
- Retrieval returns 150 candidates
- Ranking applied: top 40 nodes selected
- Token counter: still exceeds 2000
- Progressive trimming: drop lowest-ranked nodes until budget met
- Final selection: 22 nodes, 1847 tokens

**Expected Output:**
- Injection indicator: `🧠 22 of 400 items · 1847 tokens`
- User can click to see which nodes were included
- User can increase token budget in settings (up to 4000)
- Warning if they set > 4000: "Very large contexts may reduce AI performance"

---

### UC-20: Conflicting Workspace Assignment (Same Entities in Two Workspaces)

**Persona:** Dev Dana  
**Trigger:** Dana discusses Python in both "Payment Service" and "ML Project" workspaces

**System Behavior:**
- New capture: references "Python" and "FastAPI" — both workspaces have these entities
- Workspace scores: Payment Service 0.71, ML Project 0.68 (too close)
- Ambiguous assignment: prompt user

**Expected Output:**
- Extension shows: "Which workspace is this for? [Payment Service] [ML Project] [New Workspace]"
- Dana selects: "Payment Service"
- System: records URL pattern for future auto-assignment to this workspace

---

### UC-21: Cross-Workspace Search

**Persona:** Enterprise Erik  
**Trigger:** Erik searches for "vendor" across all workspaces  
**Pre-conditions:** "vendor" appears in 3 workspaces

**Flow:**
1. Erik opens Memory Audit
2. Clicks "Search All Workspaces"
3. Types "vendor"

**Expected Output:**
```
RESULTS across 3 workspaces

[Q3 Roadmap]
  DECISION: Vendor for analytics: Amplitude (Jun 3)
  ENTITY: Stripe — primary payment vendor (May 15)

[Legal & Contracts]
  TASK: Review vendor contract renewal by Aug 1 (Jun 1)

[Team OKRs]
  GOAL: Reduce vendor spend by 15% this quarter (Apr 1)
```

No context contamination — each result is clearly labeled with its workspace. Clicking a result opens that workspace's memory view.

---

### UC-22: Privacy Audit — Verify Zero Data Left Device

**Persona:** Any privacy-conscious user  
**Trigger:** User wants to verify that no conversation data was sent externally

**Flow:**
1. User opens Memory Audit → Settings → Privacy
2. Clicks "View Audit Log"
3. Filters by "Network Activity"

**Expected Output:**
```
NETWORK ACTIVITY LOG
(All network calls made by Mnemosyne)

Jun 7, 14:23  localhost:7432/capture — INTERNAL
Jun 7, 14:22  localhost:11434/api/chat — INTERNAL (Ollama local LLM)
Jun 7, 10:15  localhost:7432/context — INTERNAL
Jun 6, 09:00  pypi.org — Package update check (metadata only)

External API calls: 0
Data transmitted externally: 0 bytes
```

If user has cloud sync disabled (default), this log shows zero external calls containing user data.
