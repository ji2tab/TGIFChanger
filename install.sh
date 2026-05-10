#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Full Installer (v2.6.4)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Automates the setup of the entire TGIFChanger-Py suite.
# =============================================================================

set -e  # エラーで即停止

VERSION="v2.6.4"
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " 🛠  TGIFChanger-Py ${VERSION} Full Installer"
echo "=================================================="

# 1. 書き込み可能モードへ移行
if command -v rpi-rw >/dev/null 2>&1; then
    sudo rpi-rw
fi

# 2. 既存の古いサービスを停止
echo "🛑 既存サービスのクリーンアップ中..."
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true

# 3. ディレクトリの作成
sudo mkdir -p "$NEW_DIR"

# 4. ソースファイルの取得
echo "📥 最新スクリプトをダウンロード中..."
FILES=("tgif_daemon.py" "tg_change.py" "web_ui.py")
for f in "${FILES[@]}"; do
    echo "   -> ${f}..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done

# 5. CLIツールのシンボリックリンク作成
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 6. ファイアウォールの開放 (Port 8080)
echo "🛡️  ファイアウォールを構成中..."
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT || true
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    if ! grep -q "dport 8080" "$FW_FILE"; then
        echo "iptables -I INPUT -p tcp --dport 8080 -j ACCEPT" | sudo tee -a "$FW_FILE" > /dev/null
    fi
fi

# 7. Systemd サービス登録
echo "⚙️  システムサービスを登録中..."

# デーモンサービス
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service
[Service]
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

# Web UI サービス
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

# 8. 反映と起動
sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py tgifchanger-web
sudo systemctl start tgifchanger-py tgifchanger-web

echo "=================================================="
echo " ✅ インストールが完了しました！"
echo " 🌐 Webダッシュボード: http://$(hostname -I | awk '{print $1}'):8080"
echo "=================================================="
