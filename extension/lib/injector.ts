// Context injection indicator. These AI web UIs expose no system-prompt hook,
// so we can't silently inject. Instead we show a visible, transparent indicator
// (Doc 14 §5 — never inject invisibly) of the reconstructed context, with an
// explicit "Insert into prompt" action that prepends it to the input box.
//
// Multi-workspace handling: the bar carries a workspace dropdown. The backend
// picks an initial workspace by (1) a saved URL->workspace mapping, (2) embedding
// inference from the typed hint, (3) most-recently-active fallback. The user can
// override via the dropdown — which is remembered for this URL — and as they type
// their first message we re-infer (until they pick manually).

import { isCaptureEnabled, pauseCapture, resumeCapture } from "~lib/observer"
import type { PlatformConfig } from "~lib/platformDetector"
import { showToast } from "~lib/toast"
import type { ContextResult, Workspace } from "~lib/types"

const HOST_ID = "mnemosyne-host"
const OFFLINE_ID = "mnemosyne-offline"
const AUTO_INSERT_KEY = "mn_auto_insert"
const NEW_WS_OPTION = "__mn_new_workspace__"  // sentinel value in the workspace dropdown

// Module state survives across re-renders of the bar within one page load.
let manualPick = false // user chose a workspace from the dropdown -> stop auto-inferring
let hintWired = false // the page input listener is attached only once
let currentWsId = "" // workspace currently shown (skip redundant re-renders)
let offlineDismissed = false // user closed the offline banner this session
let autoInserted = false // auto-insert fired once for the current chat

type CtxResult = ContextResult & { status?: string }

/** Reset per-conversation state so the bar behaves fresh after SPA navigation
 *  (new chat). Removes the existing bar; flags are re-armed for the new chat. */
export function resetInjector(): void {
  document.getElementById(HOST_ID)?.remove()
  manualPick = false
  hintWired = false
  currentWsId = ""
  autoInserted = false
}

async function getAutoInsert(): Promise<boolean> {
  try {
    const v = await chrome.storage.local.get(AUTO_INSERT_KEY)
    return v[AUTO_INSERT_KEY] === true
  } catch {
    return false
  }
}

function styles(): HTMLStyleElement {
  const s = document.createElement("style")
  s.textContent = `
    .mn-bar{font-family:Inter,system-ui,sans-serif;background:#111118;color:#F0F0F5;
      border:1px solid #2A2A3A;border-radius:10px;padding:8px 12px;margin:8px auto;max-width:760px;
      font-size:13px;display:flex;align-items:center;gap:8px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
    .mn-meta{color:#8B8BA7}
    .mn-ws{background:#0A0A0F;color:#F0F0F5;border:1px solid #2A2A3A;border-radius:6px;
      padding:3px 6px;font-size:12px;max-width:200px;cursor:pointer}
    .mn-btn{margin-left:auto;background:#7C3AED;color:#fff;border:none;border-radius:6px;
      padding:4px 10px;cursor:pointer;font-size:12px}
    .mn-toggle{margin-left:0!important;background:#2A2A3A!important}
    .mn-x{background:transparent;color:#8B8BA7;border:none;cursor:pointer;font-size:14px}
    .mn-body{max-width:760px;margin:0 auto;background:#0A0A0F;border:1px solid #2A2A3A;
      border-radius:8px;padding:10px 12px;white-space:pre-wrap;font-size:12px;color:#C8C8D8;display:none}
  `
  return s
}

/** Ask the background worker for reconstructed context. tab_url lets the backend
 *  apply a saved URL->workspace mapping before any inference. */
async function fetchContext(
  config: PlatformConfig,
  opts: { hint?: string; workspace_id?: string },
): Promise<CtxResult | null> {
  return (await chrome.runtime.sendMessage({
    type: "GET_CONTEXT",
    payload: {
      platform: config.platformName,
      hint: opts.hint,
      workspace_id: opts.workspace_id,
      tab_url: location.href,
    },
  })) as CtxResult | null
}

function usable(result: CtxResult | null): result is CtxResult {
  return !!result && result.status !== "offline" && !!result.context_string && (result.nodes_included?.length ?? 0) > 0
}

export async function injectContext(config: PlatformConfig, hint?: string): Promise<void> {
  const result = await fetchContext(config, { hint })
  if (result?.status === "offline") {
    showOfflineBanner(config)
    return
  }
  document.getElementById(OFFLINE_ID)?.remove() // engine is back
  if (!usable(result)) return
  render(config, result)
  wireHintReinference(config)
  void maybeAutoInsert(config, result)
}

/** When the engine is down the bar can't render, which previously meant total
 *  silence — users couldn't tell memory had simply stopped. Show a small,
 *  dismissible banner so the failure is visible and actionable. */
