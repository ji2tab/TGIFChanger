#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Full Suite Installer (v2.6.0)
# Description: Installs Daemon, CLI, Web UI and configures Firewall (Port 8080)
# =============================================================================

set -e
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger-Py Full Installation (with Firewall)"
echo "=================================================="

# WPSDを書き込み可能モードへ
if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# 1. サービスの停止
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true

# 2. ディレクトリ作成とファイル取得
sudo mkdir -p "$NEW_DIR"
for f in tgif_daemon.py tg_change.py web_ui.py; do
    echo "📥 Downloading $f..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 3. ファイアウォール設定 (Port 8080 開放)
echo "🛡️  Configuring Firewall (Port 8080)..."
# 今すぐ適用
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT || true

# WPSDの永続設定に追加 (重複チェック付き)
FW_FILE="/usr/local/bin/pistar-firewall"
RULE="iptables -I INPUT -p tcp --dport 8080 -j ACCEPT"
if [ -f "$FW_FILE" ]; then
    if ! grep -q "dport 8080" "$FW_FILE"; then
        echo "$RULE" | sudo tee -a "$FW_FILE" > /dev/null
        echo "   -> Added to $FW_FILE"
    fi
fi

# 4. システムサービス登録 (20s Boot Delay版)
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service network-online.target
[Service]
Type=simple
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 ${NEW_DIR}/tgif_daemon.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/tgifchanger-web.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Web UI
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 ${NEW_DIR}/web_ui.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

# 5. 起動
sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py tgifchanger-web
sudo systemctl start tgifchanger-py tgifchanger-web

echo "✅ Done! Access: http://$(hostname -I | awk '{print $1}'):8080"
