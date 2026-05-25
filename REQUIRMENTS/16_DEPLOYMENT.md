# DOCUMENT 16 — DEPLOYMENT
## Infrastructure, Installation, CI/CD, Monitoring, Scaling
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. DEPLOYMENT MODEL

Mnemosyne has a fundamentally different deployment model from web applications.

**What we ship:**
1. **Chrome Extension** — distributed via Chrome Web Store
2. **Local Engine** — distributed as a native installer (macOS .pkg, Windows .exe, Linux .deb/.rpm)

**What we do NOT ship:**
- No servers (in v1)
- No databases (except what runs on the user's machine)
- No CDN
- No Kubernetes clusters

The deployment problem is primarily an **installer engineering** and **update management** problem, not a cloud infrastructure problem.

---

## 2. LOCAL ENGINE INSTALLATION

### 2.1 macOS Installation (.pkg)

**Package contents:**
```
Mnemosyne.pkg
├── /usr/local/bin/mnemosyne-engine      ← Python executable (bundled with PyApp)
├── /usr/local/lib/mnemosyne/            ← Python dependencies
├── ~/Library/LaunchAgents/
│   └── com.mnemosyne.engine.plist       ← Auto-start at login
└── ~/Library/Application Support/
    └── Mnemosyne/                       ← Data directory
        └── (created on first run)
```

**First-run initialization:**
```python
def first_run_setup():
    """Runs on initial install. Idempotent — safe to re-run."""
    
    # Create data directory structure
    mnemosyne_dir = Path.home() / ".mnemosyne"
    for subdir in ["workspaces", "backups", "logs", "tls"]:
        (mnemosyne_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    # Generate auth token
    if not (mnemosyne_dir / "config.json").exists():
        token = secrets.token_urlsafe(32)
        config = {"token": token, "version": "1.0.0", "first_run": datetime.utcnow().isoformat()}
        (mnemosyne_dir / "config.json").write_text(json.dumps(config))
    
    # Generate TLS cert for localhost
    if not (mnemosyne_dir / "tls" / "cert.pem").exists():
        generate_localhost_cert(mnemosyne_dir / "tls")
    
    # Initialize global database
    init_global_db(mnemosyne_dir / "global.db")
    
    # Download default embedding model (if not present)
    if not model_cache_exists("BGE-M3"):
        download_model("BGE-M3")  # 567MB, shows progress bar
    
    # Check Ollama (optional — warn if not found)
    if not is_ollama_installed():
        show_notification("Ollama not found — LLM extraction disabled. Install Ollama for full features.")
```

**macOS plist (auto-start):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mnemosyne.engine</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/mnemosyne-engine</string>
        <string>--port</string>
        <string>7432</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/USERNAME/.mnemosyne/logs/engine.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/USERNAME/.mnemosyne/logs/engine_err.log</string>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
```

### 2.2 Windows Installation (.exe, NSIS)

**Key differences from macOS:**
- Windows Service or Task Scheduler (instead of launchd)
- `%APPDATA%\Mnemosyne\` as data directory (instead of `~/.mnemosyne`)
- PowerShell script for service registration

```powershell
# Register Windows Service
New-Service -Name "MnemosyneEngine" `
            -BinaryPathName "$env:PROGRAMFILES\Mnemosyne\engine.exe --port 7432" `
            -DisplayName "Mnemosyne Memory Engine" `
            -StartupType Automatic `
            -Description "Local AI memory engine for Project Mnemosyne"

# Start service
Start-Service MnemosyneEngine
```

### 2.3 Linux Installation (.deb and .rpm)

**systemd user service (not system service — runs as user):**
```ini
# ~/.config/systemd/user/mnemosyne.service

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
```

**Enable:**
```bash
systemctl --user enable mnemosyne
systemctl --user start mnemosyne
```

### 2.4 Python Bundling

We use **PyApp** to bundle the Python engine into a single executable:

```toml
# PyApp configuration
[tool.pyapp]
project = "mnemosyne-engine"
version = "1.0.0"
python-version = "3.11"
entry-point = "mnemosyne.engine:main"
distribution = "standalone"  # Bundle Python interpreter
```

This produces:
- macOS: `mnemosyne-engine` (arm64 + x86_64 universal binary)
- Windows: `mnemosyne-engine.exe`
- Linux: `mnemosyne-engine` (ELF)

**Benefits:**
- User does not need Python installed
- Dependency isolation
- Single-file distribution

---

## 3. CHROME EXTENSION DISTRIBUTION

### 3.1 Chrome Web Store

**Publishing pipeline:**
```yaml
# .github/workflows/publish-extension.yml

on:
  push:
    tags:
      - 'v*'  # Trigger on version tags

jobs:
  publish:
    steps:
      - name: Build extension
        run: pnpm build:chrome:production

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

### 3.2 Extension Update Flow

Chrome handles extension updates automatically. When a new version is published:
1. Chrome detects the new version within 24 hours
2. Extension updates silently in the background
3. On next browser restart, new version is active

**For breaking API changes:**
- Extension checks engine version on startup: `GET /health`
- If engine version < required: show "Please update the Mnemosyne engine" notification
- Engine updates are separate from extension updates (native installer)

### 3.3 Extension ID Stability

The Extension ID is derived from the developer key. We use a consistent key across all builds to maintain the same ID. This is critical because:
- The auth token is paired with a specific Extension ID
- The CORS policy in the engine allows only this specific extension ID
- If the ID changes, all users need to re-authenticate

---

## 4. CI/CD PIPELINE

### 4.1 Branch Strategy

```
main          ← Production releases only
├── develop   ← Integration branch
│   ├── feature/extraction-improvements
│   ├── feature/graph-viz
│   └── fix/conflict-resolution-bug
└── release/  ← Release candidate branches
    └── v1.1.0
```

### 4.2 Full CI Pipeline

```yaml
# .github/workflows/ci.yml

name: CI

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: mypy src/ --strict
      - run: pnpm eslint extension/src/
      - run: pnpm tsc --noEmit

  test-python:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ['3.11']
    steps:
      - uses: actions/checkout@v4
      - run: pip install uv
      - run: uv sync
      - run: uv run pytest tests/unit/ tests/integration/ -v --cov
      - run: uv run python tests/benchmarks/run_benchmarks.py

  test-extension:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm install
      - run: pnpm vitest run
      - run: pnpm build:chrome

  build-installers:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    if: github.ref == 'refs/heads/main'
    steps:
      - run: build installer for ${{ matrix.os }}
      - uses: actions/upload-artifact@v4
        with:
          name: installer-${{ matrix.os }}
          path: dist/

  sign-macos:
    needs: build-installers
    runs-on: macos-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Sign and notarize .pkg
        env:
          APPLE_DEVELOPER_ID: ${{ secrets.APPLE_DEVELOPER_ID }}
          APPLE_NOTARIZE_TEAM: ${{ secrets.APPLE_NOTARIZE_TEAM }}
        run: ./scripts/sign_and_notarize.sh
```

### 4.3 Release Process

```
1. Create release branch: git checkout -b release/v1.1.0
2. Update version in: pyproject.toml, manifest.json, package.json
3. Run full test suite (including E2E)
4. Run memory quality benchmarks — must meet targets
5. Manual QA on macOS, Windows, Linux
6. Merge to main
7. Tag: git tag v1.1.0
8. CI automatically: builds installers, signs macOS, submits extension
9. Create GitHub Release with installers attached
10. Update download links on website
```

---

## 5. MONITORING AND LOGGING

Mnemosyne is a local application — there is no central server to monitor. Monitoring is **local-only.**

### 5.1 Log Structure

```
~/.mnemosyne/logs/
├── engine.log          ← Main engine log (rotated daily, keep 7 days)
├── engine_err.log      ← Stderr (errors only)
├── extraction.log      ← Extraction pipeline events
└── audit.jsonl         ← Immutable audit trail (never rotated)
```

**Log format (structured JSON):**
```json
{
  "timestamp": "2025-06-07T10:30:00.123Z",
  "level": "INFO",
  "component": "extraction_worker",
  "event": "extraction_completed",
  "capture_id": "cap_abc123",
  "workspace_id": "ws_xyz789",
  "auto_committed": 3,
  "pending_review": 1,
  "duration_ms": 342
}
```

**Important:** Logs never contain:
- Message content (user messages or AI responses)
- Memory node content
- API tokens

### 5.2 Health Check

The extension polls the engine health every 30 seconds:
```
GET /health → { "status": "healthy", "version": "1.0.0", ... }
```

If health check fails 3 times in a row:
- Extension badge turns gray
- Notification: "Mnemosyne engine not responding. [Restart]"
- Extension offers to restart the daemon

### 5.3 Engine Health Dashboard (Memory Audit UI)

```
SYSTEM STATUS

Engine:           ● Running v1.0.0
Uptime:           3h 42m
Database:         ● OK
Vector Store:     ● OK
Extraction Queue: ● 0 items
Decay Worker:     ● Running (next: 6h)
Consolidation:    ● Running (next: 21h)

PERFORMANCE (last hour)
Captures processed: 24
Extractions/min:    0.4
Avg extraction ms:  312
Context queries:    18
Avg context ms:     187

STORAGE
Total nodes:        892
Archived nodes:     134
Vector embeddings:  758
Disk usage:         147 MB
```

### 5.4 Crash Recovery

When the engine crashes and restarts:
```python
async def startup_recovery():
    """Replays any captures that were queued but not processed at crash time."""
    
    # Read the disk-backed queue journal
    journal_path = MNEMOSYNE_DIR / "temp" / "capture_queue.jsonl"
    
    if not journal_path.exists():
        return
    
    unprocessed = []
    with open(journal_path) as f:
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

## 6. UPDATE STRATEGY

### 6.1 Engine Auto-Update

The engine checks for updates once per day:

```python
async def check_for_updates():
    """Check GitHub releases API for new engine version."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://api.github.com/repos/mnemosyne/engine/releases/latest"
            )
            latest = response.json()["tag_name"].lstrip("v")
            current = get_current_version()
            
            if semver.compare(latest, current) > 0:
                notify_user_of_update(latest)
    except Exception:
        pass  # Update check failure is non-critical; never crash for this
```

**No silent auto-update of the engine.** Updates require user action (download + install new package). This is because the engine modifies system-level components (launchd plist, Windows Service).

### 6.2 Extension Auto-Update

Chrome handles this automatically. No action required.

### 6.3 Model Updates

Embedding models and local LLMs are updated independently:
```bash
# User runs this when prompted:
mnemosyne-engine update-models
```

After a model update:
- Old embeddings are still valid (backward compatible)
- Re-embedding runs in the background over 24 hours
- Engine remains operational during re-embedding

---

## 7. DATA BACKUP

### 7.1 Automatic Daily Backup

```python
async def backup_all_workspaces():
    """Run daily. Keeps 7 days of backups."""
    backup_dir = MNEMOSYNE_DIR / "backups"
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    
    for workspace in get_active_workspaces():
        src_db = MNEMOSYNE_DIR / "workspaces" / workspace.id / "graph.db"
        dst_db = backup_dir / f"{workspace.id}_{timestamp}.db"
        
        # SQLite online backup — no lock on main DB
        conn = sqlite3.connect(str(src_db))
        backup = sqlite3.connect(str(dst_db))
        conn.backup(backup)
        backup.close()
    
    # Prune old backups (keep 7 days)
    cutoff = datetime.utcnow() - timedelta(days=7)
    for f in backup_dir.glob("*.db"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
```

### 7.2 User-Triggered Export

Via Memory Audit UI → "Export Workspace" → Downloads complete JSON export.

This is the recommended pre-migration path:
1. Export all workspaces as JSON
2. Install Mnemosyne on new machine
3. Import JSON files

---

## 8. UNINSTALL

**macOS uninstall:**
```bash
launchctl unload ~/Library/LaunchAgents/com.mnemosyne.engine.plist
rm ~/Library/LaunchAgents/com.mnemosyne.engine.plist
rm -rf /usr/local/lib/mnemosyne/
rm /usr/local/bin/mnemosyne-engine
# Optional (removes all memory data):
rm -rf ~/.mnemosyne/
```

The installer ships an `Uninstall Mnemosyne.app` that handles this with a GUI.

**Chrome extension:** Remove from chrome://extensions like any extension.

**Data retention post-uninstall:** `~/.mnemosyne/` persists after engine uninstall unless user explicitly deletes it. This is intentional — users should not lose memory data by accidentally uninstalling the engine. The data directory can be re-used on reinstall.
