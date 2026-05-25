# Security Policy

Mnemosyne is built around a simple promise: **your data never leaves your machine.**
Security and privacy are the foundation, not a feature.

## Security model

- **Local-only.** Extraction, storage, and retrieval all run on `localhost`. There is no
  backend server, no account, and no telemetry.
- **No raw transcripts.** Conversation text is never persisted — only the structured facts
  it reveals.
- **Encrypted at rest.** Databases use SQLCipher (AES-256) with a machine-derived key when
  the driver is available. The engine reports its true encryption status at `/health`.
- **Sensitive-data filtering.** API keys, passwords, card numbers, and secrets are detected
  and blocked **before** any extraction or storage.
- **Authenticated API.** The local engine requires a bearer token; the extension pairs once
  through a short, time-boxed window.
- **Auditable.** Every extraction, conflict resolution, and deletion is recorded in an
  append-only audit log.

## The only network calls

1. A one-time embedding/model download during install.
2. Calls to your **own local** Ollama instance, if you choose to install it.

That's it. No user data is transmitted anywhere.

## Reporting a vulnerability

If you discover a security issue, please **do not open a public issue**. Instead, report it
privately via [GitHub Security Advisories](../../security/advisories/new) (or open a minimal
issue asking for a private contact channel). Please include:

- A description of the issue and its impact.
- Steps to reproduce.
- Affected component (engine / extension) and version.

We aim to acknowledge reports within a few days and will credit reporters who wish to be
named once a fix ships.

## Supported versions

This project is in active development; security fixes target the latest `main`.
