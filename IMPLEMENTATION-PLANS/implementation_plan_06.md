# Plan 06 — Chrome Extension Core

> Covers: Doc 03 (Architecture), Doc 09 (Frontend), Doc 11 (Tech Stack), Doc 13 (Extension Security)

---

## 1. PROJECT SETUP

### package.json
```json
{
  "name": "mnemosyne-extension",
  "version": "1.0.0",
  "scripts": {
    "dev": "plasmo dev",
    "build": "plasmo build",
    "build:chrome": "plasmo build --target=chrome-mv3",
    "test": "vitest run"
  },
  "dependencies": {
    "plasmo": "^0.88.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "cytoscape": "^3.29.0",
    "@anthropic-ai/sdk": "latest"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/react": "^18.3.0",
    "tailwindcss": "^3.4.0",
    "vitest": "^1.0.0"
  }
}
```

### tailwind.config.js
```js
module.exports = {
  prefix: 'mn-',  // Prevent collision with host page CSS
  content: ['./src/**/*.{tsx,ts}'],
  theme: {
    extend: {
      colors: {
        accent: '#7C3AED',
        'accent-hover': '#6D28D9',
        surface: '#1E1E2E',
        'surface-hover': '#2A2A3E',
        'surface-border': '#3A3A4E',
        'text-primary': '#E4E4E7',
        'text-secondary': '#A1A1AA',
        success: '#10B981',  // Tailwind emerald-500 — matches Doc 09 §2.1 design token --color-success
        warning: '#F59E0B',
        danger: '#EF4444',
        info: '#3B82F6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      }
    }
  }
}
```

### Manifest permissions (via Plasmo config)
```typescript
// plasmo.config.ts
export default {
  manifest: {
    permissions: ["storage", "activeTab", "scripting"],
    host_permissions: [
      "https://claude.ai/*",
      "https://chat.openai.com/*",
      "https://chatgpt.com/*",
      "https://gemini.google.com/*",
      "https://localhost:7432/*"
    ]
  }
}
```

---

## 2. BACKGROUND SERVICE WORKER (background.ts)

