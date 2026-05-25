# DOCUMENT 02 — PRODUCT REQUIREMENTS DOCUMENT (PRD)
## Full Feature Specification, User Stories, Acceptance Criteria
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. PRODUCT OVERVIEW

### Product Mission
Give every AI interaction persistent, structured memory without requiring users to think about memory at all.

### Design Philosophy
- **Zero friction capture** — memory happens automatically
- **High friction delete** — losing memory should require intent
- **Instant recall** — context reconstruction feels like thought, not search
- **Radical transparency** — users always know what the system knows

---

## 2. USER PERSONAS

### Persona 1: Dev Dana
- Full-stack developer, 5 years experience
- Uses Claude daily for architecture, debugging, code review
- Works on 4-6 projects simultaneously
- Biggest pain: re-explaining the same project architecture every session
- Values: speed, accuracy, privacy, keyboard shortcuts
- Device: MacBook Pro M3, Chrome browser

### Persona 2: Research Riya
- PhD student in ML
- Uses GPT for paper synthesis, hypothesis generation
- Long-running research spanning months
- Biggest pain: AI doesn't remember previous discussions about her research direction
- Values: depth, relationships between ideas, audit trail
- Device: Ubuntu laptop, Firefox

### Persona 3: Enterprise Erik
- Product manager at a 200-person startup
- Uses AI for decision-making, stakeholder communication, roadmap planning
- Needs institutional memory that survives team turnover
- Biggest pain: onboarding new team members to project context
- Values: shareability, decision history, reliability
- Device: Windows machine, work-managed Chrome

---

## 3. FEATURE LIST

### 3.1 CORE FEATURES (Must-Have for V1)

#### F-001: Automatic Capture
**Description:** Silently intercept and process AI conversations from the browser
**Trigger:** User sends a message to Claude.ai, chat.openai.com, gemini.google.com
**Behavior:**
- Extension detects message + response pairs
- Sends to local extraction pipeline
- No user action required
- Capture indicator in extension badge

**Acceptance Criteria:**
- [ ] Captures 100% of messages on supported platforms
- [ ] Does NOT capture passwords, API keys, credit card numbers (auto-detected)
- [ ] Capture latency < 200ms (non-blocking, async)
- [ ] User can pause capture with one click
- [ ] Capture status visible in extension icon

---

#### F-002: Workspace Management
**Description:** Create, manage, and switch between isolated cognitive workspaces
**Behavior:**
- Auto-detect workspace from conversation context (suggest to user)
- Manual workspace creation
- Workspace switching
- Workspace archival
- Workspace deletion (with confirmation + export option)

**Workspace Object:**
```
{
  id: uuid,
  name: string,
  description: string,
  color: string (for UI),
  icon: string (emoji or icon),
  created_at: timestamp,
  last_active: timestamp,
  status: 'active' | 'archived' | 'paused',
  capture_enabled: boolean,
  tags: string[],
  entity_count: number,
  memory_health_score: float (0-1)
}
```

**Acceptance Criteria:**
- [ ] Create workspace in < 3 clicks
- [ ] Auto-suggest fires when new project detected (confidence > 0.8)
- [ ] Maximum 50 active workspaces per user
- [ ] Workspace switching < 100ms
- [ ] Each workspace is completely isolated (no memory leakage)

---

#### F-003: Cognitive Extraction
**Description:** Parse conversations and extract structured entities, goals, decisions, relationships
**Behavior:**
- Runs locally via lightweight extraction model
- Extracts: entities, goals, decisions, tasks, preferences, technical facts
- Assigns confidence score to each extraction
- Low-confidence extractions queued for user review
- High-confidence extractions committed automatically

**Extraction Categories:**

| Category | Examples | Auto-Commit Threshold |
|---|---|---|
| Technical Fact | "using PostgreSQL", "deployed on AWS" | 0.85 |
| Decision | "decided to remove offline mode" | 0.80 |
| Goal | "need to ship by Friday" | 0.75 |
| Entity/Person | "mentor Dr. Chen", "partner Amir" | 0.90 |
| Preference | "prefers concise answers" | 0.70 |
| Relationship | "X depends on Y", "X blocks Y" | 0.80 |
| Open Problem | "still unclear how to handle latency" | 0.75 |

