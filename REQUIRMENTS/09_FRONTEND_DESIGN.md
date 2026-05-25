# DOCUMENT 09 — FRONTEND DESIGN
## UI/UX Specification, Design System, Component Library
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. DESIGN PHILOSOPHY

Mnemosyne's UI takes direct inspiration from:

| Product | What We Borrow |
|---------|---------------|
| **Linear** | Keyboard-first, minimal, blazing fast, developer trust |
| **Obsidian** | Graph visualization, local-first feel, power-user depth |
| **Raycast** | Command palette, instant results, friction-less |
| **Arc Browser** | Modern sidebar, innovative space organization |
| **Vercel** | Clean dashboard, status indicators, subtle animations |
| **Figma** | Professional tool aesthetic, canvas exploration |

**The design must communicate:**
1. Speed (everything feels instant)
2. Trust (you can see everything, control everything)
3. Intelligence (the system is working for you, not vice versa)
4. Privacy (local-first feel — nothing is "in the cloud")

---

## 2. DESIGN SYSTEM

### 2.1 Color Palette

```css
/* Foundation */
--color-bg-primary:       #0A0A0F;   /* Near-black background */
--color-bg-secondary:     #111118;   /* Card backgrounds */
--color-bg-tertiary:      #1A1A24;   /* Elevated surfaces */
--color-bg-hover:         #1E1E2E;   /* Hover states */
--color-border:           #2A2A3A;   /* Subtle borders */
--color-border-strong:    #3A3A4E;   /* Stronger dividers */

/* Brand / Accent */
--color-accent:           #7C3AED;   /* Primary purple (Mnemosyne brand) */
--color-accent-soft:      #7C3AED20; /* Accent bg tint */
--color-accent-hover:     #6D28D9;   /* Darker on hover */

/* Text */
--color-text-primary:     #F0F0F5;   /* Main text */
--color-text-secondary:   #8B8BA7;   /* Subdued text */
--color-text-tertiary:    #5A5A72;   /* Faint labels */
--color-text-disabled:    #3A3A50;

/* Semantic Colors */
--color-success:          #10B981;   /* Goals, completed */
--color-success-soft:     #10B98120;
--color-warning:          #F59E0B;   /* Pending review, conflicts */
--color-warning-soft:     #F59E0B20;
--color-danger:           #EF4444;   /* Delete, errors */
--color-danger-soft:      #EF444420;
--color-info:             #3B82F6;   /* Information, hints */
--color-info-soft:        #3B82F620;

/* Node Type Colors */
--color-node-goal:        #10B981;   /* Green */
--color-node-decision:    #7C3AED;   /* Purple */
--color-node-task:        #3B82F6;   /* Blue */
--color-node-problem:     #EF4444;   /* Red */
--color-node-entity:      #F59E0B;   /* Amber */
--color-node-preference:  #EC4899;   /* Pink */
--color-node-fact:        #6B7280;   /* Gray */
--color-node-event:       #14B8A6;   /* Teal */
```

### 2.2 Typography

```css
/* Font Stack */
--font-sans:  'Inter Variable', 'Inter', system-ui, sans-serif;
--font-mono:  'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;

/* Scale */
--text-xs:    11px / 1.5;
--text-sm:    13px / 1.5;
--text-base:  14px / 1.6;
--text-md:    15px / 1.6;
--text-lg:    17px / 1.4;
--text-xl:    20px / 1.3;
--text-2xl:   24px / 1.2;
--text-3xl:   30px / 1.1;

/* Weights */
--weight-normal:   400;
--weight-medium:   500;
--weight-semibold: 600;
--weight-bold:     700;
```

### 2.3 Spacing

