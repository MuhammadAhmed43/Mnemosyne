# Plan 11 — Deployment, CI/CD & Installers

> Covers: Doc 16 (Deployment — full), Doc 11 (Tech Stack — packaging), Doc 13 §3.2 (TLS cert generation)

---

## 1. PYTHON BUNDLING WITH PYAPP (Doc 16 §2.4)

### backend/pyproject.toml
```toml
[project]
name = "mnemosyne-engine"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.6",
    "sqlcipher3>=0.5",
    "qdrant-client>=1.8",
    "sentence-transformers>=2.7",
    "spacy>=3.7",
    "langraph>=0.1",
    "httpx>=0.27",
    "cryptography>=42.0",
    "tiktoken>=0.7",
]

[tool.pyapp]
project = "mnemosyne-engine"
version = "1.0.0"
python-version = "3.11"
entry-point = "mnemosyne.engine:main"
distribution = "standalone"
```

Produces single executables: `mnemosyne-engine` (macOS/Linux), `mnemosyne-engine.exe` (Windows). User does NOT need Python installed.

---

## 2. FIRST-RUN INITIALIZATION (Doc 16 §2.1)

### backend/setup/first_run.py
```python
async def first_run_setup():
    """Runs on initial install. Idempotent — safe to re-run."""
    data_dir = get_data_dir()  # ~/.mnemosyne or %APPDATA%\Mnemosyne

    # 1. Create directory structure
    for subdir in ["workspaces", "backups", "logs", "tls", "temp"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 2. Generate auth token
    if not (data_dir / "config.json").exists():
        token = secrets.token_urlsafe(32)
        config = {"token": token, "version": "1.0.0",
                  "first_run": datetime.utcnow().isoformat()}
        (data_dir / "config.json").write_text(json.dumps(config, indent=2))

    # 3. Generate machine salt
    if not (data_dir / "salt").exists():
        (data_dir / "salt").write_bytes(os.urandom(32))

    # 4. Generate TLS cert for localhost (Doc 13 §3.2)
    if not (data_dir / "tls" / "cert.pem").exists():
        generate_localhost_cert(data_dir / "tls")

    # 5. Initialize global database
    init_global_db(data_dir / "global.db")

    # 6. Download embedding model
    if not model_cache_exists("BGE-M3"):
        logger.info("Downloading BGE-M3 embedding model (567 MB)...")
        download_model("BGE-M3", progress_callback=log_progress)

    # 7. Check Ollama (optional)
    if not is_ollama_installed():
        logger.warning("Ollama not found — LLM extraction disabled.")

def get_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Mnemosyne"
    elif sys.platform == "darwin":
        return Path.home() / ".mnemosyne"
    else:
        return Path.home() / ".mnemosyne"
```

---

## 3. PLATFORM-SPECIFIC INSTALLERS

### 3A. Windows Installer (NSIS) — Doc 16 §2.2

#### scripts/install_windows.ps1
```powershell
# Post-install script run by NSIS installer

# Register as Windows Service
$enginePath = "$env:PROGRAMFILES\Mnemosyne\mnemosyne-engine.exe"

New-Service -Name "MnemosyneEngine" `
    -BinaryPathName "$enginePath --port 7432" `
    -DisplayName "Mnemosyne Memory Engine" `
    -StartupType Automatic `
    -Description "Local AI memory engine for Project Mnemosyne"

# Start the service
Start-Service MnemosyneEngine

# Add firewall rule for localhost only
New-NetFirewallRule -DisplayName "Mnemosyne Engine" `
    -Direction Inbound -LocalPort 7432 -Protocol TCP `
    -Action Allow -RemoteAddress 127.0.0.1

Write-Host "Mnemosyne Engine installed and running on localhost:7432"
```

### 3B. macOS Installer (.pkg) — Doc 16 §2.1

#### scripts/install_macos.sh
```bash
#!/bin/bash
set -e

INSTALL_DIR="/usr/local/lib/mnemosyne"
BIN_DIR="/usr/local/bin"
PLIST_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$INSTALL_DIR" "$PLIST_DIR"

# Copy engine binary
cp mnemosyne-engine "$BIN_DIR/mnemosyne-engine"
chmod +x "$BIN_DIR/mnemosyne-engine"

# Install LaunchAgent plist
cat > "$PLIST_DIR/com.mnemosyne.engine.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.mnemosyne.engine</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/mnemosyne-engine</string>
        <string>--port</string><string>7432</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key>
    <string>$HOME/.mnemosyne/logs/engine.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.mnemosyne/logs/engine_err.log</string>
    <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
EOF

# Load and start
launchctl load "$PLIST_DIR/com.mnemosyne.engine.plist"
echo "Mnemosyne Engine installed and running."
```

