"""Workspace archetype templates (Plan 12 §4)."""

from __future__ import annotations

WORKSPACE_TEMPLATES: dict[str, dict] = {
    "research_project": {"icon": "🔬", "tags": ["research"], "description": "Academic or independent research"},
    "startup": {"icon": "🚀", "tags": ["startup", "product"], "description": "Startup or product development"},
    "client_work": {"icon": "💼", "tags": ["client"], "description": "Client-facing project or consulting"},
    "learning": {"icon": "📚", "tags": ["learning"], "description": "Course, tutorial, or self-study"},
    "blank": {"icon": "📝", "tags": [], "description": "Start from scratch"},
}


def template_for(key: str) -> dict:
    return WORKSPACE_TEMPLATES.get(key, WORKSPACE_TEMPLATES["blank"])
