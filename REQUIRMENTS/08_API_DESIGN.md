# DOCUMENT 08 — API DESIGN
## All REST/WebSocket Endpoints, Contracts, Error Codes
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. API OVERVIEW

**Base URL:** `https://localhost:7432/api/v1`
**Protocol:** HTTPS (self-signed cert on localhost)
**Auth:** Bearer token (generated on install, stored in extension)
**Content-Type:** `application/json`

---

## 2. AUTHENTICATION

All endpoints require:
```
Authorization: Bearer {mnemosyne_local_token}
```

Token is generated on installation:
```python
import secrets
TOKEN = secrets.token_urlsafe(32)
# Stored in: ~/.mnemosyne/config.json
# Extension reads from: chrome.storage.local
```

---

## 3. CAPTURE ENDPOINTS

### POST /capture
Submit a conversation turn for processing.

**Request:**
```json
{
  "session_id": "sess_abc123",
  "platform": "claude",
  "user_message": "We decided to remove offline mode from the MVP",
  "ai_response": "That makes sense given your timeline...",
  "timestamp": "2025-06-07T10:30:00Z",
  "tab_url": "https://claude.ai/chat/abc",
  "workspace_id": "ws_xyz789",  // optional, omit for auto-detect
  "metadata": {
    "tab_id": 42,
    "conversation_id": "conv_123"
  }
}
```

**Response (202 Accepted):**
```json
{
  "capture_id": "cap_aaa111",
  "status": "queued",
  "workspace_id": "ws_xyz789",
  "estimated_processing_ms": 400,
  "sensitive_data_detected": false
}
```

**Response (if sensitive data):**
```json
{
  "capture_id": "cap_aaa112",
  "status": "blocked",
  "reason": "sensitive_data_detected",
  "patterns_matched": ["api_key"]
}
```

**Error Responses:**
| Code | Meaning |
|------|---------|
| 400 | Invalid request body |
| 401 | Invalid auth token |
| 413 | Message too long (> 50,000 chars) |
| 503 | Processing queue full |

---

### GET /capture/{capture_id}/status
Check processing status of a capture.

**Response:**
```json
{
  "capture_id": "cap_aaa111",
  "status": "completed",  // queued/processing/completed/failed/skipped
  "auto_committed": 3,
  "pending_review": 1,
  "processing_time_ms": 342,
  "nodes_created": ["node_001", "node_002", "node_003"],
  "pending_ids": ["pend_001"]
}
```

---

## 4. CONTEXT ENDPOINTS

### GET /context
Get reconstructed context for injection.

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_id | string | No | If omitted, auto-detected |
| token_budget | integer | No | Max tokens (default: 2000) |
| intent | string | No | Hint about current task |
| platform | string | Yes | claude/chatgpt/gemini |

**Example Request:**
```
GET /context?workspace_id=ws_xyz789&token_budget=1500&platform=claude
```

**Response:**
```json
{
  "workspace": {
    "id": "ws_xyz789",
    "name": "Blind Navigation Startup"
  },
  "context_string": "[MNEMOSYNE CONTEXT — Workspace: Blind Navigation Startup]\n\nCurrent Goals:\n• Submit hackathon demo by Sunday [HIGH]\n...",
  "token_count": 347,
  "nodes_included": 12,
  "nodes_available": 89,
  "freshness_score": 0.91,
  "injection_format": "system_prompt_prepend"
}
```

**Error Responses:**
| Code | Meaning |
|------|---------|
| 404 | Workspace not found |
| 503 | Retrieval engine not ready |

---

## 5. WORKSPACE ENDPOINTS

### GET /workspaces
List all workspaces.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| status | string | active | active/archived/paused/all |
| sort | string | last_active | last_active/created_at/name |

**Response:**
```json
{
  "workspaces": [
    {
      "id": "ws_xyz789",
      "name": "Blind Navigation Startup",
      "description": "Hackathon project for AI-powered navigation",
      "color": "#6366F1",
      "icon": "🧭",
      "status": "active",
      "capture_enabled": true,
      "last_active": "2025-06-07T10:30:00Z",
      "created_at": "2025-06-01T09:00:00Z",
      "tags": ["ml", "hackathon", "mobile"],
      "node_count": 89,
      "pending_review_count": 2,
      "memory_health_score": 0.87
    }
  ],
  "total": 1
}
```

