"""Pass 3 — local LLM extraction via Ollama (Doc 06 §5).

Only invoked when rules+NER miss goals/decisions or the turn is complex
(gated by the pipeline). Degrades gracefully: if Ollama is down, returns [].
Uses Ollama's format=json to force valid JSON (more reliable than regex-stripping).
"""

from __future__ import annotations

import json
import logging
import re

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


class LLMExtractor:
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "phi4-mini"):
        self.ollama_url = ollama_url
        self.model = model
        self._available: bool | None = None

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                self._available = any(self.model in m for m in models)
        except Exception:  # noqa: BLE001
            self._available = False
        return self._available

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
                        "model": self.model,
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
