const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, Header, Footer
} = require('docx');
const fs = require('fs');

const C = {
  dark:    '1E1B4B',
  brand:   '4F46E5',
  mid:     '6366F1',
  green:   '16A34A',
  red:     'DC2626',
  amber:   'D97706',
  gray:    '6B7280',
  text:    '111827',
  lightR:  'FEF2F2',
  lightG:  'F0FDF4',
  lightA:  'FFFBEB',
  lightB:  'EEF2FF',
  tblHdr:  '312E81',
  tblAlt:  'F5F3FF',
  border:  'C7D2FE',
};

const font = 'Calibri';
const sz = 22;

const t  = (text, color = C.text, bold = false, italic = false, size = sz) =>
  new TextRun({ text, color, bold, italics: italic, size, font });
const b  = (text, color = C.text) => t(text, color, true);
const it = (text, color = C.gray) => t(text, color, false, true);
const code = (text) => new TextRun({ text, font: 'Courier New', size: 18, color: '374151' });

const sp = (before = 60, after = 60) => ({ before, after });

const para = (children, spacing = sp(), align = AlignmentType.LEFT, indent = {}) =>
  new Paragraph({ children: Array.isArray(children) ? children : [children], spacing, alignment: align, indent });

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text, bold: true, size: 40, color: C.dark, font })],
  spacing: { before: 400, after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.brand, space: 4 } }
});
const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text, bold: true, size: 28, color: C.brand, font })],
  spacing: { before: 280, after: 100 },
});
const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun({ text, bold: true, size: 22, color: C.mid, font })],
  spacing: { before: 220, after: 80 },
});

const body = (text) => new Paragraph({
  children: [new TextRun({ text, size: sz, font, color: C.text })],
  spacing: sp(),
});

const bul = (runs, level = 0) => new Paragraph({
  numbering: { reference: 'bullets', level },
  children: Array.isArray(runs) ? runs : [new TextRun({ text: runs, size: sz, font, color: C.text })],
  spacing: { before: 40, after: 40 },
});

const num = (runs, level = 0) => new Paragraph({
  numbering: { reference: 'numbers', level },
  children: Array.isArray(runs) ? runs : [new TextRun({ text: runs, size: sz, font, color: C.text })],
  spacing: { before: 40, after: 40 },
});

const gap = (n = 1) => Array.from({ length: n }, () =>
  new Paragraph({ children: [new TextRun('')], spacing: { before: 0, after: 0 } }));

const divider = () => new Paragraph({
  children: [new TextRun('')],
  border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.border, space: 4 } },
  spacing: { before: 120, after: 120 },
});

const callout = (label, labelColor, bg, lines) => {
  const paragraphs = [];
  lines.forEach((line, i) => {
    const isFirst = i === 0;
    paragraphs.push(new Paragraph({
      children: isFirst
        ? [new TextRun({ text: `  ${label}  `, bold: true, size: 18, font, color: 'FFFFFF',
            shading: { fill: labelColor, type: ShadingType.CLEAR } }),
           new TextRun({ text: `  ${line}`, size: 20, font, color: C.text })]
        : [new TextRun({ text: `  ${line}`, size: 20, font, color: C.text })],
      shading: { fill: bg, type: ShadingType.CLEAR },
      border: { left: { style: BorderStyle.SINGLE, size: 20, color: labelColor, space: 8 } },
      spacing: { before: i === 0 ? 100 : 20, after: i === lines.length - 1 ? 100 : 20 },
      indent: { left: 240, right: 240 },
    }));
  });
  return paragraphs;
};

const conflictBox = (lines) => callout('🔴 CONFLICT', C.red, C.lightR, lines);
const fixBox = (lines) => callout('✅ FIX', C.green, C.lightG, lines);
const gapBox = (lines) => callout('⚠️  MISSING', C.amber, C.lightA, lines);
const noteBox = (lines) => callout('💡 NOTE', C.brand, C.lightB, lines);

// Standard table
const tbl = (rows, hdrs, widths) => {
  const border = { style: BorderStyle.SINGLE, size: 1, color: C.border };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (text, bg, bold = false, color = C.text) =>
    new TableCell({
      borders, width: { size: widths[0], type: WidthType.DXA },
      shading: { fill: bg, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text, bold, size: 20, font, color })] })],
    });

  const tableRows = [];
  if (hdrs) {
    tableRows.push(new TableRow({
      children: hdrs.map((h, i) => new TableCell({
        borders,
        width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: C.tblHdr, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, size: 20, font, color: 'FFFFFF' })] })],
      }))
    }));
  }

  rows.forEach((row, i) => {
    const bg = i % 2 === 0 ? 'FFFFFF' : C.tblAlt;
    tableRows.push(new TableRow({
      children: row.map((cell_text, j) => new TableCell({
        borders,
        width: { size: widths[j], type: WidthType.DXA },
        shading: { fill: bg, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: cell_text, size: 20, font, color: C.text })] })],
      }))
    }));
  });

  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths,
    rows: tableRows,
  });
};