```typescript
import { Storage } from "@plasmohq/storage"

const storage = new Storage()
const HEALTH_POLL_INTERVAL = 30_000  // 30 seconds
const ENGINE_URL = "https://localhost:7432"

// State
let engineOnline = false
let authToken: string | null = null

// ── Lifecycle ──

chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === "install") {
    // First install → open onboarding
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding/index.html") })
    await storage.set("first_run", true)
  }
})

// ── Health Polling ──

async function pollHealth() {
  try {
    const token = await getToken()
    const resp = await fetch(`${ENGINE_URL}/health`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
    const data = await resp.json()
    engineOnline = data.status === "healthy"
    await storage.set("engine_status", data)

    // Update badge
    chrome.action.setBadgeBackgroundColor({ color: engineOnline ? "#7C3AED" : "#6B7280" })
  } catch {
    engineOnline = false
    await storage.set("engine_status", { status: "offline" })
    chrome.action.setBadgeBackgroundColor({ color: "#6B7280" })
  }
}

setInterval(pollHealth, HEALTH_POLL_INTERVAL)
pollHealth()  // Initial check

// ── Auth Token Management ──

async function getToken(): Promise<string> {
  if (authToken) return authToken
  authToken = await storage.get("auth_token")
  if (!authToken) {
    // Try to read from engine config (first-run handshake)
    // Extension will prompt user to paste token from engine setup
  }
  return authToken!
}

// ── Message Handling (content script ↔ background) ──

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CAPTURE") {
    handleCapture(msg.payload).then(sendResponse)
    return true  // Async response
  }
  if (msg.type === "GET_CONTEXT") {
    handleGetContext(msg.payload).then(sendResponse)
    return true
  }
  if (msg.type === "GET_STATUS") {
    sendResponse({ online: engineOnline })
  }
  if (msg.type === "RESTART_ENGINE") {
    handleRestartEngine().then(sendResponse)
    return true  // Async response
  }
})

async function handleCapture(payload: CapturePayload) {
  if (!engineOnline) {
    // Buffer to IndexedDB for later replay
    await bufferCapture(payload)
    return { status: "buffered" }
  }
  const token = await getToken()
  const resp = await fetch(`${ENGINE_URL}/api/v1/capture`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  })
  return await resp.json()
}

async function handleGetContext(payload: ContextPayload) {
  if (!engineOnline) return { status: "offline" }
  const token = await getToken()
  const params = new URLSearchParams({
    ...(payload.workspace_id && { workspace_id: payload.workspace_id }),
    ...(payload.hint && { hint: payload.hint }),
    platform: payload.platform,
    token_budget: String(payload.token_budget || 2000),
  })
  const resp = await fetch(`${ENGINE_URL}/api/v1/context?${params}`, {
    headers: { "Authorization": `Bearer ${token}` }
  })
  return await resp.json()
}

// ── Offline Buffer ──

async function bufferCapture(payload: CapturePayload) {
  const buffer = await storage.get<CapturePayload[]>("capture_buffer") || []
  buffer.push(payload)
  await storage.set("capture_buffer", buffer)
}

async function replayBuffer() {
  const buffer = await storage.get<CapturePayload[]>("capture_buffer") || []
  if (buffer.length === 0) return
  for (const payload of buffer) {
    await handleCapture(payload)
  }
  await storage.set("capture_buffer", [])
}

// ── Engine Restart (Gap fix — Doc 12 UC-18) ──

/**
 * Trigger engine restart via native messaging host or health-based retry.
 * The extension can't directly execute OS commands, so we use two strategies:
 * 1. POST to /api/v1/admin/restart if engine is responsive (graceful)
 * 2. Native messaging host (mnemosyne_native_host) for hard restart when offline
 */
async function handleRestartEngine(): Promise<{ status: string }> {
  try {
    // Strategy 1: Graceful restart via API (if engine is still responsive)
    const token = await getToken()
    const resp = await fetch(`${ENGINE_URL}/api/v1/admin/restart`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` }
    })
    if (resp.ok) {
      // Wait for engine to come back
      await waitForEngineRestart()
      return { status: "restarted" }
    }
  } catch {
    // Engine not responding — try native messaging
  }

  try {
    // Strategy 2: Native messaging host (installed alongside engine)
    const response = await chrome.runtime.sendNativeMessage(
      "com.mnemosyne.native_host",
      { action: "restart_engine" }
    )
    if (response?.success) {
      await waitForEngineRestart()
      return { status: "restarted" }
    }
  } catch (e) {
    console.error("Native messaging restart failed:", e)
  }

  return { status: "failed" }
}

async function waitForEngineRestart(maxWaitMs = 15000) {
  const start = Date.now()
  while (Date.now() - start < maxWaitMs) {
    await new Promise(r => setTimeout(r, 1000))
    try {
      const resp = await fetch(`${ENGINE_URL}/health`, { signal: AbortSignal.timeout(2000) })
      if (resp.ok) { await pollHealth(); return }
    } catch { /* keep waiting */ }
  }
}
```

---

## 3. DOM OBSERVER (content/observer.ts)

```typescript
import { detectPlatform, type PlatformConfig } from "../utils/platformDetector"

let observer: MutationObserver | null = null
let captureEnabled = true
let lastCapturedText = ""

export function startObserver() {
  const platform = detectPlatform(window.location.href)
  if (!platform) return  // Not an AI platform

  const config = getPlatformConfig(platform)

  observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node instanceof HTMLElement) {
          if (isAIResponse(node, config)) {
            onNewResponse(node, config)
          }
        }
      }
    }
  })

  // Observe the chat container
  const container = document.querySelector(config.chatContainerSelector)
  if (container) {
    observer.observe(container, { childList: true, subtree: true })
  }
}

function isAIResponse(el: HTMLElement, config: PlatformConfig): boolean {
  return el.matches(config.aiResponseSelector) ||
         !!el.querySelector(config.aiResponseSelector)
}