### 3C. Linux Installer (.deb) — Doc 16 §2.3

#### scripts/install_linux.sh
```bash
#!/bin/bash
set -e

cp mnemosyne-engine /usr/local/bin/
chmod +x /usr/local/bin/mnemosyne-engine

# Create systemd user service
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/mnemosyne.service" << 'EOF'
[Unit]
Description=Mnemosyne Memory Engine
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mnemosyne-engine --port 7432
Restart=on-failure
RestartSec=5
Environment=HOME=%h

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable mnemosyne
systemctl --user start mnemosyne
echo "Mnemosyne Engine installed as user service."
```

---

## 4. CHROME EXTENSION PUBLISHING (Doc 16 §3)

### .github/workflows/publish-extension.yml
```yaml
name: Publish Extension
on:
  push:
    tags: ['v*']

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
      - run: pnpm install
      - run: pnpm build:chrome:production

      - name: Package extension
        run: pnpm plasmo package

      - name: Submit to Chrome Web Store
        uses: mnao305/chrome-extension-upload@v4
        with:
          file-path: build/chrome-mv3-prod.zip
          extension-id: ${{ secrets.EXTENSION_ID }}
          client-id: ${{ secrets.CHROME_CLIENT_ID }}
          client-secret: ${{ secrets.CHROME_CLIENT_SECRET }}
          refresh-token: ${{ secrets.CHROME_REFRESH_TOKEN }}
```

Extension ID is stable (derived from developer key). CORS policy and auth token are paired with this ID.

---

## 5. BUILD INSTALLERS WORKFLOW (Doc 16 §4.2)

### .github/workflows/build-installers.yml
```yaml
name: Build Installers
on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - name: Install uv
        run: pip install uv

      - name: Build with PyApp
        run: |
          uv sync
          uv run pyapp build --target ${{ matrix.os }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: installer-${{ matrix.os }}
          path: dist/

  sign-macos:
    needs: build
    runs-on: macos-latest
    if: startsWith(github.ref, 'refs/tags/')
    steps:
      - uses: actions/download-artifact@v4
        with: { name: installer-macos-latest }

      - name: Sign and notarize
        env:
          APPLE_DEVELOPER_ID: ${{ secrets.APPLE_DEVELOPER_ID }}
          APPLE_NOTARIZE_TEAM: ${{ secrets.APPLE_NOTARIZE_TEAM }}
        run: ./scripts/sign_and_notarize.sh

  release:
    needs: [build, sign-macos]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/')
    steps:
      - uses: actions/download-artifact@v4

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            installer-macos-latest/*
            installer-windows-latest/*
            installer-ubuntu-latest/*
```

---

## 6. LOGGING & MONITORING (Doc 16 §5)

### backend/utils/logging.py
```python
import logging
import json
from logging.handlers import TimedRotatingFileHandler  # NOT RotatingFileHandler

def setup_logging(data_dir: Path):
    """Structured JSON logging. Rotated daily at midnight, keep 7 days. (Doc 16 §5.1)

    Uses TimedRotatingFileHandler (date-based) instead of RotatingFileHandler
    (size-based). Doc 16 §5.1 specifies 'rotated daily, keep 7 days' — size-based
    rotation cannot guarantee this behaviour: it may rotate multiple times per day
    on a busy system or never rotate on a quiet one.
    """
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Main engine log — rotate at midnight, keep 7 daily files
    engine_handler = TimedRotatingFileHandler(
        log_dir / "engine.log",
        when='midnight',       # Rotate at midnight local time
        interval=1,            # Every 1 day
        backupCount=7,         # Keep 7 days of logs
        encoding='utf-8',
        utc=True               # Rotate based on UTC midnight for consistency
    )
    engine_handler.setFormatter(JsonFormatter())

    # Error log — same rotation policy
    err_handler = TimedRotatingFileHandler(
        log_dir / "engine_err.log",
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8',
        utc=True
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(JsonFormatter())

    # Extraction log — same rotation policy
    extraction_handler = TimedRotatingFileHandler(
        log_dir / "extraction.log",
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8',
        utc=True
    )
    extraction_handler.setFormatter(JsonFormatter())

    root = logging.getLogger("mnemosyne")
    root.setLevel(logging.INFO)
    root.addHandler(engine_handler)
    root.addHandler(err_handler)

    logging.getLogger("mnemosyne.extraction").addHandler(extraction_handler)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "component": record.name.split(".")[-1],
            "event": record.getMessage(),
            # NEVER log message content (Doc 14)
        })
```

