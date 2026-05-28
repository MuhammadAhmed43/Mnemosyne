"""Pass 3 — local LLM extraction via Ollama (Doc 06 §5).

Only invoked when rules+NER miss goals/decisions or the turn is complex
(gated by the pipeline). Degrades gracefully: if Ollama is down, returns [].
Uses Ollama's format=json to force valid JSON (more reliable than regex-stripping).
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

logger = logging.getLogger("mnemosyne.extraction")

SYSTEM_PROMPT = (
    "You are a cognitive extraction engine. Extract structured memory from an AI "
    "conversation turn. Extract ONLY what is explicitly stated or strongly implied. "
    "Do NOT infer things that aren't there. Do NOT extract generic/obvious facts. "
    "Return ONLY valid JSON, no preamble."
)

USER_PROMPT = """Extract structured memory from this conversation turn:

USER: {user_message}

AI: {ai_response}

Workspace context (for disambiguation): {workspace_summary}

Output JSON with these keys (use empty arrays when none found, no extra keys):
{{
  "goals": [{{"content": "...", "priority": "HIGH|MEDIUM|LOW", "deadline": "ISO date or null", "status": "ACTIVE|COMPLETED|ABANDONED"}}],
  "decisions": [{{"content": "...", "rationale": "...", "reversible": true}}],
  "preferences": [{{"content": "...", "domain": "communication|technical|workflow|other"}}],
  "open_problems": [{{"content": "...", "severity": "BLOCKING|IMPORTANT|MINOR"}}],
  "technical_facts": [{{"entity": "...", "attribute": "...", "value": "..."}}],
  "insights": [{{"content": "an idea or concept the user is exploring, summarized with how it works so it can be resumed later", "topic": "short label"}}]
}}"""


RECONCILE_SYSTEM = (
    "You maintain a developer's evolving project memory. Given the latest "
    "conversation turn and the project's existing memories, decide how the memory "
    "should change. Capture durable, reusable knowledge (goals, decisions + WHY, "
    "tech stack, requirements/constraints, use-cases, code/interfaces, problems, "
    "preferences). Ignore chit-chat, pleasantries, and one-off questions. "
    "Return ONLY valid JSON."
)

RECONCILE_PROMPT = """Project summary: {summary}

Existing memories (id [type] content):
{memories}

Latest turn:
USER: {user_message}
AI: {ai_response}

Decide the memory changes. Output JSON with these keys (use [] when none):
{{
  "add":       [{{"type": "<one of: goal|decision|task|problem|technical_fact|preference|insight|user_note|open_question|hypothesis|constraint|entity|event>", "content": "<concise, self-contained statement>"}}],
  "update":    [{{"id": "<existing id>", "content": "<the FULL updated statement, merging the new detail>", "reason": "<why>"}}],
  "supersede": [{{"id": "<existing id>", "type": "<type>", "content": "<the NEW statement that replaces it>", "reason": "<what changed>"}}],
  "complete":  [{{"id": "<existing id>", "reason": "<how it was completed>"}}],
  "profile":   [{{"content": "<a durable fact about the USER that applies across ALL their projects>"}}]
}}

Rules:
- add: NEW durable knowledge stated this turn that is NOT already in memory.
- update: an existing memory that this turn ELABORATES or adds detail to (same underlying truth) — return its full rewritten content.
- supersede: an existing memory whose CHOICE/DECISION changed (e.g. switched language/DB/approach) — return the new content.
- complete: an existing goal/task this turn marks done.
- profile: a fact about the USER THEMSELVES — role, experience level, skills, tools they always use, communication/coding preferences — that is true across every project (NOT specific to this one). Usually empty.
- CRITICAL — exploration vs commitment: distinguish what the USER actually decided from what the AI merely SUGGESTED or the user is exploring. Options the AI proposed, "here are some ideas", and "what it does / possible stack" discussion are exploratory — capture them as type "insight" or "hypothesis", NEVER as goal/decision. Use goal/decision ONLY when the USER explicitly commits or states firm intent (e.g. "I'll build X", "let's go with Y", "we decided Z").
- Use the actual words from the turn; never invent names, companies, or details not present.
- Never duplicate an existing memory. Prefer update over add when it's the same topic. Be comprehensive but precise."""