```css
/* 4px base unit */
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

### 2.4 Border Radius

```css
--radius-sm:   4px;
--radius-md:   8px;
--radius-lg:   12px;
--radius-xl:   16px;
--radius-full: 9999px;
```

### 2.5 Shadows

```css
--shadow-sm:  0 1px 3px rgba(0,0,0,0.4);
--shadow-md:  0 4px 16px rgba(0,0,0,0.4);
--shadow-lg:  0 8px 32px rgba(0,0,0,0.5);
--shadow-accent: 0 0 0 1px var(--color-accent), 0 4px 16px rgba(124,58,237,0.3);
```

### 2.6 Animations

```css
--transition-fast:   120ms ease;
--transition-normal: 200ms ease;
--transition-slow:   300ms cubic-bezier(0.4, 0, 0.2, 1);

/* Micro-animation for data appearing */
@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
animation: fadeSlideIn 200ms ease;
```

---

## 3. EXTENSION POPUP (400px × 600px)

### Layout
```
┌─────────────────────────────────────┐
│ 🧠 Mnemosyne          ⚙️  [●] ON   │  ← Header: logo, settings, capture toggle
├─────────────────────────────────────┤
│                                     │
│  ACTIVE WORKSPACE                   │
│  ┌─────────────────────────────┐   │
│  │ 🧭  Blind Navigation MVP    │   │  ← Workspace card, clickable
│  │     89 memories · 2 pending │   │
│  └─────────────────────────────┘   │
│  [Switch workspace ▾]              │
│                                     │
│  LAST INJECTION                     │
│  ┌─────────────────────────────┐   │
│  │ ✓ 12 items · 347 tokens     │   │
│  │ "Goals + Recent decisions"  │   │
│  └─────────────────────────────┘   │
│                                     │
│  PENDING REVIEW                     │
│  ┌─────────────────────────────┐   │
│  │ ⚠️  2 items need review     │   │  ← Yellow indicator
│  │ [Review Now]                 │   │
│  └─────────────────────────────┘   │
│                                     │
│  [Open Memory Audit]               │  ← Opens sidebar
│                                     │
├─────────────────────────────────────┤
│  🔒 Local only · No data sent      │  ← Trust indicator
└─────────────────────────────────────┘
```

---

## 4. SIDEBAR (380px wide, injected into AI platform)

### 4.1 Overall Structure
```
┌──────────────────────────────────┐
│ 🧠 Mnemosyne              [×]   │  ← Header with close
├──────────────────────────────────┤
│ [Graph] [Memory] [Audit] [Search]│  ← Tab navigation
├──────────────────────────────────┤
│                                  │
│  [TAB CONTENT — see below]       │
│                                  │
├──────────────────────────────────┤
│ Workspace: Blind Nav MVP    [▾]  │  ← Always-visible workspace switcher
└──────────────────────────────────┘
```

### 4.2 Memory Tab (Default)

Organized by category, collapsible sections:

```
🎯 GOALS  (3 active)                [+]
├── ● Submit hackathon demo [HIGH]   ← Active = filled circle
│     Due: Sunday
├── ● Redesign retrieval
└── ○ Explore edge deployment       ← Completed = hollow circle

📋 DECISIONS  (12 total · show recent 5)
├── Removed offline mode from MVP
│   Jun 3 · reason: scope
├── Switched to monocular depth
│   Jun 5 · reason: latency
└── [Show all 12]

⚡ OPEN PROBLEMS  (3)
├── 🔴 Scene understanding in low light
├── 🟡 Latency spike in model inference
└── 🟢 Retrieval architecture unclear

🔧 TECH STACK
├── Python 3.11, FastAPI
├── ML Kit + Gemini 1.5
├── React Native (mobile)
└── [Show all 9]

👥 PEOPLE
├── Dr. Chen — Mentor
└── Amir — Co-founder