// ─── Content ──────────────────────────────────────────────────────────────────

const content = [

  // COVER
  ...gap(5),
  new Paragraph({
    children: [new TextRun({ text: 'PROJECT MNEMOSYNE', bold: true, size: 72, color: C.dark, font })],
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
  }),
  new Paragraph({
    children: [new TextRun({ text: 'Implementation Plan Review', size: 36, color: C.brand, font, italics: true })],
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
  }),
  new Paragraph({
    children: [new TextRun({ text: 'Conflicts, Gaps & Required Fixes', size: 26, color: C.mid, font })],
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 200 },
  }),
  new Paragraph({
    children: [new TextRun({ text: 'Cross-referenced against Requirements Documents 00–17', size: 22, color: C.gray, font, italics: true })],
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
  }),
  ...gap(2),
  new Paragraph({
    children: [new TextRun({ text: 'Plans Reviewed: 00–12  |  Total Issues Found: 11  |  Severity: 4 Critical · 4 Moderate · 3 Minor', size: 20, color: C.gray, font })],
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
  }),
  ...gap(8),
  new Paragraph({ children: [new PageBreak()] }),

  // ─── SUMMARY TABLE ────────────────────────────────────────────────────────
  h1('Executive Summary'),
  body('All 13 implementation plans (Plan 00–12) were reviewed against the 18 requirement documents. Below is the full issue inventory. Each issue is then detailed with its exact location, the requirement it violates, and the precise code fix required.'),
  ...gap(1),

  tbl([
    ['01', 'Plan 01', 'CRITICAL', 'Extra ConflictType enum values break SQL CHECK constraint in graph.db'],
    ['02', 'Plan 01', 'CRITICAL', 'WorkspaceStatus.DELETED not in Doc 07 schema — breaks DB constraint'],
    ['03', 'Plan 03', 'CRITICAL', 'Temporal conflict resolution missing 24h + confidence-gap check (Doc 05 §4)'],
    ['04', 'Plan 03', 'CRITICAL', 'Missing importance > 0.8 escalation to user review (Doc 05 §4 Strategy 2)'],
    ['05', 'Plan 04', 'MODERATE', 'Network activity middleware logs inbound requests, not outbound — logic inverted'],
    ['06', 'Plan 04', 'MODERATE', 'Workspace 50-active limit not enforced — WORKSPACE_FULL 409 never raised'],
    ['07', 'Plan 07/08', 'MODERATE', 'EditNodeModal/BoostNodeModal are blocking modals — violates Doc 14 UI Law'],
    ['08', 'Plan 07', 'MODERATE', 'Incognito mode missing from popup — Doc 14 requires one-click from extension icon'],
    ['09', 'Plan 01', 'MINOR', 'NodeStatus.DECAYED not in Doc 04 schema — creates undefined state path'],
    ['10', 'Plan 01', 'MINOR', 'REVIEW_THRESHOLD constant missing — confidence routing boundary undefined'],
    ['11', 'Plan 12', 'MINOR', 'NL Graph Query (Addition #11) must enforce workspace_id scoping — Doc 14 §2'],
  ],
  ['#', 'Plan', 'Severity', 'Issue'],
  [360, 720, 1080, 6480]),

  ...gap(1),
  body('All 12 additions in Plan 12 are reviewed separately in Section 9. None violate core requirements — they are additive. One requires a scoping guard.'),

  new Paragraph({ children: [new PageBreak()] }),

  // ─── ISSUE 1 ──────────────────────────────────────────────────────────────
  h1('Section 1 — Critical Issues'),

  h2('Issue #01 — Extra ConflictType Values Break SQL CHECK Constraint'),
  h3('Plan 01  ·  backend/models/enums.py  ·  CRITICAL'),
  ...gap(1),

  body('Plan 01 adds four new ConflictType enum values beyond what Doc 05 and Doc 07 define:'),
  ...gap(1),
  ...conflictBox([
    'Plan 01 ConflictType enum adds: GOAL_CONFLICT, VERSION_FORK, SCOPE_CONTRADICTION, LOGICAL_INCONSISTENCY',
    'Doc 07 §2.4 SQL CHECK constraint allows ONLY: DIRECT_FACT, GOAL_STATE, SEMANTIC_DRIFT, PREFERENCE, LOGICAL_ERROR, ENTITY_DISAMBIGUATION',
    'Any row inserted with the new enum values will raise a CHECK constraint violation and crash the extraction pipeline.',
    'The comment in Plan 01 says "must be added to SQL CHECK constraint" but the schema in Plan 01 does NOT update it.',
  ]),
  ...gap(1),
  body('The requirement source is Doc 07 §2.4 (conflict_events table) and Doc 05 §2 (the authoritative conflict type taxonomy). The schema and the enum must be identical.'),
  ...gap(1),
  ...fixBox([
    'OPTION A (Recommended): Remove the 4 extra enum values. Doc 05 defines 6 types deliberately — they cover all cases.',
    'OPTION B: If the team decides the new types add value, update the SQL CHECK constraint in Plan 01 §DB Schema to include them.',
    '',
    'Fix in backend/models/enums.py — remove these lines:',
    '    GOAL_CONFLICT = "goal_conflict"',
    '    VERSION_FORK = "version_fork"',
    '    SCOPE_CONTRADICTION = "scope_contradiction"',
    '    LOGICAL_INCONSISTENCY = "logical_inconsistency"',
    '',
    'OR update Plan 01 SQL CHECK to:',
    "    CONSTRAINT valid_conflict_type CHECK (conflict_type IN (",
    "        'DIRECT_FACT', 'GOAL_STATE', 'SEMANTIC_DRIFT', 'PREFERENCE',",
    "        'LOGICAL_ERROR', 'ENTITY_DISAMBIGUATION',",
    "        'GOAL_CONFLICT', 'VERSION_FORK', 'SCOPE_CONTRADICTION', 'LOGICAL_INCONSISTENCY'",
    "    ))",
  ]),

  divider(),

  h2('Issue #02 — WorkspaceStatus.DELETED Breaks DB Constraint'),
  h3('Plan 01  ·  backend/models/enums.py  ·  CRITICAL'),
  ...gap(1),

  body('Plan 01 adds a DELETED value to WorkspaceStatus. This does not exist in the schema.'),
  ...gap(1),
  ...conflictBox([
    'Plan 01 WorkspaceStatus enum: ACTIVE, ARCHIVED, PAUSED, DELETED',
    'Doc 07 §3.1 workspaces table SQL CHECK: status IN (\'ACTIVE\', \'ARCHIVED\', \'PAUSED\')',
    'If workspace deletion logic sets status = "deleted", the DB write fails with a CHECK constraint violation.',
    'Doc 08 §5 DELETE /workspaces/{id} — the correct behavior is hard deletion of the row, not a status transition.',
  ]),
  ...gap(1),
  ...fixBox([
    'Remove DELETED from WorkspaceStatus enum. Workspace deletion is a hard row delete, not a status change.',
    '',
    'Fix in backend/models/enums.py:',
    '    class WorkspaceStatus(str, Enum):',
    '        ACTIVE = "active"',
    '        ARCHIVED = "archived"',
    '        PAUSED = "paused"',
    '        # DELETED removed — deletion = hard row delete per Doc 08 §5',
    '',
    'In workspace_service.py delete(): call node_repo.hard_delete() + sqlite DELETE FROM workspaces.',
    'Do not set status field at all.',
  ]),

  divider(),

  h2('Issue #03 — Temporal Conflict Resolution Missing 24h + Confidence-Gap Check'),
  h3('Plan 03  ·  backend/services/conflict_service.py  ·  CRITICAL'),
  ...gap(1),

  body('Doc 05 §4 Strategy 1 defines three explicit conditions for temporal auto-resolution. Plan 03 only checks one of them.'),
  ...gap(1),
  ...conflictBox([
    'Doc 05 §4 Strategy 1 — ALL THREE conditions required for auto-resolve:',
    '  (1) Both nodes same type',
    '  (2) Time difference > 24 hours',
    '  (3) Neither node is user-verified',
    '',
    'Plan 03 _can_auto_resolve() checks ONLY condition (3): user_verified = False.',
    'Conditions (1) and (2) are completely missing.',
    '',
    'Result: a conflict between a node created 5 minutes ago and one created 4 minutes ago',
    'would be auto-resolved temporally — when it should go to user review.',
    'A conflict between a GOAL and a TECHNICAL_FACT of different types would also auto-resolve — incorrect.',
  ]),
  ...gap(1),
  ...fixBox([
    'Fix _can_auto_resolve() in conflict_service.py to add the two missing checks:',
    '',
    '    def _can_auto_resolve(self, node_a: MemoryNode, node_b: MemoryNode,',
    '                           strategy: ConflictStrategy) -> bool:',
    '        # Condition 1: Never auto-resolve user-verified (Doc 14)',
    '        if node_a.user_verified or node_b.user_verified:',
    '            return False',
    '',
    '        # Condition 2: Strategy must not require user review',
    '        if strategy == ConflictStrategy.USER_REVIEW:',
    '            return False',
    '',
    '        # Condition 3 (NEW — Doc 05 §4): For TEMPORAL strategy,',
    '        # both nodes must be same type AND time diff > 24h',
    '        if strategy == ConflictStrategy.TEMPORAL:',
    '            if node_a.node_type != node_b.node_type:',
    '                return False',
    '            time_diff = abs((node_b.created_at - node_a.created_at).total_seconds())',
    '            if time_diff < 86400:  # 24 hours',
    '                return False',
    '',
    '        return True',
  ]),

  divider(),

  h2('Issue #04 — Missing Importance > 0.8 Escalation to User Review'),
  h3('Plan 03  ·  backend/services/conflict_service.py  ·  CRITICAL'),
  ...gap(1),

  body('Doc 05 §4 Strategy 2 defines a fourth condition for forcing user review that Plan 03 does not implement at all.'),
  ...gap(1),
  ...conflictBox([
    'Doc 05 §4 Strategy 2 — Use User Review when ANY of these are true:',
    '  (1) Either node is user-verified',
    '  (2) Confidence scores are close (within 0.1)',
    '  (3) Conflict type is SEMANTIC_DRIFT or PREFERENCE',
    '  (4) Node importance > 0.8   ← ENTIRELY MISSING from Plan 03',
    '',
    'Plan 03 _classify_strategy() handles (1), (2), and (3) but has no check for (4).',
    'High-importance nodes (critical facts, key decisions) can be silently auto-resolved.',
    'This violates the intent of the requirement: high-stakes conflicts must surface to the user.',
  ]),
  ...gap(1),
  ...fixBox([
    'Fix _classify_strategy() in conflict_service.py — add the importance check:',
    '',
    '    def _classify_strategy(self, conflict: ConflictCandidate,',
    '                            node_a: MemoryNode, node_b: MemoryNode) -> ConflictStrategy:',
    '        # Force user review for high-importance nodes (Doc 05 §4 Strategy 2)',
    '        if node_a.importance_score > 0.8 or node_b.importance_score > 0.8:',
    '            return ConflictStrategy.USER_REVIEW',
    '',
    '        # Force user review if either is user-verified',
    '        if node_a.user_verified or node_b.user_verified:',
    '            return ConflictStrategy.USER_REVIEW',
    '',
    '        # Force user review if confidence scores are close (within 0.1)',
    '        conf_gap = abs(node_a.extraction_confidence - node_b.extraction_confidence)',
    '        if conf_gap < 0.1:',
    '            return ConflictStrategy.USER_REVIEW',
    '',
    '        # SEMANTIC_DRIFT and PREFERENCE always go to user review',
    '        if conflict.conflict_type in (ConflictType.SEMANTIC_DRIFT, ConflictType.PREFERENCE):',
    '            return ConflictStrategy.USER_REVIEW',
    '',
    '        # Default: temporal for DIRECT_FACT, GOAL_STATE',
    '        return ConflictStrategy.TEMPORAL',
  ]),

  new Paragraph({ children: [new PageBreak()] }),

  // ─── SECTION 2: MODERATE ─────────────────────────────────────────────────
  h1('Section 2 — Moderate Issues'),

  h2('Issue #05 — Network Activity Middleware Logic Is Inverted'),
  h3('Plan 04  ·  backend/main.py  ·  MODERATE'),
  ...gap(1),

  body('The network activity logging middleware in Plan 04 is designed to log outbound requests (to Ollama, GitHub update check, etc.) for the privacy audit. Its condition is inverted — it currently logs inbound API calls instead.'),
  ...gap(1),
  ...conflictBox([
    'Plan 04 network_activity_logger middleware condition:',
    '    if not request.url.path.startswith("/api"):',
    '        await state.network_repo.log(..., is_internal=True)',
    '',
    'This logs every request that does NOT start with /api — meaning health checks, websocket,',
    'and any non-API route. These are all INBOUND requests from the extension.',
    '',
    'Outbound requests (to Ollama on port 11434, to GitHub releases API, etc.) are NOT',
    'intercepted by FastAPI middleware at all — they are made by httpx inside service code.',
    'The middleware cannot catch them.',
  ]),
  ...gap(1),
  ...fixBox([
    'The middleware approach cannot log outbound requests. Remove the flawed middleware.',
    'Instead, add logging directly in the two places that make external calls:',
    '',
    '    # In update_service.py — after GitHub API call:',
    '    await network_repo.log(',
    '        destination="api.github.com",',
    '        purpose="update_check",',
    '        is_internal=False,',
    '        data_sent="none — read-only version check"',
    '    )',
    '',
    '    # In llm_extractor.py — before each Ollama call:',
    '    await network_repo.log(',
    '        destination="localhost:11434",',
    '        purpose="llm_extraction",',
    '        is_internal=True,  # Ollama runs locally',
    '        data_sent="extraction_prompt_only_no_raw_content"',
    '    )',
    '',
    'Delete the network_activity_logger middleware from main.py entirely.',
  ]),

  divider(),

  h2('Issue #06 — 50 Active Workspace Limit Not Enforced'),
  h3('Plan 04  ·  backend/routes/workspace_routes.py  ·  MODERATE'),
  ...gap(1),

  body('Doc 02 §F-002 acceptance criteria defines a hard limit of 50 active workspaces. Doc 08 §13 defines the WORKSPACE_FULL 409 error code for this. Neither is implemented in Plan 04.'),
  ...gap(1),
  ...conflictBox([
    'Doc 02 §F-002 Acceptance Criteria: "Maximum 50 active workspaces per user"',
    'Doc 08 §13 Error Codes: WORKSPACE_FULL → HTTP 409 — "Max node count reached"',
    '',
    'Plan 04 POST /workspaces route has no count check before creating a new workspace.',
    'A user can create unlimited workspaces — the 409 WORKSPACE_FULL error is never raised.',
    '',
    'Note: Doc 00 clarifies that 50 is the product-enforced limit; 100 is the storage design ceiling.',
  ]),
  ...gap(1),
  ...fixBox([
    'Add limit check at the top of the POST /workspaces handler:',
    '',
    '    @router.post("/workspaces", status_code=201)',
    '    async def create_workspace(body: CreateWorkspaceRequest, ...):',
    '        # Doc 02 §F-002: max 50 active workspaces',
    '        active_count = await workspace_service.count_active()',
    '        if active_count >= 50:',
    '            raise HTTPException(',
    '                status_code=409,',
    '                detail={',
    '                    "code": "WORKSPACE_FULL",',
    '                    "message": "Maximum of 50 active workspaces reached.",',
    '                    "hint": "Archive unused workspaces to create new ones."',
    '                }',
    '            )',
    '        # ... rest of creation logic',
    '',
    'Add count_active() method to WorkspaceService:',
    '    async def count_active(self) -> int:',
    '        return await self.workspace_repo.count(status=WorkspaceStatus.ACTIVE)',
  ]),

  divider(),

  h2('Issue #07 — EditNodeModal and BoostNodeModal Are Blocking Modals'),
  h3('Plan 07 and Plan 08  ·  sidebar/MemoryTab.tsx, dashboard/pages/MemoryBrowserPage.tsx  ·  MODERATE'),
  ...gap(1),

  body('Doc 14 §5 (UI Laws) contains an absolute prohibition on modal dialogs that interrupt AI interaction. Plan 07 and Plan 08 both use modals for editing and boosting nodes within the sidebar — which overlays directly on top of the AI platform.'),
  ...gap(1),
  ...conflictBox([
    'Doc 14 §5 Engineering Law (non-negotiable):',
    '    "DON\'T: Create any modal dialogs that interrupt AI interaction."',
    '    "Mnemosyne runs alongside AI platforms. We must never disrupt the user\'s flow."',
    '    "Notifications are badges and banners, never blocking modals."',
    '',
    'Plan 07 sidebar/MemoryTab.tsx:',
    '    onEdit={(id) => openEditModal(id)}  → <EditNodeModal />',
    '    onBoost={(id) => openBoostModal(id)} → <BoostNodeModal />',
    '',
    'Plan 08 dashboard: EditNodeModal, BoostNodeModal, VersionHistoryModal all as blocking overlays.',
    '',
    'The sidebar is injected directly over Claude.ai/ChatGPT. A blocking modal overlay on the sidebar',
    'covers the AI platform interface — a direct violation of this law.',
  ]),
  ...gap(1),
  ...fixBox([
    'Replace all blocking modals in the sidebar with inline expansion panels:',
    '',
    '    // INSTEAD OF opening a modal:',
    '    // <EditNodeModal node={node} />',
    '',
    '    // USE inline expand: clicking Edit expands the card in place',
    '    const [editingId, setEditingId] = useState<string | null>(null)',
    '',
    '    <MemoryNodeCard',
    '      node={node}',
    '      isEditing={editingId === node.id}',
    '      onEdit={() => setEditingId(node.id)}',
    '      onEditCancel={() => setEditingId(null)}',
    '      onEditSave={(data) => { handleSave(data); setEditingId(null) }}',
    '    />',
    '',
    'The card expands to show edit fields inline. The AI platform remains fully visible.',
    '',
    'For the Dashboard (Plan 08): modals are acceptable there because the dashboard is a',
    'dedicated full-page new tab — it does NOT overlay an AI platform. Keep modals in dashboard.',
    'Only the sidebar (Plan 07) must use inline editing.',
  ]),

  divider(),

  h2('Issue #08 — Incognito Mode Missing from Popup'),
  h3('Plan 07  ·  popup/index.tsx  ·  MODERATE'),
  ...gap(1),

  body('Doc 14 §5 and Doc 02 §F-007 both require incognito mode to be accessible directly from the extension icon popup. Plan 07 does not include it.'),
  ...gap(1),
  ...conflictBox([
    'Doc 14 §5 UI Law: "DO: Make disable/pause always one click away."',
    '    "Capture toggle. Injection disable. These must be accessible from the extension icon."',
    '',
    'Doc 02 §F-007 Acceptance Criteria: "Incognito mode toggled from extension icon"',
    '',
    'Plan 07 popup/index.tsx has: Capture toggle, Open Sidebar, Memory Audit, Settings.',
    'Incognito mode (capture nothing for this session) is absent from the popup.',
    '',
    'The background.ts in Plan 06 has pauseCapture() but no incognito toggle.',
    'The Zustand store has no incognito state.',
  ]),
  ...gap(1),
  ...fixBox([
    '1. Add incognitoMode to Zustand store (mnemosyneStore.ts):',
    '    incognitoMode: boolean',
    '    toggleIncognito: () => void',
    '',
    '2. Add to popup/index.tsx — below the capture toggle:',
    '    <button onClick={toggleIncognito}',
    '      className={`mn-w-full mn-mt-2 mn-py-2 mn-rounded-lg mn-text-sm mn-font-medium',
    '        ${incognitoMode',
    '          ? "mn-bg-purple-900 mn-text-purple-200 mn-border mn-border-purple-500"',
    '          : "mn-bg-surface-hover mn-text-text-secondary"}`,}>',
    '      {incognitoMode ? "🕵️ Incognito ON — Nothing captured" : "🕵️ Incognito Mode"}',
    '    </button>',
    '',
    '3. Add purple badge indicator to extension icon when incognito is active (background.ts):',
    '    if (incognitoMode) {',
    '      chrome.action.setBadgeText({ text: "prv" })',
    '      chrome.action.setBadgeBackgroundColor({ color: "#7C3AED" })',
    '    }',
    '',
    '4. In observer.ts: before sending any capture, check incognitoMode from storage.',
    '    If true, drop the capture without sending to engine.',
  ]),

  new Paragraph({ children: [new PageBreak()] }),

  // ─── SECTION 3: MINOR ────────────────────────────────────────────────────
  h1('Section 3 — Minor Issues'),

  h2('Issue #09 — NodeStatus.DECAYED Creates Undefined State Path'),
  h3('Plan 01  ·  backend/models/enums.py  ·  MINOR'),
  ...gap(1),

  body('Plan 01 adds NodeStatus.DECAYED beyond the four statuses defined in Doc 04 and Doc 07. This is not a schema violation (Plan 01 correctly adds it to the SQL CHECK constraint), but it creates a state path not defined in any requirement document.'),
  ...gap(1),
  ...conflictBox([
    'Doc 04 §2.1 defines four node statuses: ACTIVE, ARCHIVED, PENDING_REVIEW, SUPERSEDED.',
    'Doc 07 §2.1 CHECK constraint: status IN (\'ACTIVE\', \'ARCHIVED\', \'PENDING_REVIEW\', \'SUPERSEDED\')',
    '',
    'Plan 01 adds DECAYED and correctly updates the CHECK constraint to include it.',
    'However, no requirement doc specifies what DECAYED means vs ARCHIVED.',
    '',
    'Doc 04 §8 (decay system) says decayed nodes are ARCHIVED — not given a new status.',
    'The decay worker in Plan 03 correctly sets status = NodeStatus.ARCHIVED for decayed nodes.',
    'DECAYED is unused by any service in the plans — it is defined but never set anywhere.',
  ]),
  ...gap(1),
  ...fixBox([
    'Remove NodeStatus.DECAYED from enums.py. Decayed nodes become ARCHIVED per Doc 04 §8.',
    'Revert the SQL CHECK constraint to the four canonical values.',
    '',
    'If the team wants to distinguish "decayed archive" from "manually archived" in future,',
    'this can be done via a separate "archive_reason" column — not a new status value.',
    '',
    '    class NodeStatus(str, Enum):',
    '        ACTIVE = "active"',
    '        ARCHIVED = "archived"',
    '        SUPERSEDED = "superseded"',
    '        PENDING_REVIEW = "pending_review"',
    '        # DECAYED removed — decayed nodes use ARCHIVED per Doc 04 §8',
  ]),

  divider(),

  h2('Issue #10 — REVIEW_THRESHOLD Constant Missing'),
  h3('Plan 01/02  ·  backend/extraction/confidence_scorer.py  ·  MINOR'),
  ...gap(1),

  body('Doc 14 §3 defines three confidence thresholds as named constants. Plan 02 implements two of them but is missing REVIEW_THRESHOLD, leaving the routing boundary implicit and inconsistent.'),
  ...gap(1),
  ...conflictBox([
    'Doc 14 §3 defines all three constants explicitly:',
    '    AUTO_COMMIT_THRESHOLD = 0.80',
    '    MIN_CONFIDENCE = 0.60',
    '    REVIEW_THRESHOLD = 0.60   ← defined in requirements as a named constant',
    '',
    'Plan 02 confidence_scorer.py has:',
    '    AUTO_COMMIT_THRESHOLD = 0.80  ✓',
    '    MIN_CONFIDENCE = 0.60         ✓',
    '    REVIEW_THRESHOLD              ✗ missing',
    '',
    'The routing logic in Plan 00 uses "0.60 <= confidence < 0.80" correctly but relies on',
    'the literal 0.60 rather than the named constant. If MIN_CONFIDENCE is ever changed,',
    'the routing boundary silently breaks.',
  ]),
  ...gap(1),
  ...fixBox([
    'Add REVIEW_THRESHOLD to confidence_scorer.py and use it in the router:',
    '',
    '    AUTO_COMMIT_THRESHOLD = 0.80',
    '    MIN_CONFIDENCE = 0.60',
    '    REVIEW_THRESHOLD = MIN_CONFIDENCE  # Same value — named separately for clarity',
    '',
    '    # In ExtractionRouter.route():',
    '    if candidate.confidence >= AUTO_COMMIT_THRESHOLD:',
    '        return CandidateStatus.AUTO_COMMITTED',
    '    elif candidate.confidence >= REVIEW_THRESHOLD:',
    '        return CandidateStatus.PENDING_REVIEW',
    '    else:',
    '        return CandidateStatus.DISCARDED',
    '',
    'This ensures any future threshold change updates both boundaries consistently.',
  ]),

  divider(),

  h2('Issue #11 — NL Graph Query Must Enforce Workspace Scoping'),
  h3('Plan 12  ·  Addition #11 — Natural Language Graph Query  ·  MINOR'),
  ...gap(1),

  body('Plan 12 Addition #11 adds a natural language graph query feature. It is a good enhancement but its implementation sketch does not include the mandatory workspace_id scoping required by Doc 14 §2.'),
  ...gap(1),
  ...conflictBox([
    'Doc 14 §2 Architecture Law (non-negotiable):',
    '    "DO: Keep every operation workspace-scoped."',
    '    "Every query, every write, every retrieval must include a workspace_id."',
    '    "Global state is the enemy."',
    '',
    'Plan 12 Addition #11 NL query sketch does not show workspace_id filtering.',
    'A natural language query like "What decisions did I make about the database?" must',
    'only search within the ACTIVE workspace — never across all workspaces.',
    '',
    'Cross-workspace contamination is defined as a critical bug in Doc 14 §2.',
  ]),
  ...gap(1),
  ...fixBox([
    'Ensure all NL Graph Query endpoints and service calls include workspace_id:',
    '',
    '    # Route — workspace_id MUST be path param, not optional query param',
    '    @router.post("/workspaces/{workspace_id}/query")',
    '    async def natural_language_query(',
    '        workspace_id: str,',
    '        body: NLQueryRequest,',
    '        _=Depends(verify_token)',
    '    ) -> NLQueryResponse:',
    '        ...',
    '',
    '    # Service — all downstream calls receive workspace_id',
    '    async def nl_query(self, workspace_id: str, query: str) -> list[MemoryNode]:',
    '        # Embed query',
    '        embedding = await self.embedding_service.embed(query)',
    '        # Semantic search SCOPED to workspace',
    '        results = await self.qdrant.search(',
    '            collection_name=workspace_id,  # Workspace-scoped collection',
    '            query_vector=embedding,',
    '            limit=20',
    '        )',
    '        # Graph expansion also scoped',
    '        return await self.node_repo.get_active(workspace_id, node_ids=[r.id for r in results])',
  ]),

  new Paragraph({ children: [new PageBreak()] }),

  // ─── SECTION 4: PLAN 12 ADDITIONS ─────────────────────────────────────────
  h1('Section 4 — Plan 12 Additions Review'),
  body('Plan 12 lists 12 features added beyond the 18 requirement documents. None violate any requirement law. All are additive. Below is the assessment of each.'),
  ...gap(1),

  tbl([
    ['1', 'Conversation Thread Tracking', '✅ APPROVED', 'Sessions table already in Doc 07 §2.6. This extends it cleanly with thread_nodes linkage. No conflicts.'],
    ['2', 'Smart Context Templates', '✅ APPROVED', 'Doc 08 §4 GET /context already returns injection_format. Templates formalize per-platform formatting. No conflicts.'],
    ['3', 'Memory Snapshots (Markdown)', '✅ APPROVED', 'Export/import is in Doc 02 §F-006. Markdown variant is additive. No conflicts.'],
    ['4', 'Workspace Templates', '✅ APPROVED', 'Not in requirements but does not conflict. Useful cold-start enhancement per Doc 17.'],
    ['5', 'Extraction Feedback Loop', '✅ APPROVED', 'Doc 14 §3 says "allow users to correct any extraction." Feeding rejections back to scoring is a natural extension.'],
    ['6', 'Keyboard-First Command Palette', '✅ APPROVED', 'CommandPalette.tsx is already in Plan 00 file structure. Formalizes the component.'],
    ['7', 'Graph Diff View', '✅ APPROVED', 'Temporal versioning (Doc 04 §4) makes this possible. Additive visualization.'],
    ['8', 'Multi-Model Embedding Support', '✅ APPROVED', 'Doc 11 lists BGE-M3 as default. Hot-swap capability is a hardware optimization, no conflicts.'],
    ['9', 'Offline Extension Buffer', '✅ APPROVED', 'Doc 14 §2: "extension must degrade gracefully when engine offline." IndexedDB buffer is the correct implementation of this law.'],
    ['10', 'Workspace Merge', '✅ APPROVED', 'Additive feature, no conflicts. Ensure merged workspace retains both audit logs.'],
    ['11', 'Natural Language Graph Query', '⚠️  APPROVED WITH FIX', 'Approved but requires workspace_id scoping (Issue #11 above).'],
    ['12', 'Session Replay', '✅ APPROVED', 'Builds on Thread Tracking (#1). Shows extraction provenance — strengthens transparency law (Doc 14 §8).'],
  ],
  ['#', 'Addition', 'Status', 'Notes'],
  [360, 2160, 1440, 5400]),

  new Paragraph({ children: [new PageBreak()] }),

  // ─── SECTION 5: COMPLETE FIX CHECKLIST ────────────────────────────────────
  h1('Section 5 — Complete Fix Checklist'),
  body('The following is a prioritized, ordered checklist of every required change. Fix critical issues before any code review of the affected plans.'),
  ...gap(1),

  h2('Critical — Fix Before Merging Any Plan 01/03 Code'),
  ...gap(1),
  num('ISSUE #01 — Plan 01: Remove 4 extra ConflictType values OR update SQL CHECK constraint in graph.db schema to match.'),
  num('ISSUE #02 — Plan 01: Remove WorkspaceStatus.DELETED. Workspace deletion = hard row delete, not status transition.'),
  num('ISSUE #03 — Plan 03: Add same-type check AND 24h time-diff check to _can_auto_resolve() for TEMPORAL strategy.'),
  num('ISSUE #04 — Plan 03: Add importance > 0.8 check at top of _classify_strategy() to force USER_REVIEW escalation.'),
  ...gap(1),

  h2('Moderate — Fix Before UI Code Review'),
  ...gap(1),
  num('ISSUE #05 — Plan 04: Remove inverted network middleware. Add outbound logging directly in update_service.py and llm_extractor.py.'),
  num('ISSUE #06 — Plan 04: Add 50-workspace active limit check to POST /workspaces. Raise WORKSPACE_FULL 409 when exceeded.'),
  num('ISSUE #07 — Plan 07: Replace sidebar EditNodeModal and BoostNodeModal with inline card expansion panels. Dashboard modals are fine.'),
  num('ISSUE #08 — Plan 07: Add incognito mode toggle to popup/index.tsx. Add incognitoMode state to Zustand store. Add purple badge to extension icon.'),
  ...gap(1),

  h2('Minor — Fix Before Final Test Pass'),
  ...gap(1),
  num('ISSUE #09 — Plan 01: Remove NodeStatus.DECAYED. Decayed nodes use ARCHIVED per Doc 04 §8. Revert CHECK constraint.'),
  num('ISSUE #10 — Plan 02: Add REVIEW_THRESHOLD = MIN_CONFIDENCE constant and use it in extraction router logic.'),
  num('ISSUE #11 — Plan 12: Ensure NL Graph Query uses workspace_id as mandatory path parameter on route and in all service calls.'),
  ...gap(1),

  h2('Plan 12 Additions — One Conditional Approval'),
  ...gap(1),
  num('Addition #11 (NL Query): Workspace scope fix required. All other 11 additions approved as-is.'),

  divider(),
  ...gap(1),

  body('After these fixes are applied, the implementation plans are fully consistent with requirements Documents 00–17. No new features need to be removed — only the 4 critical bugs corrected, 4 moderate gaps filled, and 3 minor inconsistencies cleaned up.'),
  ...gap(2),

  new Paragraph({
    children: [new TextRun({ text: 'Total files requiring changes: 6', bold: true, size: 24, font, color: C.brand })],
    alignment: AlignmentType.CENTER, spacing: sp(80, 40),
  }),
  new Paragraph({
    children: [new TextRun({
      text: 'backend/models/enums.py  ·  conflict_service.py  ·  confidence_scorer.py  ·  main.py  ·  workspace_routes.py  ·  popup/index.tsx',
      size: 20, font, color: C.gray, italics: true
    })],
    alignment: AlignmentType.CENTER, spacing: sp(40, 80),
  }),
];

const doc = new Document({
  numbering: {
    config: [
      { reference: 'bullets',
        levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: 'numbers',
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  styles: {
    default: { document: { run: { font, size: sz } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 40, bold: true, font, color: C.dark },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 28, bold: true, font, color: C.brand },
        paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, font, color: C.mid },
        paragraph: { spacing: { before: 220, after: 80 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [new TextRun({ text: 'Project Mnemosyne — Implementation Plan Review', size: 18, color: C.gray, font })],
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.border, space: 4 } },
        })]
      })
    },
    children: content,
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/mnt/user-data/outputs/Mnemosyne_Plan_Review.docx', buf);
  console.log('Done');
});