---

### POST /workspaces
Create a new workspace.

**Request:**
```json
{
  "name": "Research: Transformer Interpretability",
  "description": "PhD research on attention head analysis",
  "color": "#10B981",
  "icon": "🔬",
  "tags": ["research", "ml", "interpretability"]
}
```

**Response (201):**
```json
{
  "id": "ws_new123",
  "name": "Research: Transformer Interpretability",
  "created_at": "2025-06-07T11:00:00Z",
  "status": "active"
}
```

---

### GET /workspaces/{id}
Get workspace details.

**Response:**
```json
{
  "id": "ws_xyz789",
  "name": "Blind Navigation Startup",
  "description": "...",
  "color": "#6366F1",
  "icon": "🧭",
  "status": "active",
  "capture_enabled": true,
  "tags": ["ml", "hackathon"],
  "stats": {
    "node_count": 89,
    "edge_count": 134,
    "goal_count": 7,
    "decision_count": 12,
    "open_problem_count": 3,
    "pending_review_count": 2,
    "conflict_count": 0,
    "memory_health_score": 0.87,
    "oldest_memory": "2025-06-01T09:00:00Z",
    "most_recent_capture": "2025-06-07T10:30:00Z"
  }
}
```

---

### PUT /workspaces/{id}
Update workspace.

**Request (partial update supported):**
```json
{
  "name": "New Name",
  "capture_enabled": false
}
```

---

### DELETE /workspaces/{id}
Delete workspace and all its data.

**Request:**
```json
{
  "confirm": true,
  "export_first": true  // If true, returns JSON export before deleting
}
```

**Response:**
```json
{
  "deleted": true,
  "export": { ... }  // Only if export_first was true
}
```

---

## 6. NODE ENDPOINTS

### GET /workspaces/{workspace_id}/nodes
List memory nodes.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| type | string | all | goal/decision/task/etc |
| status | string | active | active/archived/superseded/all |
| sort | string | importance | importance/created_at/last_accessed |
| limit | integer | 50 | Max results |
| offset | integer | 0 | Pagination |
| search | string | - | Full-text search |

**Response:**
```json
{
  "nodes": [
    {
      "id": "node_001",
      "node_type": "decision",
      "tier": "EPISODIC",
      "content": "Decided to remove offline mode from MVP",
      "structured_data": {
        "decision": "Remove offline mode",
        "rationale": "Scope too large for hackathon deadline",
        "reversible": true
      },
      "importance_score": 0.82,
      "extraction_confidence": 0.91,
      "user_verified": false,
      "reinforcement_count": 2,
      "created_at": "2025-06-03T09:30:00Z",
      "valid_from": "2025-06-03T09:30:00Z",
      "valid_until": null,
      "version": 1,
      "source_platform": "claude",
      "status": "ACTIVE"
    }
  ],
  "total": 89,
  "limit": 50,
  "offset": 0
}
```

---

### GET /workspaces/{workspace_id}/nodes/{node_id}
Get single node with full detail.

**Response includes:** node data + version history + connected edges + conflict events

---

### PUT /workspaces/{workspace_id}/nodes/{node_id}
Edit a memory node (user edit).

**Request:**
```json
{
  "content": "Updated content here",
  "structured_data": { "updated": "data" },
  "importance_score": 0.9,
  "is_permanent": true
}
```

