#!/bin/bash
set -e
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

sudo systemctl stop tgifchanger-py 2>/dev/null || true
sudo mkdir -p "$NEW_DIR"

for f in tgif_daemon.py tg_change.py; do
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Classic Daemon
After=mmdvmhost.service
[Service]
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py
sudo systemctl start tgifchanger-py
echo "✅ Classic Restore Complete."
