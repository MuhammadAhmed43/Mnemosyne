# DOCUMENT 13 — SECURITY & PRIVACY
## Threat Model, Privacy Design, Data Handling, Compliance
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. SECURITY PHILOSOPHY

Mnemosyne's security model is built on a single foundational principle:

> **The user's cognitive data is the most sensitive data we handle. It contains everything they think about, work on, and struggle with. Treating it with anything less than maximum care is a betrayal of trust.**

This means:
- Privacy is a design constraint, not a feature
- Every architectural decision is evaluated through a privacy lens
- Default settings must be the most private settings
- Users must be able to verify our claims, not just trust them

---

## 2. THREAT MODEL

### 2.1 Actors and Threats

**Threat Actor 1: Local Malware / Other Applications**

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| Port scanning | Attacker app reads from localhost:7432 | Bearer token auth + HTTPS, even on localhost |
| File system access | Malware reads SQLite files | SQLCipher AES-256 encryption at rest |
| Memory scraping | Malware reads engine process memory | Not mitigated in v1 (acceptable risk for local-first tool) |

**Threat Actor 2: Malicious Web Pages**

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| XSS attack via AI platform | Malicious content injected into AI platform DOM triggers capture | Extension validates message sources; only captures from known platform selectors |
| CSRF against local engine | Web page calls localhost:7432 | CORS restricted to extension origin only; Bearer token required |
| Extension fingerprinting | Page detects Mnemosyne is installed | Content scripts operate in isolated world; no global variables exposed |

**Threat Actor 3: Anthropic / AI Platforms Themselves**

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| Platform captures injection content | AI platform sees the injected context | By design — context injection is the feature; Mnemosyne injects nothing the user wouldn't type themselves |
| Platform data used for training | Injected context used to train models | User's responsibility; Mnemosyne doesn't alter what the user sends |

**Threat Actor 4: Supply Chain**

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| Compromised dependency | npm/pip package with malicious payload | Lockfiles for all deps; minimal external dependencies; regular audits |
| Compromised update | Malicious extension update | Chrome extension signing; code review on all PRs |

**Threat Actor 5: Physical Access**

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| Machine theft | Attacker accesses SQLite files | SQLCipher encryption; encryption key not stored in plaintext |
| Forensic analysis | Law enforcement imaging of device | Encryption at rest; deletion truly removes data (not soft-deleted in plaintext) |

### 2.2 Out of Scope Threats

- **State-level adversaries with hardware access** — not in threat model for v1
- **Zero-day browser vulnerabilities** — extension runs in sandboxed context
- **Social engineering** — cannot be prevented technically

---

## 3. ENCRYPTION DESIGN

### 3.1 Encryption at Rest (SQLCipher)

All SQLite databases are encrypted using SQLCipher with AES-256-CBC.

**Key Derivation:**
```python
def derive_encryption_key(user_password: Optional[str] = None) -> str:
    """
    Two modes:
    1. Machine-key mode (default): key derived from hardware identifiers
    2. Password mode (opt-in): key derived from user password
    """
    if user_password:
        # PBKDF2-HMAC-SHA512, 256,000 iterations
        salt = get_or_create_machine_salt()  # Stored in ~/.mnemosyne/salt (not encrypted)
        key = hashlib.pbkdf2_hmac(
            'sha512',
            user_password.encode('utf-8'),
            salt,
            iterations=256000
        )
    else:
        # Machine-key mode: hardware fingerprint
        machine_id = get_machine_id()  # /etc/machine-id on Linux, IOPlatformUUID on macOS
        salt = get_or_create_machine_salt()
        key = hashlib.pbkdf2_hmac('sha512', machine_id.encode(), salt, 100000)
    
    return key.hex()[:64]  # 256-bit key as hex string for SQLCipher PRAGMA

def configure_sqlcipher(conn: sqlite3.Connection, key: str):
    conn.execute(f"PRAGMA key='{key}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    conn.execute("PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")
```

**What is encrypted:**
- All workspace `graph.db` files — contains all memory nodes, edges, versions
- `global.db` — workspace metadata, settings
- Backup files

**What is NOT encrypted:**
- `~/.mnemosyne/salt` — needed to derive key; low-risk without the password/machine-id
- `~/.mnemosyne/config.json` — auth token, general settings; contains no memory data
- Qdrant vector files — embeddings only (semantic vectors, not raw content)

**Rationale for not encrypting vectors:** Vector embeddings are not human-readable and do not contain the original text. Reversing embeddings to recover text is computationally infeasible with current methods.

### 3.2 Encryption in Transit

All localhost communication uses HTTPS with a self-signed certificate:

```python
def generate_localhost_cert() -> Tuple[str, str]:
    """Generate self-signed cert for localhost, valid 10 years."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mnemosyne Local CA")]))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(IPv4Address("127.0.0.1"))
        ]), critical=False)
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    
    # Store cert and key in ~/.mnemosyne/tls/
    # Extension pins the certificate on install
    return cert_path, key_path
```