**Behavior:**
- Creates new version (doesn't overwrite)
- Sets `changed_by: 'user'`
- Sets `user_verified: true`
- Old version archived in `node_versions`

---

### DELETE /workspaces/{workspace_id}/nodes/{node_id}
Delete a memory node.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| hard | boolean | If true, purge completely. Default: soft delete (archive) |

---

### POST /workspaces/{workspace_id}/nodes/{node_id}/boost
Boost importance of a node.

**Request:**
```json
{
  "boost_amount": 0.2,
  "reason": "user_explicit"
}
```

---

## 7. GRAPH ENDPOINTS

### GET /workspaces/{workspace_id}/graph
Get graph data for visualization.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| max_nodes | integer | 200 | Limit nodes returned |
| center_node | string | - | Return subgraph around this node |
| hops | integer | 3 | Hops from center node |
| filter_type | string | all | Filter by node type |

**Response:**
```json
{
  "nodes": [
    {
      "id": "node_001",
      "label": "Remove offline mode",
      "type": "decision",
      "importance": 0.82,
      "x": 120.5,    // Optional layout hint
      "y": 340.2
    }
  ],
  "edges": [
    {
      "id": "edge_001",
      "source": "node_001",
      "target": "node_002",
      "type": "CAUSED_BY",
      "label": "caused by"
    }
  ],
  "node_count": 89,
  "edge_count": 134
}
```

---

## 8. PENDING REVIEW ENDPOINTS

### GET /workspaces/{workspace_id}/pending
Get pending review items.

**Response:**
```json
{
  "items": [
    {
      "id": "pend_001",
      "candidate_type": "goal",
      "candidate_content": "Need to add obstacle avoidance by Sunday",
      "candidate_data": {
        "priority": "HIGH",
        "deadline": "2025-06-09"
      },
      "candidate_confidence": 0.71,
      "source_platform": "claude",
      "created_at": "2025-06-07T10:30:00Z",
      "expires_at": "2025-06-14T10:30:00Z",
      "source_context": "...the conversation snippet that generated this..."
    }
  ],
  "total": 2
}
```

---

### POST /workspaces/{workspace_id}/pending/{pending_id}/approve
Approve a pending extraction.

**Request (optional edits):**
```json
{
  "edits": {
    "content": "Add basic obstacle avoidance by hackathon deadline",
    "structured_data": { "priority": "HIGH" }
  }
}
```

---

### POST /workspaces/{workspace_id}/pending/{pending_id}/reject
Reject a pending extraction.

**Request:**
```json
{
  "reason": "inaccurate"  // inaccurate/irrelevant/duplicate/other
}
```

---

## 9. CONFLICT ENDPOINTS

### GET /workspaces/{workspace_id}/conflicts
Get active conflicts.

### POST /workspaces/{workspace_id}/conflicts/{conflict_id}/resolve
Resolve a conflict manually.

**Request:**
```json
{
  "strategy": "keep_a",  // keep_a / keep_b / merge / custom
  "merged_content": "...",  // Only if strategy is 'merge' or 'custom'
  "reason": "We switched databases on June 15"
}
```

---

## 10. SETTINGS ENDPOINTS

### GET /settings
Get all settings.

### PUT /settings
Update settings.

**Request:**
```json
{
  "capture_enabled": true,
  "auto_commit_threshold": 0.85,
  "context_token_budget": 1500
}
```

---

## 11. HEALTH ENDPOINTS

### GET /health
Engine health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "database_ok": true,
  "vector_store_ok": true,
  "extraction_worker": "running",
  "decay_worker": "running",
  "queue_depth": 0,
  "workspace_count": 3,
  "total_node_count": 234
}
```

---

## 12. WEBSOCKET ENDPOINT

### WS /ws/events
Real-time event stream for extension UI updates.

**Events pushed from server:**
```json
// Extraction completed
{
  "event": "extraction_completed",
  "capture_id": "cap_aaa111",
  "workspace_id": "ws_xyz789",
  "nodes_committed": 3,
  "nodes_pending": 1
}

// New conflict detected
{
  "event": "conflict_detected",
  "workspace_id": "ws_xyz789",
  "conflict_id": "conf_001",
  "conflict_type": "DIRECT_FACT"
}

// Workspace suggestion
{
  "event": "workspace_suggestion",
  "suggested_name": "Fashion AI Research",
  "confidence": 0.82,
  "evidence": "Detected new entities: DALL-E, Stable Diffusion, style transfer"
}
```

---

## 13. ERROR RESPONSE FORMAT

All errors return:
```json
{
  "error": {
    "code": "NODE_NOT_FOUND",
    "message": "Memory node with ID 'node_xyz' was not found",
    "details": { "node_id": "node_xyz" },
    "timestamp": "2025-06-07T10:30:00Z"
  }
}
```

**Error Codes:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| INVALID_REQUEST | 400 | Malformed request body |
| UNAUTHORIZED | 401 | Invalid or missing token |
| NOT_FOUND | 404 | Resource doesn't exist |
| WORKSPACE_FULL | 409 | Max node count reached |
| SENSITIVE_DATA | 422 | Sensitive data detected in capture |
| QUEUE_FULL | 503 | Processing queue at capacity |
| ENGINE_ERROR | 500 | Internal processing error |
