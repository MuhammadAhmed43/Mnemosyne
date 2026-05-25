#!/bin/bash
# Mnemosyne Engine — macOS uninstall (Doc 16 §8). Data preserved by default.
launchctl unload "$HOME/Library/LaunchAgents/com.mnemosyne.engine.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.mnemosyne.engine.plist"
rm -f /usr/local/bin/mnemosyne-engine
rm -rf /usr/local/lib/mnemosyne
echo "Engine removed. Memory data preserved at ~/.mnemosyne/"
echo "To delete all data: rm -rf ~/.mnemosyne/"
