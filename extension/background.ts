// Service worker: health polling, auth token, message routing, offline buffer.

import { containsSensitiveData } from "~lib/sensitiveFilter"
import type { CapturePayload, CaptureResult } from "~lib/types"

const HOSTS = ["http://localhost:7432", "https://localhost:7432"]  // HTTP default
let base = HOSTS[0]
let engineOnline = false

async function getToken(): Promise<string> {
  const { auth_token } = await chrome.storage.local.get("auth_token")
  return auth_token ?? ""
}

async function tryPair(host: string): Promise<void> {
  if (await getToken()) return // already paired
  try {
    const r = await fetch(`${host}/pair`, { signal: AbortSignal.timeout(2000) })
    if (r.ok) {
      const { token } = await r.json()
      if (token) await chrome.storage.local.set({ auth_token: token })
    }
  } catch {
    /* pairing window may be closed; user can restart engine */
  }
}

async function pollHealth(): Promise<void> {
  for (const host of HOSTS) {
    try {
      const r = await fetch(`${host}/health`, { signal: AbortSignal.timeout(2000) })
      if (r.ok) {
        base = host
        engineOnline = true
        const data = await r.json()
        await chrome.storage.local.set({ engine_status: data })
        chrome.action.setBadgeBackgroundColor({ color: "#7C3AED" })
        await tryPair(host)
        await flushBuffer()
        void connectEvents()
        return
      }
    } catch {
      /* try next host */
    }
  }
  engineOnline = false
  await chrome.storage.local.set({ engine_status: { status: "offline" } })
  chrome.action.setBadgeBackgroundColor({ color: "#6B7280" })
}

// ---- live event stream (content scripts can't open a WS to localhost because
// the AI sites' CSP blocks it, so the background worker holds it and relays). ----
let eventsWs: WebSocket | null = null

async function connectEvents(): Promise<void> {
  if (eventsWs && (eventsWs.readyState === WebSocket.OPEN || eventsWs.readyState === WebSocket.CONNECTING)) return
  const token = await getToken()
  if (!token) return
  try {
    const ws = new WebSocket(`${base.replace(/^http/, "ws")}/ws/events?token=${encodeURIComponent(token)}`)
    eventsWs = ws
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(typeof e.data === "string" ? e.data : "{}")
        if (ev.event !== "extraction_completed") return
        const n = ev.nodes_committed || 0
        const p = ev.nodes_pending || 0
        if (n + p === 0) return
        const where = ev.workspace_name ? ` to ${ev.workspace_name}` : ""
        if (n > 0) {
          toastActiveTab(`🧠 Saved ${n} ${n === 1 ? "memory" : "memories"}${where}`, p > 0 ? `${p} more awaiting review` : undefined)
        } else {
          toastActiveTab(`📥 ${p} item${p === 1 ? "" : "s"} to review${where}`)
        }
      } catch {
        /* ignore malformed event */
      }
    }
    const drop = () => { if (eventsWs === ws) eventsWs = null }
    ws.onclose = drop
    ws.onerror = () => { try { ws.close() } catch { /* noop */ } drop() }
  } catch {
    eventsWs = null
  }
}

/** Single chokepoint deciding whether a capture is allowed. Honors the global
 *  capture toggle (storage.local, set by the popup) and incognito mode
 *  (storage.session, cleared when the browser closes — matching "this session").
 *  Returns a skip reason, or null when capture may proceed. */
async function captureGate(): Promise<string | null> {
  const { capture_enabled } = await chrome.storage.local.get("capture_enabled")
  if (capture_enabled === false) return "paused"
  try {
    const { incognito } = await chrome.storage.session.get("incognito")
    if (incognito === true) return "incognito"
  } catch {
    /* session storage unavailable — fail open (capture proceeds) */
  }
  return null
}