async function onNewResponse(responseEl: HTMLElement, config: PlatformConfig) {
  if (!captureEnabled) return

  // Wait for response to finish streaming
  await waitForStreamingComplete(responseEl, config)

  // Extract the message pair
  const aiText = extractText(responseEl, config.aiTextSelector)
  const userEl = findPrecedingUserMessage(responseEl, config)
  const userText = userEl ? extractText(userEl, config.userTextSelector) : ""

  if (!userText || !aiText) return

  // Dedup: don't capture same text twice
  const hash = simpleHash(userText + aiText)
  if (hash === lastCapturedText) return
  lastCapturedText = hash

  // Send to background
  chrome.runtime.sendMessage({
    type: "CAPTURE",
    payload: {
      session_id: getSessionId(),
      platform: config.platformName,
      user_message: userText,
      ai_response: aiText,
      timestamp: new Date().toISOString(),
      tab_url: window.location.href,
    }
  })
}

async function waitForStreamingComplete(el: HTMLElement, config: PlatformConfig) {
  // Poll until streaming indicator disappears or content stabilizes
  let lastLength = 0
  for (let i = 0; i < 60; i++) {  // Max 30 seconds
    await new Promise(r => setTimeout(r, 500))
    const currentLength = el.textContent?.length || 0
    if (currentLength === lastLength && currentLength > 0) break
    lastLength = currentLength
  }
}

export function pauseCapture() { captureEnabled = false }
export function resumeCapture() { captureEnabled = true }
export function stopObserver() { observer?.disconnect() }
```

---

## 4. PLATFORM HOOKS (content/platforms/)

### claude.ts
```typescript
import type { PlatformConfig } from "../../utils/platformDetector"

export const claudeConfig: PlatformConfig = {
  platformName: "claude",
  urlPattern: /claude\.ai/,
  chatContainerSelector: '[class*="conversation-turn"],.mx-auto',
  aiResponseSelector: '[data-testid="ai-message"],.font-claude-message',
  aiTextSelector: '.prose, .markdown',
  userTextSelector: '.whitespace-pre-wrap, [data-testid="user-message"]',
  userMessageSelector: '[data-testid="user-message"]',
  inputSelector: '[contenteditable="true"], textarea',
  streamingIndicator: '.result-streaming, [class*="streaming"]',
  injectionTarget: '.sticky, [class*="header"]',  // Where to inject indicator
}
```

### chatgpt.ts
```typescript
export const chatgptConfig: PlatformConfig = {
  platformName: "chatgpt",
  urlPattern: /chat\.openai\.com|chatgpt\.com/,
  chatContainerSelector: '[class*="react-scroll-to-bottom"]',
  aiResponseSelector: '[data-message-author-role="assistant"]',
  aiTextSelector: '.markdown, .prose',
  userTextSelector: '[data-message-author-role="user"] .whitespace-pre-wrap',
  userMessageSelector: '[data-message-author-role="user"]',
  inputSelector: '#prompt-textarea, textarea',
  streamingIndicator: '.result-streaming',
  injectionTarget: 'main header, [class*="sticky"]',
}
```

### gemini.ts
```typescript
export const geminiConfig: PlatformConfig = {
  platformName: "gemini",
  urlPattern: /gemini\.google\.com/,
  chatContainerSelector: '.conversation-container',
  aiResponseSelector: '.model-response-text, [class*="response"]',
  aiTextSelector: '.markdown-main-panel',
  userTextSelector: '.query-text',
  userMessageSelector: '.query-content',
  inputSelector: '.ql-editor, textarea',
  streamingIndicator: '.loading-indicator',
  injectionTarget: 'header',
}
```

---

## 5. CONTEXT INJECTOR (content/injector.ts)

```typescript
import { detectPlatform, getPlatformConfig } from "../utils/platformDetector"

