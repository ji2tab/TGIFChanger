#!/bin/bash
set -e
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=== TGIFChanger-Py Installer v2.6.2 ==="

if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo mkdir -p "$NEW_DIR"

for f in tgif_daemon.py tg_change.py web_ui.py; do
    echo "📥 Downloading $f..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# サービス登録 ( python3 に -u オプションを追加してログの遅延を解消 )
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Daemon
After=mmdvmhost.service dmrgateway.service
[Service]
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/tgifchanger-web.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Web UI
[Service]
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/web_ui.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py tgifchanger-web
sudo systemctl start tgifchanger-py tgifchanger-web
echo "✅ インストール完了！ログを確認してください。"