async function handleCapture(payload: CapturePayload): Promise<CaptureResult> {
  void connectEvents() // ensure the event stream is live for the imminent extraction result
  // Global pause / incognito — don't capture anything when either is on.
  const skip = await captureGate()
  if (skip) {
    console.log(`[Mnemosyne BG] capture skipped (${skip})`)
    return { capture_id: "", status: "skipped", reason: skip }
  }
  // Client-side defense in depth — don't even send sensitive text.
  if (containsSensitiveData(`${payload.user_message}\n${payload.ai_response}`)) {
    return { capture_id: "", status: "blocked", sensitive_data_detected: true }
  }
  // Don't gate on the in-memory engineOnline flag — it resets to false every time
  // the MV3 service worker wakes, before the health poll finishes. Just try the
  // (local) engine and buffer only on a real failure.
  try {
    const token = await getToken()
    const r = await fetch(`${base}/api/v1/capture`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(15_000),
    })
    const result = (await r.json()) as CaptureResult
    console.log("[Mnemosyne BG] capture ->", result)
    return result
  } catch (e) {
    console.warn("[Mnemosyne BG] capture failed, buffering:", String(e))
    await bufferCapture(payload)
    return { capture_id: "", status: "buffered" }
  }
}

async function handleGetContext(payload: {
  platform: string
  hint?: string
  workspace_id?: string
  tab_url?: string
}): Promise<unknown> {
  try {
    const token = await getToken()
    const q = new URLSearchParams({ platform: payload.platform, token_budget: "2000" })
    if (payload.hint) q.set("hint", payload.hint)
    if (payload.workspace_id) q.set("workspace_id", payload.workspace_id)
    if (payload.tab_url) q.set("tab_url", payload.tab_url)
    const r = await fetch(`${base}/api/v1/context?${q.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10_000),
    })
    return await r.json()
  } catch (e) {
    return { status: "offline", reason: String(e) }
  }
}

async function handleListWorkspaces(): Promise<unknown> {
  try {
    const token = await getToken()
    const r = await fetch(`${base}/api/v1/workspaces?status=active`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(8_000),
    })
    return await r.json()
  } catch (e) {
    return { status: "offline", reason: String(e), workspaces: [] }
  }
}

async function handleRememberMapping(payload: {
  platform: string
  workspace_id: string
  tab_url: string
}): Promise<unknown> {
  try {
    const token = await getToken()
    const r = await fetch(`${base}/api/v1/mappings`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(8_000),
    })
    return await r.json()
  } catch (e) {
    return { remembered: false, reason: String(e) }
  }
}

// ---- offline buffer (chrome.storage) ---- //
async function bufferCapture(payload: CapturePayload): Promise<void> {
  const { capture_buffer = [] } = await chrome.storage.local.get("capture_buffer")
  capture_buffer.push(payload)
  await chrome.storage.local.set({ capture_buffer })
}

async function flushBuffer(): Promise<void> {
  const { capture_buffer = [] } = await chrome.storage.local.get("capture_buffer")
  if (capture_buffer.length === 0) return
  const token = await getToken()
  const remaining: CapturePayload[] = []
  for (const payload of capture_buffer) {
    try {
      await fetch(`${base}/api/v1/capture`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    } catch {
      remaining.push(payload)
    }
  }
  await chrome.storage.local.set({ capture_buffer: remaining })
}

// ---- highlight-to-save (right-click a selection -> store as a note) ---- //
const SAVE_MENU_ID = "mnemosyne-save-selection"

function platformFromUrl(url: string): string {
  if (/(chatgpt\.com|chat\.openai\.com)/.test(url)) return "chatgpt"
  if (/claude\.ai/.test(url)) return "claude"
  if (/gemini\.google\.com/.test(url)) return "gemini"
  return "manual"
}

function createContextMenu(): void {
  // Recreate idempotently (removeAll first) so reloads don't throw "duplicate id".
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: SAVE_MENU_ID,
      title: "Save selection to Mnemosyne memory",
      contexts: ["selection"],
    })
  })
}

async function handleSaveNote(text: string, tabUrl: string, tabId?: number): Promise<void> {
  const notify = (message: string, sub?: string, error = false) => {
    if (tabId !== undefined) {
      chrome.tabs.sendMessage(tabId, { type: "SHOW_TOAST", message, sub, error }).catch(() => {})
    }
  }
  try {
    const token = await getToken()
    const r = await fetch(`${base}/api/v1/notes`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ text, platform: platformFromUrl(tabUrl), tab_url: tabUrl }),
      signal: AbortSignal.timeout(10_000),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    notify("🧠 Saved selection to memory")
  } catch (e) {
    console.warn("[Mnemosyne BG] save note failed:", String(e))
    notify("Couldn't save — is the engine running?", undefined, true)
  }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === SAVE_MENU_ID && info.selectionText) {
    void handleSaveNote(info.selectionText.trim(), tab?.url ?? info.pageUrl ?? "", tab?.id)
  }
})

chrome.runtime.onInstalled.addListener((details) => {
  createContextMenu()
  if (details.reason === "install") {
    chrome.tabs.create({ url: chrome.runtime.getURL("tabs/onboarding.html") })
  }
})
chrome.runtime.onStartup.addListener(createContextMenu)

// ---- keyboard shortcuts (chrome.commands) ---- //
function toastActiveTab(message: string, sub?: string): void {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const id = tabs[0]?.id
    if (id !== undefined) chrome.tabs.sendMessage(id, { type: "SHOW_TOAST", message, sub }).catch(() => {})
  })
}

async function setIncognito(next: boolean): Promise<void> {
  await chrome.storage.session.set({ incognito: next })
  await chrome.action.setBadgeText({ text: next ? "INC" : "" })
  if (next) await chrome.action.setBadgeBackgroundColor({ color: "#7C3AED" })
}

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-capture") {
    const { capture_enabled } = await chrome.storage.local.get("capture_enabled")
    const next = capture_enabled === false // was paused -> resume
    await chrome.storage.local.set({ capture_enabled: next })
    toastActiveTab(next ? "▶ Capture resumed" : "⏸ Capture paused")
  } else if (command === "toggle-incognito") {
    const { incognito } = await chrome.storage.session.get("incognito")
    const next = !(incognito === true)
    await setIncognito(next)
    toastActiveTab(next ? "🕶 Incognito ON — nothing is captured" : "Incognito off — capture resumed")
  } else if (command === "toggle-sidebar") {
    // Chrome has no programmatic "close" for the side panel; opening it from a
    // command counts as a user gesture, so this reliably opens it.
    try {
      const w = await chrome.windows.getCurrent()
      if (w.id !== undefined) await chrome.sidePanel.open({ windowId: w.id })
    } catch {
      /* side panel API unavailable */
    }
  }
  // "_execute_action" (Alt+W) is handled by Chrome itself — it opens the popup.
})

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  // Always resolve the channel — even on error — so it never "closes before a
  // response was received" (which silently drops captures under MV3).
  if (msg.type === "CAPTURE") {
    handleCapture(msg.payload)
      .then(sendResponse)
      .catch((e) => sendResponse({ capture_id: "", status: "error", reason: String(e) }))
    return true
  }
  if (msg.type === "GET_CONTEXT") {
    handleGetContext(msg.payload)
      .then(sendResponse)
      .catch((e) => sendResponse({ status: "error", reason: String(e) }))
    return true
  }
  if (msg.type === "LIST_WORKSPACES") {
    handleListWorkspaces()
      .then(sendResponse)
      .catch((e) => sendResponse({ status: "error", reason: String(e), workspaces: [] }))
    return true
  }
  if (msg.type === "REMEMBER_MAPPING") {
    handleRememberMapping(msg.payload)
      .then(sendResponse)
      .catch((e) => sendResponse({ remembered: false, reason: String(e) }))
    return true
  }
  if (msg.type === "GET_STATUS") {
    sendResponse({ online: engineOnline })
  }
  return false
})

// Health polling via chrome.alarms, NOT setInterval: MV3 kills the idle service
// worker after ~30s, which silently stops a setInterval (so the badge goes stale
// and the engine looks "offline" even after it comes back). An alarm wakes the
// worker to re-poll. Minimum period is 0.5 min.
chrome.alarms.create("health", { periodInMinutes: 0.5 })
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "health") void pollHealth()
})
// Poll immediately on worker start / browser start so status is fresh right away.
chrome.runtime.onStartup.addListener(() => void pollHealth())
void pollHealth()
