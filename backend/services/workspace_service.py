"""Workspace lifecycle, inference, health, export/import (Doc 10 §8, Doc 08 §5)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional
from urllib.parse import urlparse

from backend.config import MnemosyneConfig
from backend.db.manager import DatabaseManager
from backend.models.enums import WorkspaceStatus
from backend.models.workspace import Workspace
from backend.repositories.audit_repo import AuditRepository
from backend.repositories.conflict_repo import ConflictRepository
from backend.repositories.node_repo import NodeRepository
from backend.repositories.pending_review_repo import PendingReviewRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.services.embedding_service import EmbeddingService
from backend.utils.time import now_utc

logger = logging.getLogger("mnemosyne.workspace")

NEEDS_NEW_WORKSPACE = ""  # sentinel
INFER_THRESHOLD = 0.55  # Doc 10 §8 — at/above this, route to the matched workspace
# Mirror the infer threshold: if a substantive turn doesn't clearly belong to ANY
# existing workspace (similarity < 0.55), give it its own workspace rather than
# forcing it into a loosely-related one.
AUTO_CREATE_MAX_SIM = 0.55
# A URL→workspace pin is only honored for a substantive turn if the content is
# genuinely about the pinned workspace. Kept fairly high because two unrelated
# software projects still embed somewhat similarly — a loose pin would drag a new
# topic into the existing workspace. The LLM router is the real authority; this is
# the offline fallback.
URL_PIN_MIN_SIM = 0.62

# When the user explicitly declares a NEW project ("I want to build an app for X"),
# only reuse an existing workspace if it's a near-exact match — otherwise it's a
# new project and deserves its own workspace, even if thematically adjacent.
NEW_PROJECT_REUSE_SIM = 0.70
_NEW_PROJECT = re.compile(
    r"(?:i\s+(?:want|wanna|plan|intend|hope|aim|'?d\s+like)\s+to|i'?m\s+going\s+to|"
    r"i'?ll|let'?s|we'?re\s+going\s+to|we\s+want\s+to|i'?m\s+(?:building|making|creating|starting))\s+"
    r"(?:work\s+on|build|make|create|start|develop|launch|design|code|ship|do|begin|plan)?\s*.{0,30}?"
    r"\b(?:app|application|project|game|tool|platform|web\s?site|website|startup|product|"
    r"service|bot|extension|saas|system|software|library|prototype|mvp|marketplace|store|shop|engine|model)\b",
    re.IGNORECASE,
)


def is_new_project_declaration(text: str) -> bool:
    return bool(_NEW_PROJECT.search(text or ""))

# Filler words stripped when naming an auto-created workspace from a message.
_NAME_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on",
    "for", "with", "about", "is", "are", "was", "were", "be", "been", "being", "do",
    "does", "did", "how", "what", "why", "when", "where", "who", "which", "can", "could",
    "should", "would", "will", "shall", "may", "might", "i", "we", "you", "my", "our",
    "your", "me", "us", "it", "this", "that", "these", "those", "help", "please", "need",
    "want", "like", "get", "make", "let", "tell", "give", "show", "explain", "have", "has",
}


class WorkspaceService:
    def __init__(
        self,
        db: DatabaseManager,
        workspace_repo: WorkspaceRepository,
        embedding: EmbeddingService,
        audit_repo: AuditRepository,
        config: MnemosyneConfig,
    ):
        self.db = db
        self.repo = workspace_repo
        self.embeddings = embedding
        self.audit = audit_repo
        self.config = config

    def create(self, name: str, description: str = "", tags: Optional[list[str]] = None,
               color: str = "#3A66D6", icon: str = "") -> Workspace:
        if self.repo.count_active() >= self.config.max_active_workspaces:
            raise ValueError(f"Max active workspaces ({self.config.max_active_workspaces}) reached")
        ws = Workspace(
            name=name, description=description, tags=tags or [], color=color, icon=icon,
            summary_text=f"{name}. {description}. {' '.join(tags or [])}".strip(),
        )
        self.repo.create(ws)
        self.db.create_workspace_db(ws.id)
        self.audit.append("workspace_created", "workspace", ws.id, ws.id, {"name": name})
        return ws

    def get(self, workspace_id: str) -> Optional[Workspace]:
        return self.repo.get(workspace_id)

    def list(self, status: Optional[str] = None, sort: str = "last_active") -> list[Workspace]:
        return self.repo.list(status, sort)

    def archive(self, workspace_id: str) -> None:
        self.repo.update_fields(workspace_id, status=WorkspaceStatus.ARCHIVED)
        self.audit.append("workspace_archived", "workspace", workspace_id, workspace_id, {})

    def delete(self, workspace_id: str) -> dict:
        export = self.export_json(workspace_id)
        self.repo.delete(workspace_id)
        # Vector collection lives under the workspace dir; removed with it on disk cleanup.
        self.audit.append("workspace_deleted", "workspace", workspace_id, workspace_id, {})
        return export

    def infer_workspace(self, user_message: str, ai_response: str, tab_url: str = "") -> tuple[str, float]:
        active = self.repo.get_active()
        if not active:
            return NEEDS_NEW_WORKSPACE, 0.0
        combined = f"{user_message} {ai_response}"
        can_embed = self.embeddings.available
        # A turn carries real text; a context-injection probe (empty/short hint) does not.
        meaningful = len(combined.strip()) >= 40
        # An explicit "I want to build an app for X" declaration is a strong signal
        # to start a fresh workspace — it must not be trapped by the chat's pin.
        new_project = is_new_project_declaration(user_message)

        # URL pin (Doc 10 §8): honor it for context probes and when embeddings are
        # off. But for a substantive turn, only honor it if the content actually
        # fits the pinned workspace — one chat is often used for several topics, so
        # a stale pin must not trap an unrelated new topic (let content decide).
        if tab_url and not new_project:
            row = self.db.get_global().execute(
                "SELECT workspace_id FROM platform_mappings WHERE ? LIKE '%' || url_pattern || '%' "
                "ORDER BY priority DESC LIMIT 1",
                (tab_url,),
            ).fetchone()
            if row:
                mapped_id = row[0]
                if not can_embed or not meaningful:
                    return mapped_id, 1.0
                mapped = self.repo.get(mapped_id)
                fit = (
                    self.embeddings.similarity(combined, mapped.summary_text or f"{mapped.name} {mapped.description}")
                    if mapped else 0.0
                )
                if fit >= URL_PIN_MIN_SIM:
                    return mapped_id, 1.0
                # else: stale pin / topic switch -> fall through to content inference

        if not can_embed:
            return NEEDS_NEW_WORKSPACE, 0.0
        best_id, best = NEEDS_NEW_WORKSPACE, 0.0
        for ws in active:
            score = self.embeddings.similarity(combined, ws.summary_text or f"{ws.name} {ws.description}")
            if score > best:
                best_id, best = ws.id, score
        # A declared new project only reuses an existing workspace on a near-exact
        # match; otherwise force a new one (return conf 0.0 so the capture layer's
        # auto-create fires). A normal turn uses the usual threshold and reports the
        # real best score so the caller can tell a confident miss from a near-miss.
        threshold = NEW_PROJECT_REUSE_SIM if new_project else INFER_THRESHOLD
        if best >= threshold:
            return best_id, best
        return NEEDS_NEW_WORKSPACE, (0.0 if new_project else best)

    def suggest_name(self, user_message: str, ai_response: str = "") -> str:
        """Derive a short, human workspace name from what the user is asking,
        e.g. 'how do I file my taxes for 2026' -> 'File Taxes 2026'. Keyword
        extraction (stopword-stripped, first occurrences) — deterministic and
        offline, no LLM dependency in the synchronous capture path."""
        import re

        text = (user_message or "").strip() or (ai_response or "").strip()
        keywords: list[str] = []
        seen: set[str] = set()
        for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9'+#.-]*", text):
            low = tok.lower()
            if low in _NAME_STOPWORDS or len(tok) < 3 or low in seen:
                continue
            seen.add(low)
            keywords.append(tok if tok[:1].isupper() else tok.capitalize())
            if len(keywords) >= 4:
                break
        name = " ".join(keywords).strip()
        return name[:40] if name else "New Topic"

    def create_for_topic(self, user_message: str, ai_response: str, platform: str) -> Workspace:
        """Auto-create a workspace for a conversation that doesn't fit any existing
        one. Seeds summary_text with the conversation so future related chats match
        it via embedding inference (and consolidate instead of spawning duplicates)."""
        name = self.suggest_name(user_message, ai_response)
        ws = self.create(name=name, description=f"Auto-created from a {platform} conversation", icon="")
        summary = f"{user_message} {ai_response}".strip()[:500]
        self.repo.update_fields(ws.id, summary_text=summary)
        ws.summary_text = summary
        self.audit.append("workspace_auto_created", "workspace", ws.id, ws.id, {"name": name, "platform": platform})
        logger.info("auto-created workspace '%s' (%s) for off-topic %s conversation", name, ws.id, platform)
        return ws

    # --- URL -> workspace mappings (Doc 10 §8, Doc 17 §"remembered") --------- #
    # A recognized "container" segment (a Claude project, a ChatGPT custom GPT, a
    # Gemini gem) is stable across the many conversations inside it, so a mapping
    # keyed there generalizes. Anything else is keyed off the exact conversation
    # path (no generalization), and a bare host with no path is too broad to store.
    _CONTAINER_SEGMENTS = {"project", "projects", "g", "gem", "gems", "app", "gpts"}

    def _url_pattern(self, url: str) -> str:
        """Derive a stable substring pattern from a chat URL (matcher uses
        `tab_url LIKE %pattern%`):
          - host + container/<id>  when a known container segment is present
            (generalizes across every chat in that project / GPT / gem);
          - host + full path       otherwise (pins just that one conversation);
          - host alone             for a path-less URL (the empty new-chat page)."""
        p = urlparse(url if "//" in url else f"//{url}")
        host = p.netloc or p.path.split("/")[0]
        parts = [s for s in p.path.split("/") if s]
        for i, seg in enumerate(parts):
            if seg in self._CONTAINER_SEGMENTS and i + 1 < len(parts):
                return f"{host}/{seg}/{parts[i + 1]}"
        return f"{host}/{'/'.join(parts)}" if parts else host

    def url_mapping(self, tab_url: str) -> Optional[str]:
        """The workspace this conversation URL is already bound to (or None).
        Used to keep routing sticky once a chat is pinned, so the per-turn LLM
        router can't re-route an ongoing conversation into a brand-new workspace."""
        if not tab_url:
            return None
        row = self.db.get_global().execute(
            "SELECT workspace_id FROM platform_mappings WHERE ? LIKE '%' || url_pattern || '%' "
            "ORDER BY priority DESC LIMIT 1",
            (tab_url,),
        ).fetchone()
        return row[0] if row else None

    def remember_mapping(self, platform: str, workspace_id: str, tab_url: str) -> str:
        """Persist 'this URL pattern -> this workspace' so future visits route
        deterministically. Re-pointing the same pattern replaces the old row.
        A host-only pattern (no path) is intentionally NOT stored — mapping an
        entire platform to one workspace from a single pick is too sweeping; the
        switch still applies to the current chat, just isn't remembered.
        Priority = pattern specificity (path depth). Returns the stored pattern
        (empty string when nothing was persisted)."""
        pattern = self._url_pattern(tab_url)
        if "/" not in pattern:
            logger.info("skip remembering host-only mapping %s (too broad)", pattern)
            return ""
        priority = pattern.count("/")  # host/seg=1, host/container/id=2, deeper chat=more
        conn = self.db.get_global()
        conn.execute("DELETE FROM platform_mappings WHERE url_pattern = ?", (pattern,))
        conn.execute(
            "INSERT INTO platform_mappings (id, platform, workspace_id, url_pattern, priority, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, platform, workspace_id, pattern, priority, now_utc().isoformat()),
        )
        conn.commit()
        self.audit.append(
            "mapping_remembered", "workspace", workspace_id, workspace_id,
            {"url_pattern": pattern, "platform": platform},
        )
        logger.info("remembered mapping %s -> %s (priority=%d)", pattern, workspace_id, priority)
        return pattern

    def get_health(self, workspace_id: str) -> float:
        conn = self.db.get_workspace(workspace_id)
        nr = NodeRepository(conn)
        active = nr.count(workspace_id)
        pending = len(PendingReviewRepository(conn).get_pending(workspace_id))
        conflicts = len(ConflictRepository(conn).get_pending(workspace_id))
        score = 1.0 - min(0.3, pending * 0.02) - min(0.4, conflicts * 0.05)
        score = round(max(0.0, score), 3)
        self.repo.update_fields(workspace_id, node_count=active, memory_health_score=score)
        return score

    def export_json(self, workspace_id: str) -> dict:
        ws = self.repo.get(workspace_id)
        conn = self.db.get_workspace(workspace_id)
        nodes = [dict(r) for r in conn.execute("SELECT * FROM memory_nodes WHERE workspace_id=?", (workspace_id,))]
        edges = [dict(r) for r in conn.execute("SELECT * FROM memory_edges WHERE workspace_id=?", (workspace_id,))]
        versions = [dict(r) for r in conn.execute("SELECT * FROM node_versions WHERE workspace_id=?", (workspace_id,))]
        return {
            "workspace": ws.model_dump(mode="json") if ws else {"id": workspace_id},
            "exported_at": now_utc().isoformat(),
            "nodes": nodes, "edges": edges, "node_versions": versions,
        }

    def import_json(self, data: dict) -> Workspace:
        wsdata = data["workspace"]
        ws = Workspace(**{k: v for k, v in wsdata.items() if k in Workspace.model_fields})
        self.repo.create(ws)
        conn = self.db.create_workspace_db(ws.id)
        for n in data.get("nodes", []):
            cols = ",".join(n.keys())
            conn.execute(f"INSERT OR IGNORE INTO memory_nodes ({cols}) VALUES ({','.join('?' * len(n))})", list(n.values()))
        for e in data.get("edges", []):
            cols = ",".join(e.keys())
            conn.execute(f"INSERT OR IGNORE INTO memory_edges ({cols}) VALUES ({','.join('?' * len(e))})", list(e.values()))
        conn.commit()
        return ws
