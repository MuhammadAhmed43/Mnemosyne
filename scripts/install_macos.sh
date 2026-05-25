#!/bin/bash
# Mnemosyne Engine — macOS install (Doc 16 §2.1). Auto-starts via LaunchAgent.
set -e
BIN_DIR="/usr/local/bin"
PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"

cp mnemosyne-engine "$BIN_DIR/mnemosyne-engine"
chmod +x "$BIN_DIR/mnemosyne-engine"

cat > "$PLIST_DIR/com.mnemosyne.engine.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
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
  <key>StandardOutPath</key><string>$HOME/.mnemosyne/logs/engine.log</string>
  <key>StandardErrorPath</key><string>$HOME/.mnemosyne/logs/engine_err.log</string>
  <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
EOF

mkdir -p "$HOME/.mnemosyne/logs"
launchctl unload "$PLIST_DIR/com.mnemosyne.engine.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.mnemosyne.engine.plist"
echo "Mnemosyne Engine installed and running."
