// DOM observer: detect AI response completion, extract the message pair, send
// to the background worker. Selectors are platform-specific and brittle.

import type { PlatformConfig } from "~lib/platformDetector"
import { showToast } from "~lib/toast"

let observer: MutationObserver | null = null
let captureEnabled = true
let captureGuardUntil = 0 // suppress captures until this time (skip conversation backlog)
const seenHashes = new Set<string>()  // every turn captured this session (dedup)

/** Suppress captures for a short window. Armed on observer start and on SPA
 *  navigation so that opening (or switching into) an EXISTING conversation
 *  doesn't re-capture its whole history as the page hydrates. Real new turns
 *  happen well after this window (type + AI latency >> guard). */
export function armCaptureGuard(ms = 6000): void {
  captureGuardUntil = Date.now() + ms
}

// innerText (not textContent): textContent concatenates block elements with no
// separator, gluing words across paragraphs ("Write" + "If" -> "WriteIf"), which
// poisons entity extraction. innerText respects rendered line breaks.
function readText(el: Element | null): string {
  if (!el) return ""
  return ((el as HTMLElement).innerText ?? el.textContent ?? "").trim()
}

function textOf(root: Element | null, selector: string): string {
  if (!root) return ""
  const el = root.matches(selector) ? root : root.querySelector(selector)
  return readText(el)
}

function simpleHash(s: string): string {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  return String(h)
}

/** Collapse an accidentally-doubled capture ("X" + optional sep + "X" -> "X").
 *  Guards against DOM quirks that yield the same text twice back-to-back. */
function collapseDoubled(raw: string): string {
  const t = raw.trim().replace(/\s+/g, " ")
  const n = t.length
  for (const gap of [0, 1]) {
    const a = (n - gap) / 2
    if (Number.isInteger(a) && a > 15 && t.slice(0, a).trim() === t.slice(a + gap).trim()) {
      return t.slice(0, a).trim()
    }
  }
  return t
}

async function waitForStreamingComplete(el: Element): Promise<void> {
  let last = 0
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 500))
    const len = el.textContent?.length ?? 0
    if (len > 0 && len === last) return
    last = len
  }
}

function findPrecedingUser(responseEl: Element, config: PlatformConfig): Element | null {
  // Walk previous siblings / ancestors for the most recent user message.
  const all = Array.from(document.querySelectorAll(config.userTextSelector))
  let best: Element | null = null
  for (const u of all) {
    if (responseEl.compareDocumentPosition(u) & Node.DOCUMENT_POSITION_PRECEDING) best = u
  }
  return best
}

async function onNewResponse(responseEl: Element, config: PlatformConfig): Promise<void> {
  if (!captureEnabled) return
  // Skip the burst of historical messages that render while an existing chat
  // hydrates — otherwise opening an old conversation re-captures every turn.
  if (Date.now() < captureGuardUntil) {
    console.log("[Mnemosyne] startup guard — skipping (conversation backlog)")
    return
  }
  await waitForStreamingComplete(responseEl)
  const aiText = collapseDoubled(textOf(responseEl, config.aiTextSelector) || readText(responseEl))
  const userEl = findPrecedingUser(responseEl, config)
  const userText = collapseDoubled(readText(userEl))
  if (!userText || !aiText) {
    console.log(`[Mnemosyne] skipped capture — userText=${userText.length} aiText=${aiText.length} chars`)
    return
  }

  // Dedup against every turn seen this session — ChatGPT re-mounts message nodes
  // while streaming, so the same turn can be detected multiple times.
  const hash = simpleHash(userText + aiText)
  if (seenHashes.has(hash)) return
  seenHashes.add(hash)

  console.log(`[Mnemosyne] capturing turn (user=${userText.length}, ai=${aiText.length} chars)`)
  chrome.runtime.sendMessage(
    {
      type: "CAPTURE",
      payload: {
        session_id: location.pathname,
        platform: config.platformName,
        user_message: userText,
        ai_response: aiText,
        timestamp: new Date().toISOString(),
        tab_url: location.href,
      },
    },
    (resp) => {
      console.log("[Mnemosyne] capture result:", resp)
      // The message channel can fail if the extension was reloaded/updated while
      // this page kept the old content script ("context invalidated").
      if (chrome.runtime.lastError) {
        showToast("Mnemosyne disconnected — reload this tab", { error: true })
        return
      }
      // Visible confirmation for EVERY outcome — silence (no toast) erodes trust
      // and hid the common "why didn't it save?" cases (incognito / paused).
      const r = resp as { status?: string; reason?: string; workspace_created?: boolean; workspace_name?: string } | undefined
      const status = r?.status
      if (status === "queued" || status === "processing") {
        if (r?.workspace_created) {
          showToast(`🧠 New workspace: ${r.workspace_name ?? "Untitled"}`, { sub: "New topic detected — capturing here" })
        } else {
          // Honest wording: the turn is queued; extraction (which may yield 0, 1,
          // or several memories) runs in the background a moment later.
          showToast("🧠 Captured — extracting memories…")
        }
      } else if (status === "blocked") {
        showToast("Mnemosyne: skipped (sensitive data detected)", { sub: "Not stored" })
      } else if (status === "buffered" || status === "offline") {
        showToast("Mnemosyne engine offline — buffered locally", { error: true, sub: "Will sync when the app is running" })
      } else if (status === "skipped" && r?.reason === "incognito") {
        showToast("🕶 Incognito on — this turn was not saved", { sub: "Toggle it off in the toolbar to resume" })
      } else if (status === "skipped" && r?.reason === "paused") {
        showToast("⏸ Capture paused — this turn was not saved", { sub: "Resume in the toolbar (or Alt+P)" })
      } else if (status === "skipped") {
        showToast("Mnemosyne: capture skipped", { sub: r?.reason })
      } else if (status === "error") {
        showToast("Mnemosyne: couldn't save (engine error)", { error: true, sub: r?.reason })
      } else {
        showToast("Mnemosyne: no response from engine", { error: true })
      }
    },
  )
}

export function startObserver(config: PlatformConfig): void {
  // Observe document.body (not the chat container): these are single-page apps
  // that swap out the chat container on navigation, which would orphan a
  // container-scoped observer. Body survives client-side route changes.
  if (observer) return // already running — survives SPA navigation
  armCaptureGuard() // ignore the initial conversation backlog on first load
  const matched = !!document.querySelector(config.chatContainerSelector)
  console.log(`[Mnemosyne] observer started on ${config.platformName}; chat container ${matched ? "found" : "not found yet"}, observing document.body`)
  observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of Array.from(m.addedNodes)) {
        if (node instanceof HTMLElement) {
          const target = node.matches(config.aiResponseSelector)
            ? node
            : node.querySelector(config.aiResponseSelector)
          if (target) {
            console.log("[Mnemosyne] AI response element detected")
            void onNewResponse(target, config)
          }
        }
      }
    }
  })
  observer.observe(document.body, { childList: true, subtree: true })
}

export function pauseCapture(): void {
  captureEnabled = false
}
export function resumeCapture(): void {
  captureEnabled = true
}
export function isCaptureEnabled(): boolean {
  return captureEnabled
}
export function stopObserver(): void {
  observer?.disconnect()
  observer = null
}