---

## 7. CRASH RECOVERY (Doc 16 §5.4)

### backend/setup/recovery.py
```python
async def startup_recovery(data_dir: Path):
    """Replays unprocessed captures from disk-backed queue journal."""
    journal = data_dir / "temp" / "capture_queue.jsonl"
    if not journal.exists():
        return

    unprocessed = []
    with open(journal) as f:
        for line in f:
            capture = CaptureRecord.model_validate_json(line)
            if capture.status == "queued":
                unprocessed.append(capture)

    if unprocessed:
        logger.info(f"Recovery: replaying {len(unprocessed)} unprocessed captures")
        for capture in unprocessed:
            await extraction_queue.push(capture)
```

---

## 8. AUTO-UPDATE CHECK (Doc 16 §6)

### backend/services/update_service.py
```python
class UpdateService:
    GITHUB_RELEASES_URL = "https://api.github.com/repos/mnemosyne/engine/releases/latest"

    def __init__(self, network_logger):
        self._network_logger = network_logger  # Injected dependency

    async def check_for_updates(self) -> Optional[UpdateInfo]:
        """Check once per day. No user data sent. Non-critical — never crash."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Log the OUTBOUND network call before it happens (Doc 13 §6, UC-22)
                await self._network_logger.log(
                    destination=self.GITHUB_RELEASES_URL,
                    purpose="update_check",
                    is_internal=False,
                    bytes_sent=0
                )
                r = await client.get(self.GITHUB_RELEASES_URL)
                latest = r.json()["tag_name"].lstrip("v")
                current = get_current_version()
                if semver.compare(latest, current) > 0:
                    return UpdateInfo(current=current, latest=latest,
                                     download_url=r.json()["html_url"])
        except Exception:
            pass  # Update check failure is non-critical
        return None
```

No silent auto-update of the engine. User must download + install manually.

---

## FIX C-11 — Missing `scripts/uninstall_linux.sh`
**File to create:** `scripts/uninstall_linux.sh`

Doc 16 §8 documents uninstall procedures for all three platforms. Plan 11 ships
`uninstall_windows.ps1` and `uninstall_macos.sh` but the Linux uninstaller is absent
from both the implementation section and the files summary table.

**Create this file at `scripts/uninstall_linux.sh`:**

```bash
#!/bin/bash
# Mnemosyne — Linux Uninstaller
# Doc 16 §8: Removes engine binary and systemd user service.
# Data directory (~/.mnemosyne/) is preserved by default — see note at bottom.
#
# Usage:
#   ./uninstall_linux.sh              # Remove engine, keep data
#   ./uninstall_linux.sh --purge      # Remove engine AND all data

set -e

PURGE=false
if [[ "$1" == "--purge" ]]; then
    PURGE=true
fi

echo "🧹 Mnemosyne Linux Uninstaller"
echo "================================"

# 1. Stop and disable the systemd user service
if systemctl --user is-active --quiet mnemosyne 2>/dev/null; then
    echo "Stopping mnemosyne service..."
    systemctl --user stop mnemosyne
fi

if systemctl --user is-enabled --quiet mnemosyne 2>/dev/null; then
    echo "Disabling mnemosyne service..."
    systemctl --user disable mnemosyne
fi

# 2. Remove the systemd unit file
SYSTEMD_UNIT="$HOME/.config/systemd/user/mnemosyne.service"
if [ -f "$SYSTEMD_UNIT" ]; then
    rm "$SYSTEMD_UNIT"
    echo "Removed: $SYSTEMD_UNIT"
    systemctl --user daemon-reload
fi

# 3. Remove the engine binary
if [ -f /usr/local/bin/mnemosyne-engine ]; then
    rm /usr/local/bin/mnemosyne-engine
    echo "Removed: /usr/local/bin/mnemosyne-engine"
fi

# 4. Remove any lib files if present
if [ -d /usr/local/lib/mnemosyne ]; then
    rm -rf /usr/local/lib/mnemosyne
    echo "Removed: /usr/local/lib/mnemosyne"
fi

# 5. Data directory — intentionally preserved unless --purge
# Doc 16 §8: "~/.mnemosyne/ persists after engine uninstall unless user
# explicitly deletes it. This is intentional — users should not lose memory
# data by accidentally uninstalling the engine."
DATA_DIR="$HOME/.mnemosyne"

if [ "$PURGE" = true ]; then
    if [ -d "$DATA_DIR" ]; then
        rm -rf "$DATA_DIR"
        echo "Purged: $DATA_DIR (all memory data deleted)"
    fi
else
    echo ""
    echo "✅ Engine removed. Memory data preserved at: $DATA_DIR"
    echo "   To delete all data: rm -rf $DATA_DIR"
    echo "   Or re-run with: ./uninstall_linux.sh --purge"
fi

echo ""
echo "Done. Remove the Chrome extension from chrome://extensions to complete uninstall."
```

