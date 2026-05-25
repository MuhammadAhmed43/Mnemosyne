# FIX — Plan 01: Models, Config & Database Schema
## Fixes for C-01 and C-02
---

## HOW TO USE THIS FILE
Apply each fix block to the file and exact location shown in the header.
Do NOT rewrite the whole file — just make the two surgical changes below.

---

## FIX C-01 — `WorkspaceStatus.DELETED` not in SQL CHECK
**File to edit:** `backend/db/schema.py`
**Section:** Global Database (global.db) → `workspaces` table
**Find this line (at the end of the CREATE TABLE workspaces block):**

```sql
    CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'paused'))
```

**Replace with:**

```sql
    CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'paused', 'deleted'))
```

**Why:** The Python enum `WorkspaceStatus` in `backend/models/enums.py` already has
`DELETED = "deleted"`. Any code path that soft-deletes a workspace (e.g. `DELETE /workspaces/{id}`
with `confirm: true`) sets `status = 'deleted'`. Without this fix, SQLite throws a CHECK
constraint violation and the delete crashes at runtime. The enum value and the SQL constraint
must always be in sync. (Ref: Doc 07 §3.1, C-01 conflict report)

---

## FIX C-02 — `configure_sqlcipher()` missing KDF algorithm PRAGMA
**File to edit:** `backend/db/encryption.py`
**Function:** `configure_sqlcipher(conn, key)`
**Find this block:**

```python
def configure_sqlcipher(conn, key: str):
    conn.execute(f"PRAGMA key='{key}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
```

**Replace with:**

```python
def configure_sqlcipher(conn, key: str):
    conn.execute(f"PRAGMA key='{key}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    # Required by Doc 13 §3.1 — without this, SQLCipher may silently fall back
    # to a weaker KDF (e.g. PBKDF2_HMAC_SHA1) on older SQLCipher versions.
    conn.execute("PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
```

**Why:** Doc 13 §3.1 explicitly specifies `cipher_kdf_algorithm=PBKDF2_HMAC_SHA512`.
Without this PRAGMA, certain SQLCipher builds default to a weaker algorithm. This is a
security requirement, not a performance one. The PRAGMA must be set immediately after the
key PRAGMA and before any other DB operations. (Ref: Doc 13 §3.1, C-02 conflict report)

---

## No other changes needed in Plan 01.
