"""First gate in the pipeline: block sensitive data before any storage (Doc 13 §4.1).

Runs before anything else (Doc 14 §1). On match, the whole capture is discarded
and we log only the pattern label — never the matched text.
"""

from __future__ import annotations

import re

from backend.models.extraction import SensitivityCheckResult

SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    # API keys
    (r"sk-ant-[A-Za-z0-9\-]{20,}", "Anthropic API key"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI API key"),
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"github_pat_[A-Za-z0-9_]{82}", "GitHub PAT"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub token"),
    (r"xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}", "Slack bot token"),
    # Generic credentials
    (
        r"(?:api[_\-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*[\"']?[A-Za-z0-9\-_+/]{20,}",
        "Generic credential",
    ),
    (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer token"),
    # Private keys / certs
    (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "Private key"),
    (r"-----BEGIN CERTIFICATE-----", "Certificate"),
    # PII
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
    (r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b", "Credit card"),
    (r"\b3[47]\d{13}\b", "Amex card"),
    # Connection strings
    (r"(?:postgres(?:ql)?|mysql|mongodb|redis):\/\/[^:\s]+:[^@\s]+@", "Database connection string"),
    (r"(?:POSTGRES|MYSQL|DATABASE)_(?:URL|URI|PASSWORD)\s*=\s*\S+", "DB env var"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in SENSITIVE_PATTERNS]


def contains_sensitive_data(text: str) -> SensitivityCheckResult:
    """Must run <10ms (Doc 14 §6). Patterns are pre-compiled at import."""
    for pattern, label in _COMPILED:
        if pattern.search(text):
            return SensitivityCheckResult(is_sensitive=True, pattern_matched=label)
    return SensitivityCheckResult(is_sensitive=False)


def check_custom_blocked_terms(text: str, terms: list[str]) -> SensitivityCheckResult:
    """User-defined blocked terms from settings (Doc 13 §4.2)."""
    lowered = text.lower()
    for term in terms:
        if term and term.lower() in lowered:
            return SensitivityCheckResult(is_sensitive=True, pattern_matched=f"Custom: {term}")
    return SensitivityCheckResult(is_sensitive=False)