function showOfflineBanner(config: PlatformConfig): void {
  if (offlineDismissed || document.getElementById(OFFLINE_ID)) return
  const host = document.createElement("div")
  host.id = OFFLINE_ID
  const shadow = host.attachShadow({ mode: "open" })
  shadow.appendChild(styles())
  const wrap = document.createElement("div")
  wrap.innerHTML = `
    <div class="mn-bar" style="border-color:#EF4444">
      <span>🧠</span>
      <span>Mnemosyne engine is offline</span>
      <span class="mn-meta">start the local app to capture &amp; recall memory</span>
      <button class="mn-x" id="mn-off-x" style="margin-left:auto">✕</button>
    </div>`
  shadow.appendChild(wrap)
  document.querySelector(config.injectionTarget)?.prepend(host)
  shadow.getElementById("mn-off-x")?.addEventListener("click", () => {
    offlineDismissed = true
    host.remove()
  })
}

/** If the user opted into auto-insert and the input is empty, place the context
 *  for them — no notice, no click, no Ctrl+V. Uses only the non-clipboard paths
 *  (a programmatic clipboard write needs a user gesture, which we don't have). */
async function maybeAutoInsert(config: PlatformConfig, result: CtxResult): Promise<void> {
  if (autoInserted || manualPick) return
  if (!(await getAutoInsert())) return
  const input = resolveEditor(config.inputSelector)
  if (!input || readInputText(input).length > 0) return // don't clobber a draft
  autoInserted = true
  const outcome = await insertIntoPrompt(config, stripWrapper(result.context_string), { auto: true })
  if (outcome === "inserted") showToast("🧠 Context auto-inserted", { sub: result.workspace_name })
}

function render(config: PlatformConfig, result: CtxResult): void {
  currentWsId = result.workspace_id
  document.getElementById(HOST_ID)?.remove()

  const host = document.createElement("div")
  host.id = HOST_ID
  const shadow = host.attachShadow({ mode: "open" })
  shadow.appendChild(styles())

  const wrap = document.createElement("div")
  wrap.innerHTML = `
    <div class="mn-bar">
      <span>🧠</span>
      <span>Mnemosyne</span>
      <select class="mn-ws" id="mn-ws" title="Active workspace — switch to use a different memory set"></select>
      <span class="mn-meta">${result.nodes_included.length} items · ${result.token_count} tokens</span>
      <button class="mn-btn mn-toggle" id="mn-auto" title="Auto-insert context into new empty chats">Auto: …</button>
      <button class="mn-btn mn-toggle" id="mn-pause" title="Pause capturing this conversation">⏸</button>
      <button class="mn-btn" id="mn-insert">Insert into prompt</button>
      <button class="mn-btn mn-toggle" id="mn-toggle">Show</button>
      <button class="mn-x" id="mn-close">✕</button>
    </div>
    <div class="mn-body" id="mn-body">${escapeHtml(stripWrapper(result.context_string))}</div>
  `
  shadow.appendChild(wrap)

  const target = document.querySelector(config.injectionTarget)
  target?.prepend(host)

  void populateWorkspaces(shadow, result.workspace_id, result.workspace_name)
  void initAutoButton(shadow)
  refreshPauseButton(shadow)

  shadow.getElementById("mn-toggle")?.addEventListener("click", () => {
    const body = shadow.getElementById("mn-body") as HTMLElement
    body.style.display = body.style.display === "block" ? "none" : "block"
  })
  shadow.getElementById("mn-close")?.addEventListener("click", () => host.remove())

  // Per-conversation capture pause — quick control without digging into Settings,
  // e.g. before pasting something sensitive into this chat.
  shadow.getElementById("mn-pause")?.addEventListener("click", () => {
    if (isCaptureEnabled()) {
      pauseCapture()
      showToast("Capture paused for this conversation")
    } else {
      resumeCapture()
      showToast("Capture resumed")
    }
    refreshPauseButton(shadow)
  })

  // Auto-insert preference (persisted) — when on, context drops into empty new
  // chats automatically so there's no click / Ctrl+V dance.
  shadow.getElementById("mn-auto")?.addEventListener("click", async () => {
    const next = !(await getAutoInsert())
    await chrome.storage.local.set({ [AUTO_INSERT_KEY]: next })
    setAutoButton(shadow, next)
    showToast(next ? "Auto-insert ON for new chats" : "Auto-insert OFF")
  })

  shadow.getElementById("mn-insert")?.addEventListener("click", async () => {
    const btn = shadow.getElementById("mn-insert")
    const outcome = await insertIntoPrompt(config, stripWrapper(result.context_string))
    if (btn) {
      btn.textContent =
        outcome === "inserted" ? "Inserted ✓" : outcome === "copied" ? "Copied — press Ctrl+V" : "Copy failed"
      setTimeout(() => (btn.textContent = "Insert into prompt"), 4000)
    }
  })

  // Switching workspace (or creating a new one): remember the choice for this
  // URL so the rest of the chat routes there, then reload context.
  shadow.getElementById("mn-ws")?.addEventListener("change", async (e) => {
    const wsId = (e.target as HTMLSelectElement).value
    if (wsId === NEW_WS_OPTION) {
      await createWorkspaceFlow(config)
      return
    }
    if (!wsId || wsId === currentWsId) return
    manualPick = true
    void chrome.runtime.sendMessage({
      type: "REMEMBER_MAPPING",
      payload: { platform: config.platformName, workspace_id: wsId, tab_url: location.href },
    })
    const next = await fetchContext(config, { workspace_id: wsId })
    if (usable(next)) render(config, next)
  })
}

