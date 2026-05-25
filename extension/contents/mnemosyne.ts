// Plasmo content script — runs on the AI platforms. Wires the DOM observer
// (capture) and the context indicator (injection) for the detected platform.
//
// These sites are single-page apps: starting a "New chat" or opening a past
// conversation changes the URL via history.pushState WITHOUT a full page load,
// so the content script never re-runs on its own. We watch for client-side
// navigation and re-trigger the context bar each time, otherwise the bar would
// only ever appear on the first hard page load.

import type { PlasmoCSConfig } from "plasmo"

import { injectContext, resetInjector } from "~lib/injector"
import { startObserver } from "~lib/observer"
import { detectPlatform } from "~lib/platformDetector"
import { showToast } from "~lib/toast"

export const config: PlasmoCSConfig = {
  matches: [
    "https://claude.ai/*",
    "https://chat.openai.com/*",
    "https://chatgpt.com/*",
    "https://gemini.google.com/*",
  ],
  run_at: "document_idle",
}

// Let the background worker surface in-page toasts (e.g. "Saved selection").
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "SHOW_TOAST") {
    showToast(msg.message, { sub: msg.sub, error: msg.error })
  }
})

const platform = detectPlatform(location.href)
console.log("[Mnemosyne] content script loaded; platform =", platform?.platformName ?? "NONE (url not matched)")

if (platform) {
  try {
    startObserver(platform)
    setTimeout(() => void injectContext(platform), 1500)
    watchNavigation()
  } catch (e) {
    console.error("[Mnemosyne] content script error:", e)
  }
}

/** Fire `onNavigate` whenever the SPA changes URL (pushState/replaceState/back-
 *  forward). Debounced so a burst of route updates triggers one re-inject. */
function watchNavigation(): void {
  let lastUrl = location.href
  let timer: ReturnType<typeof setTimeout> | undefined

  const onNavigate = (): void => {
    if (location.href === lastUrl) return
    lastUrl = location.href
    if (timer) clearTimeout(timer)
    // NOTE: we intentionally do NOT re-arm the capture guard here. Sending the
    // first message of a new chat triggers a pushState navigation, so arming the
    // guard would suppress that real turn. The initial-load guard still skips the
    // backlog on first page load; switching into an existing chat may re-capture,
    // but commit-time dedup collapses those, so it's harmless.
    timer = setTimeout(() => {
      console.log("[Mnemosyne] SPA navigation ->", location.pathname, "; re-injecting context")
      resetInjector()
      if (platform) void injectContext(platform)
    }, 1200) // let the new conversation's DOM settle first
  }

  // Patch the history API so we hear about programmatic navigation.
  for (const method of ["pushState", "replaceState"] as const) {
    const orig = history[method]
    history[method] = function (this: History, ...args: Parameters<History["pushState"]>) {
      const ret = orig.apply(this, args)
      onNavigate()
      return ret
    }
  }
  window.addEventListener("popstate", onNavigate)
  // Fallback: some routers mutate the URL without the history API.
  setInterval(onNavigate, 1500)
}