⚠️  PENDING REVIEW  (2)
└── [Review items] →
```

### 4.3 Graph Tab

Force-directed graph visualization:
- Nodes colored by type (see color system)
- Node size = importance score
- Edges labeled
- Click node → detail panel slides in from right
- Pinch/scroll to zoom
- Drag to pan
- Filter by type (checkbox row at top)
- Search bar filters visible nodes

**Node detail panel (when clicked):**
```
┌─────────────────────────────┐
│ [←]  DECISION               │
│                             │
│  "Removed offline mode      │
│   from MVP"                 │
│                             │
│  Created: Jun 3, 9:30 AM   │
│  Source: Claude             │
│  Confidence: 91%  ✓ Verified│
│  Importance: ████░░ 0.82   │
│                             │
│  RATIONALE                  │
│  Scope too large for        │
│  hackathon deadline         │
│                             │
│  CONNECTED TO               │
│  → Hackathon Goal           │
│  → Offline mode Task        │
│                             │
│  [Edit] [Boost] [Delete]   │
└─────────────────────────────┘
```

### 4.4 Audit Tab

Review pending extractions and conflicts:

**Pending Extractions:**
```
⚠️  NEEDS YOUR REVIEW

GOAL (71% confidence)
"Add obstacle avoidance by Sunday"
Source: Claude · Jun 7 · 10:30 AM

[✓ Approve]  [✎ Edit]  [✗ Reject]

─────────────────────────────────

TECHNICAL FACT (68% confidence)
"Using depth estimation model: MiDaS v3.1"
Source: Claude · Jun 7 · 10:25 AM

[✓ Approve]  [✎ Edit]  [✗ Reject]
```

**Conflicts:**
```
⚡ CONFLICT DETECTED

DATABASE: PostgreSQL vs MongoDB
Node A (Jun 1): "Backend uses PostgreSQL"
Node B (Jun 15): "Backend uses MongoDB"

What happened?
● We switched → PostgreSQL to MongoDB on Jun 15
○ These are different services
○ Write resolution: [field]

[Resolve]  [Skip]
```

### 4.5 Search Tab

```
┌─ 🔍 Search memories ─────────────┐
│ obstacle detection                │
└───────────────────────────────────┘

RESULTS  (4 found)

  PROBLEM · high importance
  "Scene understanding in low light"
  Blind Navigation MVP · Jun 5

  GOAL · completed
  "Implement obstacle avoidance layer"
  Blind Navigation MVP · Jun 3

  DECISION
  "Switched to depth-first obstacle..."
  Blind Navigation MVP · Jun 4

  TECHNICAL FACT
  "Using MiDaS v3.1 for depth..."
  Blind Navigation MVP · Jun 2
```

---

## 5. CONTEXT INJECTION INDICATOR

Appears above the AI chat input box:

```
┌─────────────────────────────────────────────────────────────┐
│ 🧠 Mnemosyne injected context  ·  12 items  ·  347 tokens  [▼] │
└─────────────────────────────────────────────────────────────┘
```

When expanded:
```
┌─────────────────────────────────────────────────────────────┐
│ 🧠 Context: Blind Navigation MVP                      [▲] [✎]│
│                                                              │
│ Goals: Submit hackathon · Redesign retrieval               │
│ Decisions: Removed offline mode · Switched to mono depth   │
│ Stack: Python, ML Kit, Gemini, FastAPI, React Native       │
│ Problems: Scene understanding in low light                  │
│                                                              │
│ [Edit before injecting]  [Disable for this session]        │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. FULL MEMORY AUDIT PAGE

Standalone page (opened from extension, renders in new tab):

### Layout
```
┌──────────────────────────────────────────────────────────────────┐
│  🧠 Mnemosyne                              [+ New Workspace]      │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [Workspaces ▾]  Blind Navigation MVP                            │
│                                                                    │
│  ┌─────────┬──────────────────────────────────────────────────┐  │
│  │ SIDEBAR │  MAIN CONTENT AREA                               │  │
│  │         │                                                    │  │
│  │ 📊 Overview │  [OVERVIEW / GRAPH / TIMELINE / SETTINGS]   │  │
│  │ 🕸 Graph    │                                               │  │
│  │ 📝 Memory   │  [Selected view content here]                │  │
│  │ ⚠️  Review  │                                               │  │
│  │ 🕐 Timeline │                                               │  │
│  │ ⚡ Conflicts│                                               │  │
│  │ ⚙️  Settings│                                               │  │
│  │         │                                                    │  │
│  └─────────┴──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Overview Panel
```
WORKSPACE HEALTH                    MEMORY BREAKDOWN
█████████░  87%                    Goals:     7 (3 active)
                                    Decisions: 12