/** Create a new workspace from the chat and pin this conversation to it — the
 *  explicit escape hatch when auto-routing files a turn into the wrong workspace
 *  (e.g. a tech-career game landing in a tech-career-prep workspace). */
async function createWorkspaceFlow(config: PlatformConfig): Promise<void> {
  const input = resolveEditor(config.inputSelector)
  const suggested = (input ? readInputText(input) : "").split(/\s+/).slice(0, 5).join(" ").slice(0, 40)
  const name = window.prompt("Name the new workspace (this chat will save into it):", suggested || "New Project")
  const reRender = async (wsId: string) => {
    const cur = await fetchContext(config, { workspace_id: wsId })
    if (usable(cur)) render(config, cur)
  }
  if (!name || !name.trim()) {
    void reRender(currentWsId) // cancelled — reset the dropdown selection
    return
  }
  const created = (await chrome.runtime.sendMessage({
    type: "CREATE_WORKSPACE",
    payload: { name: name.trim() },
  })) as { id?: string; name?: string } | null
  if (!created?.id) {
    showToast("Couldn't create workspace", { error: true })
    void reRender(currentWsId)
    return
  }
  manualPick = true
  void chrome.runtime.sendMessage({
    type: "REMEMBER_MAPPING",
    payload: { platform: config.platformName, workspace_id: created.id, tab_url: location.href },
  })
  showToast(`✨ New workspace: ${created.name}`, { sub: "This chat now saves here" })
  render(config, {
    workspace_id: created.id, workspace_name: created.name ?? name,
    context_string: "", nodes_included: [], token_count: 0, freshness_score: 1,
  } as CtxResult)
}

/** Fill the workspace dropdown from the engine. Falls back to a single option
 *  (the current workspace) if the list can't be fetched. */
async function populateWorkspaces(shadow: ShadowRoot, currentId: string, currentName: string): Promise<void> {
  const sel = shadow.getElementById("mn-ws") as HTMLSelectElement | null
  if (!sel) return
  const resp = (await chrome.runtime.sendMessage({ type: "LIST_WORKSPACES" })) as
    | { workspaces?: Workspace[] }
    | null
  const wss = resp?.workspaces ?? []
  sel.innerHTML = ""
  const list = wss.length ? wss : [{ id: currentId, name: currentName, icon: "" } as Partial<Workspace>]
  for (const w of list) {
    const opt = document.createElement("option")
    opt.value = w.id ?? ""
    opt.textContent = `${(w.icon ?? "").trim()} ${w.name ?? ""}`.trim()
    if (w.id === currentId) opt.selected = true
    sel.appendChild(opt)
  }
  // Explicit escape hatch: spin off a dedicated workspace for this chat.
  const newOpt = document.createElement("option")
  newOpt.value = NEW_WS_OPTION
  newOpt.textContent = "➕ New workspace…"
  sel.appendChild(newOpt)
}

function refreshPauseButton(shadow: ShadowRoot): void {
  const btn = shadow.getElementById("mn-pause")
  if (!btn) return
  const on = isCaptureEnabled()
  btn.textContent = on ? "⏸" : "▶ paused"
  btn.setAttribute("title", on ? "Pause capturing this conversation" : "Capture paused — click to resume")
  ;(btn as HTMLElement).style.color = on ? "#F0F0F5" : "#F59E0B"
}

function setAutoButton(shadow: ShadowRoot, on: boolean): void {
  const btn = shadow.getElementById("mn-auto")
  if (btn) btn.textContent = on ? "Auto: on" : "Auto: off"
}

async function initAutoButton(shadow: ShadowRoot): Promise<void> {
  setAutoButton(shadow, await getAutoInsert())
}

/** Once the user starts typing their first message, re-infer the workspace from
 *  that text (unless they've manually picked one). Re-renders only if the inferred
 *  workspace actually changed, to avoid flicker. */