class LLMExtractor:
    # Re-probe Ollama at most this often. A permanent cache meant Ollama starting
    # *after* the engine (or dying mid-session) was never noticed; a short TTL lets
    # availability self-heal in both directions without hammering /api/tags.
    AVAILABILITY_TTL_SEC = 30.0

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "phi4-mini"):
        self.ollama_url = ollama_url
        self.model = model
        # The model actually used for calls: the configured one if installed, else
        # a fallback to whatever IS installed (so a not-yet-pulled / mistyped model
        # never silently disables extraction and drops us to shallow rule-based).
        self._active_model = model
        self._available: bool | None = None
        self._checked_at: float = 0.0

    async def is_available(self) -> bool:
        if self._available is not None and (time.monotonic() - self._checked_at) < self.AVAILABILITY_TTL_SEC:
            return self._available
        active: str | None = None
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
            installed = [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
            match = next((m for m in installed if self.model in m), None)
            if match:
                active = match
            elif installed:
                active = installed[0]
                logger.warning("configured model %r not installed; using %r instead", self.model, active)
        except Exception:  # noqa: BLE001
            active = None
        available = active is not None
        # Log transitions (availability flip OR which model is in use) for visibility.
        if available != self._available or (active and active != self._active_model):
            logger.info("LLM extraction %s (model=%s)", "available" if available else "unavailable", active or self.model)
        self._active_model = active or self.model
        self._available = available
        self._checked_at = time.monotonic()
        return self._available

    async def warm(self) -> None:
        """Pre-load the model into memory at startup so the FIRST capture isn't a
        cold ~100s load, and report whether Ollama is serving it on GPU or CPU
        (CPU is the usual reason captures feel slow). Fire-and-forget."""
        if not await self.is_available():
            return
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self._active_model, "prompt": "ok", "stream": False,
                          "keep_alive": "30m", "options": {"num_predict": 1}},
                )
                logger.info("LLM warm-up complete (model=%s) — %s", self._active_model, await self._placement(client))
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM warm-up failed: %s", type(e).__name__)

    async def _placement(self, client: httpx.AsyncClient) -> str:
        """Where Ollama is running the model: GPU / CPU / partial (from /api/ps)."""
        try:
            ps = (await client.get(f"{self.ollama_url}/api/ps")).json()
            m = next((x for x in ps.get("models", []) if self._active_model in x.get("name", "")), None)
            if not m:
                return "placement unknown"
            total, vram = m.get("size", 0) or 0, m.get("size_vram", 0) or 0
            if vram <= 0:
                return "running on CPU (slow — no GPU offload; captures will take longer)"
            if total and vram >= total * 0.95:
                return "running on GPU"
            return f"running partly on GPU ({round(vram / total * 100) if total else 0}% in VRAM, rest on CPU)"
        except Exception:  # noqa: BLE001
            return "placement unknown"

    async def extract(
        self, user_msg: str, ai_msg: str, workspace_summary: str = ""
    ) -> list[ExtractionCandidate]:
        if not await self.is_available():
            return []
        prompt = USER_PROMPT.format(
            user_message=user_msg[:3000],
            ai_response=ai_msg[:3000],
            workspace_summary=(workspace_summary or "none")[:500],
        )
        try:
            # Generous timeout: a cold model load can take ~100s; warm calls ~6s.
            # keep_alive keeps the model resident so subsequent captures are fast.
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self._active_model,
                        "system": SYSTEM_PROMPT,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "keep_alive": "15m",
                        "options": {"temperature": 0.1, "num_predict": 1024},
                    },
                )
                return self._parse(resp.json().get("response", ""))
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM extraction failed: %s", type(e).__name__)
            return []

    async def route_workspace(
        self, user_msg: str, ai_msg: str, workspaces: list[dict], current_id: str = ""
    ) -> dict:
        """Decide which workspace a turn belongs to, or that it's a new project.
        Biased to KEEP the conversation in its current workspace unless the turn is
        clearly a different project. Returns {"match_id", "new_name", "confidence"};
        {} on failure so the caller falls back to embedding/rule routing."""
        if not await self.is_available():
            return {}
        ws_lines = "\n".join(
            f'- id={w["id"]} name="{w["name"]}": {(w.get("summary") or "")[:160]}' for w in workspaces[:30]
        ) or "(no workspaces yet)"
        current_line = (
            f"\nThis conversation is CURRENTLY in workspace id={current_id}. Keep it there "
            "unless this turn is clearly about a DIFFERENT project.\n" if current_id else ""
        )
        prompt = (
            "You route a conversation turn to the right PROJECT workspace.\n\n"
            f"Existing workspaces:\n{ws_lines}\n"
            f"{current_line}\n"
            f"New turn:\nUSER: {user_msg[:1500]}\nAI: {ai_msg[:1500]}\n\n"
            "Rules:\n"
            "- Each workspace is ONE product/project. Two DIFFERENT products are different "
            "projects even if both are software/technical (e.g. a GPU marketplace vs a "
            "blind-navigation app are DIFFERENT — never merge them).\n"
            "- Return match_id ONLY if this turn is about the SAME product as that workspace.\n"
            "- If it continues the current conversation's project, return that workspace's id.\n"
            "- Otherwise it's a new project: leave match_id empty and give a new_name.\n"
            'Reply ONLY JSON: {"match_id": "<existing id, or empty>", "new_name": "<2-4 word Title Case name if new, else empty>", "confidence": 0.0}'
        )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self._active_model, "prompt": prompt, "stream": False, "format": "json",
                          "keep_alive": "15m", "options": {"temperature": 0.0, "num_predict": 120}},
                )
            cleaned = re.sub(r"```(?:json)?|```", "", resp.json().get("response", "")).strip()
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM routing failed: %s", type(e).__name__)
            return {}

    async def reconcile_memories(
        self, user_msg: str, ai_msg: str, existing: list[dict], workspace_summary: str = ""
    ) -> Optional[dict]:
        """The memory-diff brain: given the turn + the project's existing memories,
        return {add, update, supersede, complete}. Returns None on failure so the
        caller falls back to plain extraction."""
        if not await self.is_available():
            return None
        mem_lines = "\n".join(
            f'- id={m["id"]} [{m["type"]}] {(m.get("content") or "")[:200]}' for m in existing[:40]
        ) or "(no memories yet)"
        prompt = RECONCILE_PROMPT.format(
            summary=(workspace_summary or "none")[:600],
            memories=mem_lines,
            # Long AI answers were truncated to 3k chars, so most content was never
            # seen. Give the model a much larger window (it has the context for it).
            user_message=user_msg[:8000],
            ai_response=ai_msg[:8000],
        )
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self._active_model,
                        "system": RECONCILE_SYSTEM,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "keep_alive": "15m",
                        # Bigger output budget so a content-rich diff isn't cut off
                        # mid-JSON (which produced truncated memories).
                        "options": {"temperature": 0.1, "num_predict": 3072, "num_ctx": 16384},
                    },
                )
            cleaned = re.sub(r"```(?:json)?|```", "", resp.json().get("response", "")).strip()
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except Exception as e:  # noqa: BLE001
            logger.warning("memory reconcile failed: %s", type(e).__name__)
            return None

    def _parse(self, raw: str) -> list[ExtractionCandidate]:
        try:
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return []
        except (json.JSONDecodeError, ValueError):
            return []

        out: list[ExtractionCandidate] = []

        for g in data.get("goals", []):
            if len(str(g.get("content", ""))) > 10:
                out.append(self._mk(NodeType.GOAL, g["content"], 0.75, {
                    "priority": g.get("priority", "MEDIUM"),
                    "deadline": g.get("deadline"),
                    "status": g.get("status", "ACTIVE"),
                }))
        for d in data.get("decisions", []):
            if len(str(d.get("content", ""))) > 10:
                out.append(self._mk(NodeType.DECISION, d["content"], 0.75, {
                    "rationale": d.get("rationale", ""),
                    "reversible": d.get("reversible", True),
                }))
        for p in data.get("preferences", []):
            if len(str(p.get("content", ""))) > 5:
                out.append(self._mk(NodeType.PREFERENCE, p["content"], 0.70, {
                    "domain": p.get("domain", "other"),
                }))
        for op in data.get("open_problems", []):
            if len(str(op.get("content", ""))) > 5:
                out.append(self._mk(NodeType.PROBLEM, op["content"], 0.72, {
                    "severity": op.get("severity", "IMPORTANT"),
                }))
        for tf in data.get("technical_facts", []):
            if tf.get("entity") and tf.get("value"):
                content = f"{tf['entity']} {tf.get('attribute', 'is')} {tf['value']}"
                out.append(self._mk(NodeType.TECHNICAL_FACT, content, 0.75, {
                    "entity": tf["entity"],
                    "attribute": tf.get("attribute", "technology"),
                    "value": tf["value"],
                }))
        for ins in data.get("insights", []):
            if len(str(ins.get("content", ""))) > 15:
                topic = str(ins.get("topic", "")).strip()
                content = f"Idea — {topic}: {ins['content']}" if topic else str(ins["content"])
                out.append(self._mk(NodeType.INSIGHT, content, 0.80, {
                    "topic": topic, "kind": "idea", "source": "llm",
                }))
        return out

    @staticmethod
    def _mk(ntype: NodeType, content: str, conf: float, data: dict) -> ExtractionCandidate:
        return ExtractionCandidate(
            node_type=ntype,
            content=str(content)[:1200],
            structured_data=data,
            confidence=conf,
            source_pass="llm",
            evidence="llm_extraction",
        )