**Acceptance Criteria:**
- [ ] Extraction precision > 85% on benchmark test suite
- [ ] Extraction recall > 75% on benchmark test suite
- [ ] False positive rate < 10% for auto-committed extractions
- [ ] Processing per conversation turn < 500ms
- [ ] User can reject/edit any extraction

---

#### F-004: Knowledge Graph
**Description:** Store all extracted state as a queryable, versioned, relationship-aware graph
**Behavior:**
- Each entity is a node
- Relationships are typed edges
- Every node has temporal versioning
- Nodes have importance scores
- Decay applies over time

**Node Types:**
- `Entity` (person, system, tool, concept)
- `Goal` (active, completed, abandoned)
- `Decision` (with rationale and timestamp)
- `Task` (open, completed, blocked)
- `Preference` (behavioral pattern)
- `TechnicalFact` (stack, architecture, config)
- `Problem` (open, resolved)
- `Event` (milestone, incident, meeting)

**Acceptance Criteria:**
- [ ] Graph supports 100,000+ nodes without performance degradation
- [ ] Relationship traversal < 50ms for 5-hop queries
- [ ] Node versioning stores full history
- [ ] Import/export to JSON supported

---

#### F-005: Context Reconstruction
**Description:** When user opens AI chat, inject relevant workspace context automatically
**Behavior:**
- Detect which workspace is active based on URL, tab, or user selection
- Pull relevant cognitive state for current goal/task
- Construct compressed system prompt injection
- Inject via extension before first user message
- Show user what was injected (collapsible)

**Injection Format:**
```
[MNEMOSYNE CONTEXT — Workspace: Blind Navigation Startup]

Current Goals:
• Submit hackathon demo by Sunday [HIGH PRIORITY]
• Redesign retrieval to use hybrid search [ACTIVE]

Recent Decisions:
• Removed offline mode from MVP (2025-06-03) — reason: scope
• Switched from SLAM to monocular depth (2025-06-05) — reason: latency

Technical State:
• Stack: Python 3.11, ML Kit, Gemini 1.5, FastAPI, React Native
• Architecture: Edge inference with cloud fallback
• Open Problem: scene understanding in low-light conditions

Key People: Dr. Chen (mentor), Amir (co-founder)

[Context injected by Mnemosyne — edit in sidebar]
```

**Acceptance Criteria:**
- [ ] Injection happens before first user message (< 300ms)
- [ ] User can disable injection per workspace
- [ ] User can edit the injected context
- [ ] Context size never exceeds configured token budget (default: 2000 tokens)
- [ ] Injection visible and collapsible in UI

---

#### F-006: Memory Audit UI
**Description:** Full visibility into what Mnemosyne knows, with edit/delete/approve controls
**This is the most important trust-building feature.**

**Views:**
- **Graph View** — visual knowledge graph (Obsidian-style)
- **Timeline View** — chronological memory events
- **Workspace View** — organized by category within workspace
- **Pending Review** — extractions awaiting user approval
- **Decay Queue** — memories approaching expiration

**Actions Available:**
- Edit any memory node
- Delete any memory node
- Merge duplicate nodes
- Boost importance of a node
- Mark node as permanent (no decay)
- Export workspace as structured JSON
- Purge entire workspace

**Acceptance Criteria:**
- [ ] All memories visible within 2 clicks
- [ ] Edit/delete available on every node
- [ ] Changes take effect immediately
- [ ] Bulk operations supported (select all, bulk delete)
- [ ] Search across all memories in a workspace

---

#### F-007: Privacy Controls
**Description:** Granular user control over what is captured and stored
**Behavior:**
- Global capture toggle (pause all)
- Per-workspace capture toggle
- Per-platform toggle (disable for ChatGPT, enable for Claude)
- Sensitive data auto-detection and blocking
- Incognito mode (capture nothing for session)

**Sensitive Data Patterns (Auto-Blocked):**
- API keys (regex: `[A-Za-z0-9]{32,}`, `sk-...`, `Bearer ...`)
- Passwords (context: "my password is", "password:")
- Credit card numbers (Luhn validation)
- SSN / National ID patterns
- Private keys / certificates

