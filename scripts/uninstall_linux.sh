#!/bin/bash
# Mnemosyne Engine — Linux uninstall (Doc 16 §8).
#   ./uninstall_linux.sh           remove engine, keep data
#   ./uninstall_linux.sh --purge   remove engine AND all data
set -e
PURGE=false
[[ "$1" == "--purge" ]] && PURGE=true

systemctl --user stop mnemosyne 2>/dev/null || true
systemctl --user disable mnemosyne 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/mnemosyne.service"
systemctl --user daemon-reload 2>/dev/null || true
rm -f /usr/local/bin/mnemosyne-engine
rm -rf /usr/local/lib/mnemosyne

DATA_DIR="$HOME/.mnemosyne"
if [ "$PURGE" = true ]; then
  rm -rf "$DATA_DIR"
  echo "Purged: $DATA_DIR (all memory data deleted)"
else
  echo "Engine removed. Memory data preserved at: $DATA_DIR"
  echo "To delete all data: rm -rf $DATA_DIR  (or re-run with --purge)"
fi