CAPTURE STATUS                      Problems:  3 (2 open)
● Active · Last: 4 min ago          Tech Facts: 31
                                    Entities:  18
RECENT ACTIVITY                     Preferences: 8
Jun 7  3 items added
Jun 5  Decision: depth switch       PENDING REVIEW
Jun 3  2 items, 1 conflict          2 items · [Review Now →]
```

---

## 7. COMPONENT LIBRARY (React + Tailwind)

### MemoryNode Card
```tsx
interface MemoryNodeCardProps {
  node: MemoryNode;
  compact?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
  onBoost?: () => void;
}

// Compact view (list items):
// [colored dot] [content] [importance bar] [actions on hover]

// Full view (detail panel):
// Node type badge, content, structured data, metadata, version history, actions
```

### WorkspaceCard
```tsx
// Shows: icon, name, node count, health score, last active
// Compact: one line
// Full: stats breakdown
```

### ConfidenceBar
```tsx
// 0-100% filled bar
// Color: red (<60%) → yellow (60-80%) → green (>80%)
```

### NodeTypeBadge
```tsx
// Small pill: colored background, type label
// goal → green, decision → purple, task → blue, etc.
```

### ConflictResolutionCard
```tsx
// Shows both conflicting nodes side by side
// Highlights the differences
// Resolution options as radio buttons
```

---

## 8. INTERACTION PATTERNS

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+M` | Toggle Mnemosyne sidebar |
| `Cmd+K` | Open command palette |
| `Cmd+Shift+Space` | Toggle capture on/off |
| `G` | Go to graph view (when sidebar open) |
| `A` | Go to audit view |
| `S` | Go to search |
| `Esc` | Close panel / go back |
| `E` | Edit selected node |
| `D` | Delete selected node |
| `B` | Boost selected node |

### Command Palette (Cmd+K)
```
> _
─────────────────────────────
QUICK ACTIONS
  Switch to: Blind Navigation MVP
  Switch to: Fashion Research
  Open Memory Audit
  Pause Capture
  Review 2 Pending Items
  Export Workspace

MEMORY SEARCH
  Search: [type to search memories]
```

---

## 9. RESPONSIVE BEHAVIOR

### Sidebar Widths
- Default: 380px
- Compact (user can drag): 280px
- Expanded: 480px
- Minimum: 260px

### Extension Popup
- Fixed: 400px × 600px
- Not resizable

### Full Audit Page
- Min width: 1024px (designed for desktop)
- Sidebar collapses to icon bar at < 1280px

---

## 10. EMPTY STATES

### No Memories Yet
```
🧠
Start capturing

Open Claude or ChatGPT and start a conversation.
Mnemosyne will automatically extract what matters.

[Open Claude] [Open ChatGPT]
```

### No Workspace Selected
```
🧭
Choose a workspace

Select a workspace to see its memories,
or let Mnemosyne suggest one.

[Browse Workspaces] [Create New]
```

### No Search Results
```
🔍 No memories found for "obstacle"

Try broader terms, or this might not
have been captured yet.

[Search all workspaces]
```

---

## 11. LOADING STATES

All data loads should use **skeleton screens** (not spinners):

```
Memory List Loading:
┌──────────────────────────────────┐
│ ████████████░░░░░░░░░ loading   │  ← Shimmer animation
│ ████████░░░░░░ loading          │
│ ████████████████░░░░ loading    │
└──────────────────────────────────┘
```

Graph loading: Show node count first, then animate nodes appearing.

---

## 12. ACCESSIBILITY

- All interactive elements keyboard accessible
- ARIA labels on all icon-only buttons
- Contrast ratios: text ≥ 4.5:1, large text ≥ 3:1
- Focus rings visible (accent color outline)
- Screen reader announcements for extraction completions
- Respect `prefers-reduced-motion` — disable animations if set
- Color never used as sole indicator of status (always paired with text/icon)
