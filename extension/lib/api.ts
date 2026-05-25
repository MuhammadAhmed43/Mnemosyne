// Typed client for the local engine (Doc 08). All calls go to localhost with a
// bearer token. We try https first (self-signed) and fall back to http, since
// the engine degrades TLS on platforms where the cert can't be trusted.

import type {
  CapturePayload,
  CaptureResult,
  Conflict,
  ContextResult,
  HealthResponse,
  MemoryNode,
  PendingItem,
  UserSettings,
  Workspace,
} from "~lib/types"

const HOSTS = ["http://localhost:7432", "https://localhost:7432"]  // HTTP default

export class MnemosyneAPI {
  private base = HOSTS[0] // default http; updated by health probe
  constructor(private token: string) {}

  setToken(token: string) {
    this.token = token
  }

  /** WebSocket URL for the live event stream (token in query — browsers can't set
   *  WS auth headers). Derives ws(s):// from the probed http(s) base. */
  eventsUrl(): string {
    return `${this.base.replace(/^http/, "ws")}/ws/events?token=${encodeURIComponent(this.token)}`
  }

  private headers(): HeadersInit {
    return { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" }
  }

  async probe(): Promise<HealthResponse | null> {
    for (const host of HOSTS) {
      try {
        const r = await fetch(`${host}/health`, { signal: AbortSignal.timeout(2000) })
        if (r.ok) {
          this.base = host
          return (await r.json()) as HealthResponse
        }
      } catch {
        /* try next */
      }
    }
    return null
  }

  private async req<T>(method: string, path: string, body?: unknown): Promise<T> {
    const r = await fetch(`${this.base}${path}`, {
      method,
      headers: this.headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`)
    return (await r.json()) as T
  }

  capture(payload: CapturePayload): Promise<CaptureResult> {
    return this.req("POST", "/api/v1/capture", payload)
  }

  getContext(params: { workspace_id?: string; hint?: string; platform: string; token_budget?: number }): Promise<ContextResult> {
    const q = new URLSearchParams()
    if (params.workspace_id) q.set("workspace_id", params.workspace_id)
    if (params.hint) q.set("hint", params.hint)
    q.set("platform", params.platform)
    q.set("token_budget", String(params.token_budget ?? 2000))
    return this.req("GET", `/api/v1/context?${q.toString()}`)
  }

  listWorkspaces(): Promise<{ workspaces: Workspace[]; total: number }> {
    return this.req("GET", "/api/v1/workspaces")
  }

  createWorkspace(body: { name: string; description?: string; tags?: string[] }): Promise<Workspace> {
    return this.req("POST", "/api/v1/workspaces", body)
  }

  listNodes(ws: string, params?: { type?: string; status?: string; search?: string; limit?: number }): Promise<{ nodes: MemoryNode[]; total: number }> {
    const q = new URLSearchParams()
    // Only set defined, non-empty values — otherwise URLSearchParams turns
    // `undefined` into the literal string "undefined" (which the backend then
    // treats as a real search term, returning nothing).
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== undefined && v !== null && v !== "") q.set(k, String(v))
    }
    return this.req("GET", `/api/v1/workspaces/${ws}/nodes?${q.toString()}`)
  }

  nodeCounts(ws: string, search?: string): Promise<{ counts: Record<string, number>; total: number }> {
    const q = search ? `?search=${encodeURIComponent(search)}` : ""
    return this.req("GET", `/api/v1/workspaces/${ws}/node-counts${q}`)
  }

  getPending(ws: string): Promise<{ items: PendingItem[]; total: number }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/pending`)
  }

  approvePending(ws: string, id: string, edits?: Record<string, unknown>): Promise<unknown> {
    return this.req("POST", `/api/v1/workspaces/${ws}/pending/${id}/approve`, edits ?? {})
  }

  rejectPending(ws: string, id: string, reason = "inaccurate"): Promise<unknown> {
    return this.req("POST", `/api/v1/workspaces/${ws}/pending/${id}/reject`, { reason })
  }

  rejectAllPending(ws: string): Promise<{ rejected: number }> {
    return this.req("POST", `/api/v1/workspaces/${ws}/pending/reject-all`, {})
  }

  getNode(ws: string, id: string): Promise<{ node: MemoryNode }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/nodes/${id}`)
  }

  getGraph(ws: string): Promise<{ nodes: unknown[]; edges: unknown[] }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/graph`)
  }

  getSettings(): Promise<UserSettings> {
    return this.req("GET", "/api/v1/settings")
  }

  updateSettings(s: UserSettings): Promise<UserSettings> {
    return this.req("PUT", "/api/v1/settings", s)
  }

  getConflicts(ws: string, status?: string): Promise<{ conflicts: Conflict[]; total: number }> {
    const q = status ? `?status=${status}` : ""
    return this.req("GET", `/api/v1/workspaces/${ws}/conflicts${q}`)
  }

  resolveConflict(ws: string, id: string, body: { strategy: string; merged_content?: string; reason?: string }): Promise<unknown> {
    return this.req("POST", `/api/v1/workspaces/${ws}/conflicts/${id}/resolve`, body)
  }

  getHealth(ws: string): Promise<{ memory_health_score: number }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/health`)
  }

  boostNode(ws: string, id: string, amount: number): Promise<unknown> {
    return this.req("POST", `/api/v1/workspaces/${ws}/nodes/${id}/boost`, { boost_amount: amount })
  }

  updateNode(ws: string, id: string, body: Record<string, unknown>): Promise<unknown> {
    return this.req("PUT", `/api/v1/workspaces/${ws}/nodes/${id}`, body)
  }

  deleteNode(ws: string, id: string, hard = false): Promise<unknown> {
    return this.req("DELETE", `/api/v1/workspaces/${ws}/nodes/${id}?hard=${hard}`)
  }

  createNode(ws: string, body: { node_type: string; content: string; structured_data?: Record<string, unknown> }): Promise<MemoryNode> {
    return this.req("POST", `/api/v1/workspaces/${ws}/nodes/manual`, body)
  }

  exportWorkspace(ws: string): Promise<Record<string, unknown>> {
    return this.req("GET", `/api/v1/workspaces/${ws}/export`)
  }

  importWorkspace(data: unknown): Promise<unknown> {
    return this.req("POST", `/api/v1/workspaces/import`, data)
  }

  getThreads(ws: string): Promise<{ threads: ThreadSummary[] }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/threads`)
  }

  getThreadNodes(ws: string, id: string): Promise<{ nodes: ThreadNode[] }> {
    return this.req("GET", `/api/v1/workspaces/${ws}/threads/${id}`)
  }

  nlQuery(ws: string, question: string): Promise<{ results: MemoryNode[]; total: number }> {
    return this.req("POST", `/api/v1/workspaces/${ws}/query`, { question })
  }
}

export interface ThreadSummary {
  id: string
  session_id: string
  platform: string
  turn_count: number
  started_at: string
}

export interface ThreadNode {
  node_id: string
  turn_index: number
  content: string
  node_type: string
}