**Acceptance Criteria:**
- [ ] Sensitive data never written to disk
- [ ] Privacy controls accessible in < 2 clicks
- [ ] Incognito mode toggled from extension icon
- [ ] All data stored encrypted at rest (AES-256)
- [ ] User can verify zero data left device (audit log)

---

### 3.2 SECONDARY FEATURES (V1 — Nice to Have)

#### F-008: Smart Suggestions
When user opens a new AI session, suggest which workspace to activate based on:
- Tab/URL context
- Time of day patterns
- Recent activity

#### F-009: Memory Health Dashboard
Visual indicator of workspace memory quality:
- Memory freshness
- Contradiction count
- Coverage gaps
- Pending reviews

#### F-010: Conversation Summarizer
On-demand: summarize any open AI conversation and extract to workspace memory.
Useful for catching up on long conversations retroactively.

#### F-011: Cross-Workspace Search
Search for entities/facts across all workspaces.
Results clearly labeled with source workspace.
No context contamination — just search.

---

### 3.3 V2 FEATURES (Do Not Build in V1)

- Multi-user workspaces
- Cloud sync
- Mobile app
- IDE plugin (VS Code, JetBrains)
- API for third-party integrations
- Voice capture
- Email/Slack capture
- Enterprise SSO
- Team memory analytics

---

## 4. USER FLOWS

### Flow 1: First-Time Setup (< 5 minutes)
```
Install Extension
     ↓
Welcome screen → "What do you work on?" (free text)
     ↓
Auto-create first workspace from response
     ↓
Open Claude/ChatGPT
     ↓
Mnemosyne detects conversation, shows capture indicator
     ↓
After 3 messages: "We extracted 4 things. Review?" (notification)
     ↓
User reviews, approves/rejects
     ↓
Onboarding complete
```

### Flow 2: Daily Use (Zero Friction)
```
User opens Claude.ai
     ↓
Mnemosyne detects active workspace (from recent activity)
     ↓
Injects context automatically (< 300ms)
     ↓
User sees "[Mnemosyne: 3 context items injected]" indicator
     ↓
User starts typing — Claude already knows the project
     ↓
After conversation: extraction runs silently in background
     ↓
If new important info found: subtle badge on extension icon
```

### Flow 3: Memory Review (Weekly)
```
User clicks extension icon
     ↓
Opens Memory Audit
     ↓
Sees pending extractions (yellow)
     ↓
Reviews each: approve / edit / reject
     ↓
Graph view updated
     ↓
Optionally browses workspace graph
```

### Flow 4: New Project
```
User starts talking to AI about a new project
     ↓
Mnemosyne detects new entities not in any workspace
     ↓
After 5 minutes: "Looks like you're working on something new. Create workspace 'X'?"
     ↓
User confirms or adjusts name
     ↓
New workspace created, retrospective extraction runs on session
```

### Flow 5: Sensitive Data Block
```
User pastes something containing API key
     ↓
Mnemosyne detects sensitive pattern
     ↓
That message: NOT extracted, NOT stored
     ↓
If user has "show blocked" enabled: subtle indicator
     ↓
User never has to think about this
```

---

## 5. ACCEPTANCE CRITERIA SUMMARY

### Performance
- Context injection: < 300ms
- Extraction pipeline: < 500ms per turn
- Graph query: < 100ms
- UI load: < 1s
- Extension install: < 30 seconds to first capture

### Accuracy
- Extraction precision: > 85%
- False positive rate: < 10%
- Contradiction detection: > 80%
- Workspace auto-detection: > 75% accuracy

### Reliability
- Extension uptime: > 99.5%
- Local engine crash recovery: < 5s
- Data loss on crash: zero (write-ahead logging)
- Memory corruption: zero (transactional writes)

### Privacy
- Zero plaintext sensitive data on disk: verified by audit
- All storage encrypted: AES-256
- Network calls during capture: zero (unless cloud sync enabled)

---

## 6. OUT OF SCOPE (Explicitly)

The following will NOT be built and should not be designed for:

1. Any feature that requires sending conversation data to a remote server without explicit user action
2. Replay of raw conversation transcripts
3. Global memory (all workspaces share state)
4. Memory that cannot be deleted
5. Extraction that runs on the cloud
6. Social features (sharing memories between users in V1)
7. Any form of advertising or memory monetization
