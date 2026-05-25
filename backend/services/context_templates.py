"""Per-platform context formatting (Plan 12 §2)."""

from __future__ import annotations

PLATFORM_TEMPLATES = {
    "claude": "<context>\n{body}\n</context>",
    "chatgpt": "[System Context]\n{body}\n[End Context]",
    "gemini": "Context from previous sessions:\n{body}",
}


def format_context_for_platform(content: str, platform: str) -> str:
    return PLATFORM_TEMPLATES.get(platform, "{body}").format(body=content)