**Make it executable (add to your build/packaging step):**
```bash
chmod +x scripts/uninstall_linux.sh
```

## 9. BACKUP WORKER (Doc 16 §7)

### backend/workers/backup_worker.py
```python
async def backup_worker(workspace_service: WorkspaceService, data_dir: Path):
    """Daily backup. Keeps 7 days. Uses SQLite online backup (no lock)."""
    while True:
        await asyncio.sleep(24 * 3600)
        backup_dir = data_dir / "backups"
        timestamp = datetime.utcnow().strftime('%Y%m%d')

        for ws in await workspace_service.get_active():
            src = data_dir / "workspaces" / ws.id / "graph.db"
            dst = backup_dir / f"{ws.id}_{timestamp}.db"
            conn = sqlite3.connect(str(src))
            backup = sqlite3.connect(str(dst))
            conn.backup(backup)
            backup.close(); conn.close()

        # Prune old backups (>7 days)
        cutoff = datetime.utcnow() - timedelta(days=7)
        for f in backup_dir.glob("*.db"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
        logger.info(f"Backup complete: {timestamp}")
```

---

## 10. UNINSTALL (Doc 16 §8)

### scripts/uninstall_windows.ps1
```powershell
Stop-Service MnemosyneEngine -ErrorAction SilentlyContinue
Remove-Service MnemosyneEngine -ErrorAction SilentlyContinue
Remove-Item "$env:PROGRAMFILES\Mnemosyne" -Recurse -Force
Remove-NetFirewallRule -DisplayName "Mnemosyne Engine" -ErrorAction SilentlyContinue
Write-Host "Engine removed. Data preserved at $env:APPDATA\Mnemosyne\"
Write-Host "To delete all data: Remove-Item $env:APPDATA\Mnemosyne -Recurse"
```

### scripts/uninstall_macos.sh
```bash
launchctl unload ~/Library/LaunchAgents/com.mnemosyne.engine.plist
rm ~/Library/LaunchAgents/com.mnemosyne.engine.plist
rm -rf /usr/local/lib/mnemosyne/
rm /usr/local/bin/mnemosyne-engine
echo "Engine removed. Data preserved at ~/.mnemosyne/"
echo "To delete all data: rm -rf ~/.mnemosyne/"
```

Data directory persists after uninstall (intentional — prevents accidental data loss).

---

## 11. RELEASE PROCESS CHECKLIST (Doc 16 §4.3)

```
1. Create release branch: git checkout -b release/v1.x.0
2. Update version in: pyproject.toml, manifest.json, package.json
3. Run full test suite (unit + integration + benchmarks + E2E)
4. Memory quality benchmarks must meet targets
5. Manual QA on macOS, Windows, Linux
6. Merge to main
7. Tag: git tag v1.x.0
8. CI auto-builds: installers + signs macOS + submits extension
9. Create GitHub Release with installers
10. Update download links
```

---

## Files Summary

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | Project config + PyApp bundling |
| `backend/setup/first_run.py` | First-run initialization |
| `backend/setup/recovery.py` | Crash recovery / queue replay |
| `backend/services/update_service.py` | Auto-update check |
| `backend/workers/backup_worker.py` | Daily backup worker |
| `backend/utils/logging.py` | Structured JSON logging |
| `scripts/install_windows.ps1` | Windows post-install |
| `scripts/install_macos.sh` | macOS installer script |
| `scripts/install_linux.sh` | Linux installer script |
| `scripts/uninstall_windows.ps1` | Windows uninstaller |
| `scripts/uninstall_macos.sh` | macOS uninstaller |
| `scripts/sign_and_notarize.sh` | macOS code signing |
| `.github/workflows/publish-extension.yml` | Extension publishing |
| `.github/workflows/build-installers.yml` | Installer build + release | `scripts/uninstall_linux.sh`  | Linux uninstaller (systemd user service) |

**Total: ~14 files.**

---

> **Next: Plan 12 — My Additions & Enhancements**
