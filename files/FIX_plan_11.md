# FIX — Plan 11: Deployment, CI/CD & Installers
## Fixes for C-10 and C-11
---

## HOW TO USE THIS FILE
Two independent changes: one replacement in an existing file, one new file to create.

---

## FIX C-10 — Log rotation must be daily (TimedRotatingFileHandler), not size-based
**File to edit:** `backend/utils/logging.py`

**Find the entire `setup_logging` function:**

```python
import logging
import json
from logging.handlers import RotatingFileHandler

def setup_logging(data_dir: Path):
    """Structured JSON logging. Rotated daily, keep 7 days."""
    log_dir = data_dir / "logs"

    # Main engine log
    engine_handler = RotatingFileHandler(
        log_dir / "engine.log", maxBytes=10_000_000, backupCount=7)
    engine_handler.setFormatter(JsonFormatter())

    # Error log
    err_handler = RotatingFileHandler(
        log_dir / "engine_err.log", maxBytes=5_000_000, backupCount=7)
    err_handler.setLevel(logging.ERROR)

    # Extraction log
    extraction_handler = RotatingFileHandler(
        log_dir / "extraction.log", maxBytes=10_000_000, backupCount=7)

    root = logging.getLogger("mnemosyne")
    root.setLevel(logging.INFO)
    root.addHandler(engine_handler)
    root.addHandler(err_handler)

    logging.getLogger("mnemosyne.extraction").addHandler(extraction_handler)
```

**Replace with:**

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
```

**Why:** Doc 16 §5.1 says logs are "rotated daily, keep 7 days." `RotatingFileHandler`
rotates on file size, not time. On a low-activity machine the log file might never reach
`maxBytes=10_000_000` and never rotate. On a busy machine it rotates multiple times a day,
making `backupCount=7` keep 7 *files* rather than 7 *days*. `TimedRotatingFileHandler` with
`when='midnight'` is the correct handler for the documented behaviour.
(Ref: Doc 16 §5.1, C-10 conflict report)

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

**Also update the Files Summary table in Plan 11 to include this file:**

```
| `scripts/uninstall_linux.sh`  | Linux uninstaller (systemd user service) |
```

**Why:** Doc 16 §8 documents uninstall procedures for all three platforms. The data
preservation behaviour (intentional — prevents accidental data loss) and the `--purge`
flag pattern should be consistent across all three uninstallers. Without the Linux uninstaller,
Linux users have no documented or scripted removal path, which is a deployment gap.
(Ref: Doc 16 §8, C-11 conflict report)

---

## No other changes needed in Plan 11.