export async function injectContext() {
  const platform = detectPlatform(window.location.href)
  if (!platform) return

  const config = getPlatformConfig(platform)

  // Request context from background → engine
  const result = await chrome.runtime.sendMessage({
    type: "GET_CONTEXT",
    payload: {
      platform: config.platformName,
      hint: getFirstUserMessage(config),
      token_budget: 2000,
    }
  })

  if (!result || result.status === "offline" || !result.context_string) return

  // Inject into the AI platform's input
  injectIntoInput(result.context_string, config)

  // Show injection indicator
  showInjectionIndicator(result, config)
}

function injectIntoInput(context: string, config: PlatformConfig) {
  // For Claude: prepend as hidden system context in the first message
  // This is done by modifying the textarea/contenteditable before submit
  // The context is invisible to the user in the input but sent with the message
}

function showInjectionIndicator(result: ContextResult, config: PlatformConfig) {
  // Create floating indicator element
  const indicator = document.createElement('div')
  indicator.id = 'mnemosyne-injection-indicator'
  indicator.setAttribute('data-testid', 'mnemosyne-injection-indicator')
  indicator.innerHTML = `
    <div class="mn-indicator">
      <span class="mn-icon">🧠</span>
      <span class="mn-label">Mnemosyne — ${result.workspace_name}</span>
      <span class="mn-meta">${result.nodes_included.length} items · ${result.token_count} tokens</span>
      <button class="mn-expand" id="mn-toggle-expand">▼ Show</button>
      <button class="mn-close" id="mn-close-indicator">✕</button>
    </div>
    <div class="mn-expanded" id="mn-expanded-view" style="display:none">
      ${buildExpandedView(result)}
    </div>
  `

  // Inject with Shadow DOM to isolate styles
  const host = document.createElement('div')
  host.id = 'mnemosyne-host'
  const shadow = host.attachShadow({ mode: 'closed' })
  shadow.appendChild(getInjectionStyles())
  shadow.appendChild(indicator)

  // Insert at top of chat area
  const target = document.querySelector(config.injectionTarget)
  if (target) {
    target.parentElement?.insertBefore(host, target.nextSibling)
  }

  // Event listeners
  shadow.getElementById('mn-toggle-expand')?.addEventListener('click', () => {
    const expanded = shadow.getElementById('mn-expanded-view')!
    expanded.style.display = expanded.style.display === 'none' ? 'block' : 'none'
  })
  shadow.getElementById('mn-close-indicator')?.addEventListener('click', () => {
    host.remove()
  })
}

function buildExpandedView(result: ContextResult): string {
  // Group nodes by type and render as sections
  const groups: Record<string, string[]> = {}
  for (const node of result.nodes_included) {
    const type = node.node_type
    if (!groups[type]) groups[type] = []
    groups[type].push(node.content)
  }
  let html = ''
  const labels: Record<string, string> = {
    goal: 'Goals', decision: 'Recent Decisions',
    technical_fact: 'Technical State', problem: 'Open Problems',
    preference: 'Preferences', entity: 'Key People & Tools',
  }
  for (const [type, items] of Object.entries(groups)) {
    html += `<div class="mn-section"><h4>${labels[type] || type}</h4><ul>`
    for (const item of items) html += `<li>${item}</li>`
    html += `</ul></div>`
  }
  return html
}
```

---

## 6. ZUSTAND STORE (stores/mnemosyneStore.ts)

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface MnemosyneState {
  // Engine status
  engineOnline: boolean
  engineVersion: string | null

  // Active workspace
  activeWorkspace: Workspace | null
  workspaces: Workspace[]

  // Capture state
  captureEnabled: boolean
  captureCount: number

  // UI state
  sidebarOpen: boolean
  activeTab: 'memory' | 'graph' | 'audit' | 'search'
  pendingReviewCount: number

  // Actions
  setEngineStatus: (online: boolean, version?: string) => void
  setActiveWorkspace: (ws: Workspace | null) => void
  setWorkspaces: (ws: Workspace[]) => void
  toggleCapture: () => void
  toggleSidebar: () => void
  setActiveTab: (tab: string) => void
  setPendingCount: (count: number) => void
  incrementCapture: () => void
}

export const useMnemosyneStore = create<MnemosyneState>()(
  persist(
    (set) => ({
      engineOnline: false, engineVersion: null,
      activeWorkspace: null, workspaces: [],
      captureEnabled: true, captureCount: 0,
      sidebarOpen: false, activeTab: 'memory',
      pendingReviewCount: 0,

      setEngineStatus: (online, version) =>
        set({ engineOnline: online, engineVersion: version || null }),
      setActiveWorkspace: (ws) => set({ activeWorkspace: ws }),
      setWorkspaces: (ws) => set({ workspaces: ws }),
      toggleCapture: () => set((s) => ({ captureEnabled: !s.captureEnabled })),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setActiveTab: (tab) => set({ activeTab: tab as any }),
      setPendingCount: (count) => set({ pendingReviewCount: count }),
      incrementCapture: () => set((s) => ({ captureCount: s.captureCount + 1 })),
    }),
    { name: 'mnemosyne-store' }
  )
)
```