**Certificate pinning in extension:**
```typescript
// Extension stores cert fingerprint on install
// Validates on every request
const CERT_FINGERPRINT = await loadCertFingerprint();

async function secureRequest(endpoint: string, options: RequestInit) {
  // Chrome's fetch respects cert pinning via chrome.storage pinned cert
  return fetch(`https://localhost:7432${endpoint}`, options);
}
```

### 3.3 Auth Token

```python
# Generated on install, stored in ~/.mnemosyne/config.json
TOKEN = secrets.token_urlsafe(32)  # 256-bit cryptographically secure random

# Extension stores in chrome.storage.local (encrypted by Chrome)
# Every request must include: Authorization: Bearer {TOKEN}
```

**CORS Policy:**
```python
# Only the Mnemosyne extension origin is allowed
ALLOWED_ORIGINS = [
    f"chrome-extension://{EXTENSION_ID}",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 4. SENSITIVE DATA DETECTION

### 4.1 Pre-Extraction Filter

This is the **first thing that runs**, before any extraction or storage. If it triggers, the message pair is discarded immediately and never touches the database.

```python
SENSITIVE_PATTERNS = [
    # API Keys — major providers
    (r'sk-[A-Za-z0-9]{20,}', "OpenAI API key"),
    (r'sk-ant-[A-Za-z0-9\-]{20,}', "Anthropic API key"),
    (r'AKIA[A-Z0-9]{16}', "AWS Access Key"),
    (r'AIza[0-9A-Za-z\-_]{35}', "Google API key"),
    (r'github_pat_[A-Za-z0-9_]{82}', "GitHub PAT"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub token"),
    (r'xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}', "Slack bot token"),
    
    # Generic high-entropy strings in key contexts
    (r'(?:api[_\-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*["\']?[A-Za-z0-9\-_+/]{20,}', "Generic credential"),
    
    # Bearer tokens
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', "Bearer token"),
    
    # Private keys
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private key"),
    (r'-----BEGIN CERTIFICATE-----', "Certificate"),
    
    # PII
    (r'\b\d{3}-\d{2}-\d{4}\b', "SSN"),
    (r'\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b', "Credit card"),
    (r'\b3[47]\d{13}\b', "Amex card"),
    
    # Connection strings
    (r'(?:postgres|mysql|mongodb|redis):\/\/[^:\s]+:[^@\s]+@', "Database connection string"),
    (r'(?:POSTGRES|MYSQL|DATABASE)_(?:URL|URI|PASSWORD)\s*=\s*\S+', "DB env var"),
]

def contains_sensitive_data(text: str) -> SensitivityCheckResult:
    for pattern, label in SENSITIVE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return SensitivityCheckResult(
                is_sensitive=True,
                pattern_matched=label,
                # Never log the actual matched value
            )
    return SensitivityCheckResult(is_sensitive=False)
```

**Important:** When sensitive data is detected, we log only:
- Timestamp
- Pattern matched (e.g., "OpenAI API key")
- Session ID

We never log the matched text, the surrounding context, or the full message.

### 4.2 User-Defined Sensitive Terms

Users can add custom terms to always block:
```json
{
  "custom_blocked_terms": [
    "Project Nightingale",  // Internal codename
    "Sarah Johnson"         // Person who doesn't want to be in AI memory
  ]
}
```

---

## 5. DATA MINIMIZATION

### 5.1 What We Never Store

| Data Type | Never Stored | Why |
|-----------|-------------|-----|
| Raw conversation transcripts | ✓ | Only structured extractions are stored |
| API keys, passwords, credentials | ✓ | Sensitive data filter prevents this |
| Email addresses (unless manually entered) | ✓ | PII detection blocks this |
| SSNs, credit cards | ✓ | PII detection blocks this |
| Browser history | ✓ | Extension only observes AI platform tabs |
| Keystrokes / form data | ✓ | Extension only captures AI message pairs |

### 5.2 What We Store (Minimized)

| Data Type | What's Stored | Retention |
|-----------|--------------|-----------|
| Memory nodes | Extracted structured content only | Until user deletes or decay |
| Session metadata | Platform, session ID, timestamp | 90 days |
| Capture records | Status + workspace ID only | 30 days |
| Audit log | Action type, timestamp, entity ID | Permanent (append-only) |
| User settings | Preferences | Until user changes/deletes |

### 5.3 Right to Deletion

Users can delete any data at any time:

```
Node level:    Delete individual memory node (soft or hard)
Workspace:     Delete workspace + all its data
Complete purge: "Delete Everything" → removes all files, resets engine
```

**Hard delete implementation:**
```python
def hard_delete_node(node_id: str, workspace_id: str):
    # Remove from SQLite
    db.execute("DELETE FROM memory_nodes WHERE id = ?", node_id)
    db.execute("DELETE FROM node_versions WHERE node_id = ?", node_id)
    db.execute("DELETE FROM memory_edges WHERE source_node_id = ? OR target_node_id = ?", node_id, node_id)
    
    # Remove from Qdrant
    vector_store.delete(workspace_id=workspace_id, point_id=node_id)
    
    # Audit log entry (records deletion, not content)
    audit_log.append({
        "action": "hard_delete_node",
        "entity_id": node_id,
        "timestamp": now(),
        "initiated_by": "user"
    })
```

---

## 6. NETWORK ISOLATION

### 6.1 Default Network Behavior

By default, Mnemosyne makes **zero** outbound network requests containing user data.

**Allowed network calls (no user data):**
- Package update check: metadata only to pypi.org / npmjs.com
- Ollama: `localhost:11434` (local, no network)
- Qdrant: embedded, no network

**Blocked by design:**
- No telemetry
- No analytics
- No crash reporting (logs are local only)
- No remote model API calls (unless user explicitly enables cloud fallback)

### 6.2 If Cloud Fallback is Enabled (User Opt-In)

When local Ollama is unavailable and user has opted in to cloud LLM fallback:
- Only the raw text of the current conversation turn is sent
- Sent to Claude Haiku API (Anthropic)
- Subject to Anthropic's data policies
- User is shown clear warning before enabling

**Network request when cloud fallback fires:**
```python
# Only fires if: ollama_available=False AND user.cloud_fallback_enabled=True
# Shows warning in UI: "Using cloud AI for this extraction — conversation turn will be sent to Anthropic"
```

---

## 7. EXTENSION SECURITY

### 7.1 Manifest V3 Permissions (Minimal)

```json
{
  "permissions": [
    "storage",          // chrome.storage.local for token + settings
    "activeTab",        // Read current tab URL for workspace detection
    "scripting"         // Inject content scripts into AI platforms
  ],
  "host_permissions": [
    "https://claude.ai/*",
    "https://chat.openai.com/*",
    "https://gemini.google.com/*",
    "https://localhost:7432/*"
  ]
}
```

**What we explicitly do NOT request:**
- `<all_urls>` — would allow reading any page
- `history` — browser history access
- `bookmarks` — bookmark access
- `tabs` — full tabs API (we use `activeTab` only)
- `webRequest` — network request interception

### 7.2 Content Script Isolation

Content scripts run in an **isolated world** — they cannot access:
- Variables defined by the host page's JavaScript
- The host page's `window` object properties
- The host page's cookies

```typescript
// Content script only observes DOM mutations
// It never reads form data, cookies, or localStorage of the AI platform
const observer = new MutationObserver((mutations) => {
    // Only looks for specific AI platform message elements
    for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
            if (isAIResponseElement(node)) {
                captureMessagePair();
            }
        }
    }
});
```

### 7.3 No Remote Code Execution

The extension contains **no `eval()` calls** and no dynamically loaded scripts. All code is bundled at build time and reviewed during the Chrome Web Store review process.

---

## 8. AUDIT TRAIL

The audit log is append-only and cryptographically protected:

```python
class AuditLog:
    """
    Append-only log of all system actions.
    Users can read but not modify or delete entries.
    """
    
    def append(self, entry: AuditEntry) -> None:
        # Every entry includes a hash of the previous entry
        # This creates a chain — any modification is detectable
        prev_hash = self._get_last_hash()
        entry.chain_hash = hashlib.sha256(
            f"{prev_hash}{entry.timestamp}{entry.action}{entry.entity_id}".encode()
        ).hexdigest()
        
        self.db.execute("""
            INSERT INTO audit_log (id, timestamp, action, entity_type, entity_id, details, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ...)
```

**Users can verify the audit log has not been tampered with** via "Verify Integrity" in the Privacy settings page.

---

## 9. SECURITY RESPONSE POLICY

If a security vulnerability is found in Mnemosyne:

**Severity: Critical (data exfiltration, encryption bypass)**
- Patch released within 48 hours
- Extension auto-update triggered
- User notification with explanation

**Severity: High (authentication bypass)**
- Patch released within 7 days
- Extension update recommended

**Severity: Medium (minor privacy leak)**
- Patch in next release cycle (< 30 days)

**Reporting:**
- security@mnemosyne.local (internal for now; public bug bounty in v2)

---

## 10. PRIVACY CHECKLIST (ENGINEERING GATES)

Before any PR that touches data handling is merged:

- [ ] Does this PR write any new data to disk? If yes, is it encrypted?
- [ ] Does this PR make any new network request? If yes, does it contain user data?
- [ ] Does this PR read any sensitive patterns and fail to sanitize them?
- [ ] Does this PR add any logging that could capture message content?
- [ ] Does this PR respect the capture pause toggle?
- [ ] Does this PR's data have a clear deletion path?
- [ ] Is the data the minimum necessary for the feature?
- [ ] Does the audit log correctly record this action?

**This checklist is required for every data-touching PR. No exceptions.**