function wireHintReinference(config: PlatformConfig): void {
  if (hintWired) return
  const input = resolveEditor(config.inputSelector)
  if (!input) return
  hintWired = true
  let timer: ReturnType<typeof setTimeout> | undefined
  input.addEventListener("input", () => {
    if (manualPick) return
    const text = readInputText(input)
    if (text.length < 12) return
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      if (manualPick) return
      const next = await fetchContext(config, { hint: text })
      if (usable(next) && next.workspace_id !== currentWsId) render(config, next)
    }, 900)
  })
}

type InsertOutcome = "inserted" | "copied" | "failed"

/** Resolve the *visible* editor element. ChatGPT's `#prompt-textarea` is a
 *  contenteditable ProseMirror div, but a stray hidden <textarea> can also match
 *  the selector and win document order — so prefer a contenteditable match. */
function resolveEditor(selector: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll(selector)) as HTMLElement[]
  return all.find((el) => el.isContentEditable) ?? all[0] ?? null
}

function isEditable(el: HTMLElement | null): boolean {
  return !!el && (el.isContentEditable || !!el.closest('[contenteditable="true"]'))
}

function readInputText(el: HTMLElement): string {
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) return el.value.trim()
  return (el.textContent ?? "").trim()
}

/** Best-effort insert into the chat box. Strategy by editor type:
 *  - real <textarea>/<input>: native value setter sticks and we verify it.
 *  - contenteditable (ChatGPT ProseMirror, Gemini Quill): try a synthetic paste
 *    event carrying a DataTransfer (ProseMirror reads clipboardData and usually
 *    honors it); if that doesn't land, copy to the clipboard and let the user
 *    press Ctrl+V (a real trusted paste always works). */
async function insertIntoPrompt(
  config: PlatformConfig,
  text: string,
  opts: { auto?: boolean } = {},
): Promise<InsertOutcome> {
  const block = `${text}\n\n`
  const input = resolveEditor(config.inputSelector)
  console.log(
    `[Mnemosyne] insert target: <${input?.tagName.toLowerCase() ?? "none"}> contenteditable=${isEditable(input)}`,
  )

  // Real <textarea>/<input> that is NOT contenteditable: native setter + verify.
  if ((input instanceof HTMLTextAreaElement || input instanceof HTMLInputElement) && !isEditable(input)) {
    input.focus()
    const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(proto.prototype, "value")?.set
    setter?.call(input, block + input.value)
    input.dispatchEvent(new Event("input", { bubbles: true }))
    if (input.value.includes(text.slice(0, 30))) {
      console.log("[Mnemosyne] inserted via native value setter")
      return "inserted"
    }
  }

  // contenteditable editors. Different frameworks honor different mechanisms, so
  // try the two that cover all three platforms, verifying after each.
  if (isEditable(input) && input) {
    const probe = text.slice(0, 30)
    const landed = (before: string) =>
      (input.textContent ?? "").includes(probe) && (input.textContent ?? "") !== before

    // 1) Synthetic paste with a DataTransfer — ProseMirror (ChatGPT, Claude) reads
    //    event.clipboardData and honors it.
    input.focus()
    let before = input.textContent ?? ""
    try {
      const dt = new DataTransfer()
      dt.setData("text/plain", block)
      input.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: dt }))
      await new Promise((r) => setTimeout(r, 60))
      if (landed(before)) {
        console.log("[Mnemosyne] inserted via synthetic paste event")
        return "inserted"
      }
    } catch {
      /* try the next mechanism */
    }

    // 2) execCommand insertText at the caret — Gemini's Quill (and most generic
    //    contenteditables) honor this even though they ignore synthetic paste.
    before = input.textContent ?? ""
    try {
      input.focus()
      const sel = window.getSelection()
      if (sel) {
        const range = document.createRange()
        range.selectNodeContents(input)
        range.collapse(false) // caret at the end
        sel.removeAllRanges()
        sel.addRange(range)
      }
      document.execCommand("insertText", false, block)
      input.dispatchEvent(new Event("input", { bubbles: true }))
      await new Promise((r) => setTimeout(r, 60))
      if (landed(before)) {
        console.log("[Mnemosyne] inserted via execCommand insertText")
        return "inserted"
      }
    } catch {
      /* fall through to clipboard */
    }
  }

  // Auto-insert runs without a user gesture, so a clipboard write would fail
  // silently (and we can't ask the user to Ctrl+V). Bail rather than mislead.
  if (opts.auto) return "failed"

  // Last resort: copy to the clipboard so the user can paste with Ctrl+V.
  input?.focus()
  try {
    await navigator.clipboard.writeText(text)
    console.log("[Mnemosyne] copied to clipboard (press Ctrl+V)")
    return "copied"
  } catch {
    return "failed"
  }
}

function stripWrapper(s: string): string {
  return s.replace(/^<context>\n?/, "").replace(/\n?<\/context>$/, "")
}

function escapeHtml(s: string): string {
  const d = document.createElement("div")
  d.textContent = s
  return d.innerHTML
}