---

## 7. UTILITIES

### utils/platformDetector.ts
```typescript
export interface PlatformConfig {
  platformName: string
  urlPattern: RegExp
  chatContainerSelector: string
  aiResponseSelector: string
  aiTextSelector: string
  userTextSelector: string
  userMessageSelector: string
  inputSelector: string
  streamingIndicator: string
  injectionTarget: string
}

const platforms = [claudeConfig, chatgptConfig, geminiConfig]

export function detectPlatform(url: string): PlatformConfig | null {
  return platforms.find(p => p.urlPattern.test(url)) || null
}
```

### utils/sensitiveFilter.ts
```typescript
// Client-side pre-filter (mirrors backend, Doc 13)
const PATTERNS = [
  /sk-[A-Za-z0-9]{20,}/,
  /AKIA[A-Z0-9]{16}/,
  /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/,
  /\b\d{3}-\d{2}-\d{4}\b/,
  // ... same patterns as backend
]

export function containsSensitiveData(text: string): boolean {
  return PATTERNS.some(p => p.test(text))
}
```

### api/client.ts
```typescript
// Typed API client wrapping fetch with auth
export class MnemosyneAPI {
  async capture(payload: CapturePayload): Promise<CaptureResult>
  async getContext(params: ContextParams): Promise<ContextResult>
  async getWorkspaces(): Promise<Workspace[]>
  async getNodes(wsId: string, params?: NodeFilters): Promise<MemoryNode[]>
  async getPending(wsId: string): Promise<PendingReview[]>
  async approvePending(id: string, edited?: string): Promise<void>
  async rejectPending(id: string): Promise<void>
  async getHealth(): Promise<HealthResponse>
  // ... all other endpoints
}
```

---

## Files Summary

| File | Purpose |
|------|---------|
| `extension/package.json` | Dependencies |
| `extension/tsconfig.json` | Strict TypeScript |
| `extension/plasmo.config.ts` | Manifest V3 permissions |
| `extension/tailwind.config.js` | mn- prefix, design tokens |
| `extension/background.ts` | Service worker, health, auth, messaging |
| `extension/content/observer.ts` | DOM MutationObserver |
| `extension/content/injector.ts` | Context injection + indicator |
| `extension/content/platforms/claude.ts` | Claude.ai selectors |
| `extension/content/platforms/chatgpt.ts` | ChatGPT selectors |
| `extension/content/platforms/gemini.ts` | Gemini selectors |
| `extension/stores/mnemosyneStore.ts` | Zustand state |
| `extension/api/client.ts` | Typed API client |
| `extension/utils/platformDetector.ts` | Platform detection |
| `extension/utils/sensitiveFilter.ts` | Client-side PII filter |
| `extension/native_host/com.mnemosyne.native_host.json` | Native messaging host manifest |

**Total: ~16 files.**

---

> **Next: Plan 07 — Extension UI: Sidebar & Popup**
