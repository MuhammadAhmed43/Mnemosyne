"""SQLCipher key derivation + connection factory (Doc 13 §3.1).

Encryption-at-rest uses whole-DB SQLCipher (transparent, keeps FTS5/json_extract
working). When the SQLCipher driver is unavailable (common on Windows), we fall
back to stdlib sqlite3 — but NOT silently: callers surface `encrypted=False` via
/health, settings, and the audit log. See memory: project-backend-language.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mnemosyne.db")

# Detect a SQLCipher-capable driver once.
try:  # pragma: no cover - environment dependent
    import sqlcipher3 as _sqlcipher  # type: ignore

    SQLCIPHER_AVAILABLE = True
except ImportError:  # pragma: no cover
    try:
        from pysqlcipher3 import dbapi2 as _sqlcipher  # type: ignore

        SQLCIPHER_AVAILABLE = True
    except ImportError:
        _sqlcipher = None  # type: ignore
        SQLCIPHER_AVAILABLE = False


def get_machine_id() -> str:
    """Stable per-machine identifier for key derivation. Falls back to MAC."""
    system = platform.system()
    try:
        if system == "Windows":
            import winreg  # noqa: PLC0415

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                return str(guid)
        if system == "Linux":
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                fp = Path(p)
                if fp.exists():
                    return fp.read_text(encoding="utf-8").strip()
        if system == "Darwin":
            import subprocess  # noqa: PLC0415

            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
    except Exception:  # noqa: BLE001 - any failure -> MAC fallback
        pass
    return str(uuid.getnode())


def get_or_create_machine_salt(data_dir: Path) -> bytes:
    salt_path = data_dir / "salt"
    if salt_path.exists():
        return salt_path.read_bytes()
    salt = os.urandom(32)
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    salt_path.write_bytes(salt)
    return salt


def derive_encryption_key(data_dir: Path, user_password: Optional[str] = None) -> str:
    """PBKDF2-HMAC-SHA512 -> 64 hex chars (256-bit) for SQLCipher PRAGMA key."""
    salt = get_or_create_machine_salt(data_dir)
    if user_password:
        raw = hashlib.pbkdf2_hmac("sha512", user_password.encode(), salt, 256_000)
    else:
        raw = hashlib.pbkdf2_hmac("sha512", get_machine_id().encode(), salt, 100_000)
    return raw.hex()[:64]


def _configure_sqlcipher(conn: sqlite3.Connection, key: str) -> None:
    """Doc 13 §3.1 + C-02 fix (cipher_kdf_algorithm must be set explicitly)."""
    conn.execute(f"PRAGMA key='{key}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    conn.execute("PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")  # C-02


_SQLITE_MAGIC = b"SQLite format 3\x00"  # first 16 bytes of any plaintext SQLite file


def _is_plaintext_sqlite(db_path: Path) -> bool:
    """True if the file exists and is an UNencrypted SQLite DB. An encrypted
    SQLCipher file has a random header, so this cleanly distinguishes the two."""
    try:
        with db_path.open("rb") as f:
            return f.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def _migrate_plaintext_to_encrypted(db_path: Path, key: str) -> None:
    """One-time, in-place upgrade of a plaintext DB to SQLCipher (AES-256). Folds
    the WAL into the main file, exports through sqlcipher_export into a temp
    encrypted copy, then atomically swaps it in. Raises on failure so the caller
    can fall back to opening plaintext rather than risk data loss."""
    # 1) Collapse any WAL into the main file and drop the side files, so the
    #    export sees a single consistent file.
    pre = sqlite3.connect(str(db_path))
    try:
        pre.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pre.execute("PRAGMA journal_mode=DELETE")
        pre.commit()
    finally:
        pre.close()

    enc_path = db_path.with_name(db_path.name + ".enc")
    if enc_path.exists():
        enc_path.unlink()
    safe_key = key.replace("'", "''")
    safe_enc = str(enc_path).replace("'", "''")

    src = _sqlcipher.connect(str(db_path), check_same_thread=False)  # plaintext (no key)
    try:
        src.execute(f"ATTACH DATABASE '{safe_enc}' AS enc KEY '{safe_key}'")
        # Match _configure_sqlcipher so the result opens with the same PRAGMAs.
        src.execute("PRAGMA enc.cipher_page_size=4096")
        src.execute("PRAGMA enc.kdf_iter=256000")
        src.execute("PRAGMA enc.cipher_hmac_algorithm=HMAC_SHA512")
        src.execute("PRAGMA enc.cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")
        src.execute("SELECT sqlcipher_export('enc')")
        src.execute("DETACH DATABASE enc")
    finally:
        src.close()

    os.replace(enc_path, db_path)  # atomic swap
    for side in (db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        if side.exists():
            side.unlink()
    logger.info("encrypted plaintext database %s at rest (AES-256)", db_path.name)


def open_connection(db_path: Path, key: str) -> tuple[sqlite3.Connection, bool]:
    """Open an (encrypted if possible) connection. Returns (conn, encrypted).

    Existing plaintext DBs are transparently migrated to SQLCipher on first open
    once the driver is available, so enabling encryption never strands old data.
    Set MNEMOSYNE_DISABLE_ENCRYPTION=1 to force plaintext (e.g. for debugging)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    disabled = os.environ.get("MNEMOSYNE_DISABLE_ENCRYPTION") == "1"

    if SQLCIPHER_AVAILABLE and _sqlcipher is not None and not disabled:
        try:
            if _is_plaintext_sqlite(db_path):
                _migrate_plaintext_to_encrypted(db_path, key)
            conn = _sqlcipher.connect(str(db_path), check_same_thread=False)
            _configure_sqlcipher(conn, key)
            conn.execute("SELECT count(*) FROM sqlite_master")  # force key check now
            encrypted = True
        except Exception as e:  # noqa: BLE001 — never hard-fail DB open; degrade safely
            logger.error(
                "Encrypted open of %s failed (%s); opening plaintext instead. "
                "Set a fresh data dir or fix the key to enable encryption.",
                db_path.name, type(e).__name__,
            )
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            encrypted = False
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        if not disabled:
            logger.warning(
                "SQLCipher driver unavailable - database %s is NOT encrypted at rest. "
                "Install sqlcipher3-wheels to enable AES-256 encryption.",
                db_path.name,
            )
        encrypted = False

    # Use the connecting driver's own Row class — sqlite3.Row cannot wrap a
    # sqlcipher3 cursor (and vice-versa). Both expose the same mapping API.
    conn.row_factory = _sqlcipher.Row if encrypted and _sqlcipher is not None else sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Doc 14: crash safety
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn, encrypted
