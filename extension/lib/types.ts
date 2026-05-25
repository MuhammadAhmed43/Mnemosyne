// Shared types mirroring the backend API contracts (Doc 08).

export type Platform = "claude" | "chatgpt" | "gemini" | "manual"

export interface Workspace {
  id: string
  name: string
  description: string
  color: string
  icon: string
  status: "active" | "archived" | "paused" | "deleted"
  capture_enabled: boolean
  tags: string[]
  node_count: number
  memory_health_score: number
  last_active: string
}

export interface CapturePayload {
  session_id: string
  platform: Platform
  user_message: string
  ai_response: string
  timestamp: string
  tab_url: string
  workspace_id?: string
}

export interface CaptureResult {
  capture_id: string
  status: "queued" | "blocked" | "skipped" | "buffered" | "offline"
  workspace_id?: string
  sensitive_data_detected?: boolean
  reason?: string
  workspace_created?: boolean
  workspace_name?: string
}

export interface ContextNode {
  node_id: string
  node_type: string
  content: string
  relevance_score: number
  source: string
}

export interface ContextResult {
  workspace_id: string
  workspace_name: string
  context_string: string
  nodes_included: ContextNode[]
  token_count: number
  freshness_score: number
}

export interface HealthResponse {
  status: string
  version: string
  vector_store_ok: boolean
  ollama_available: boolean
  queue_depth: number
  workspace_count: number
}

export interface MemoryNode {
  id: string
  node_type: string
  content: string
  structured_data: Record<string, unknown>
  importance_score: number
  extraction_confidence: number
  user_verified: boolean
  is_permanent: boolean
  version: number
  status: string
  created_at: string
}

export interface PendingItem {
  id: string
  candidate_type: string
  candidate_content: string
  candidate_confidence: number
  source_platform: string
  source_context?: string
}

export interface UserSettings {
  capture_enabled: boolean
  token_budget: number
  auto_commit_threshold: number
  min_confidence: number
  decay_enabled: boolean
  sensitive_data_filter: boolean
  llm_extraction_enabled: boolean
  cloud_fallback_enabled: boolean
  custom_blocked_terms: string[]
  [key: string]: unknown
}

export interface Conflict {
  id: string
  node_a_id: string
  node_b_id: string
  conflict_type: string
  contradiction_score: number
  status: string
  suggested_strategy: string
}
