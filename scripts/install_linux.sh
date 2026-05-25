#!/bin/bash
# Mnemosyne Engine — Linux install (Doc 16 §2.3). systemd user service.
set -e
cp mnemosyne-engine /usr/local/bin/
chmod +x /usr/local/bin/mnemosyne-engine

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/mnemosyne.service" <<EOF
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
echo "Mnemosyne Engine installed as a systemd user service."
