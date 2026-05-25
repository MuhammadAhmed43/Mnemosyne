# Changelog

All notable changes to this project are documented here. The format is loosely based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Local engine: 3-pass extraction (rules → spaCy NER → optional Ollama LLM), confidence
  routing, conflict resolution, decay, consolidation, and an append-only audit log.
- Per-workspace SQLite knowledge graph with FTS5 + Qdrant vector search.
- SQLCipher AES-256 encryption at rest, with transparent migration of existing plaintext
  databases and an honest `encryption_at_rest` flag on `/health`.
- Exact + embedding-based de-duplication so repeated facts reinforce one node.
- Auto-creation of a content-named workspace on a confident topic shift.
- Idea/insight capture for brainstorming and info-seeking turns.
- Chrome MV3 extension: live capture, context bar with workspace switcher and auto-insert,
  interactive knowledge graph (add/edit/boost/delete), pending review, conflicts, session
  replay, and JSON/CSV/Markdown export.
- Keyboard shortcuts, incognito mode, per-conversation pause, and a sensitive-data filter.
- Extraction quality eval harness (labeled cases + precision/recall) gating CI.
- One-step `pip install` (ships the spaCy model), `mnemosyne-engine` CLI, and a startup
  capability banner.

[Unreleased]: https://github.com/MuhammadAhmed43/Mnemosyne
