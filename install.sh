#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer (v2.6.2)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Automates the deployment of the TGIFChanger-Py suite.
#              Configures:
#              - Core Daemon with 20s boot delay and unbuffered logging.
#              - Web Dashboard (Port 8080) for remote management.
#              - Firewall rules to allow web access.
# License:     GPL v3
# =============================================================================

set -e  # エラーが発生した時点で停止

# --- 定数定義 ---
VERSION="v2.6.2"
NEW_DIR="/opt/tgifchanger-py"
CONF_FILE="/etc/tgifchanger.conf"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " 🚀 TGIFChanger-Py ${VERSION} Full Installer"
echo "=================================================="

# 1. WPSD/Pi-Star を書き込み可能モードへ移行
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 システムを書き込み可能(RW)モードに切り替えています..."
    sudo rpi-rw
fi

# 2. 古いサービスの停止とクリーンアップ
echo "🧹 既存サービスの停止とクリーンアップ中..."
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true

# 3. インストールディレクトリの準備
echo "📁 ディレクトリ作成: ${NEW_DIR}"
sudo mkdir -p "${NEW_DIR}"

# 4. GitHubから最新ソースを取得 (キャッシュを無視)
echo "📥 スクリプト群をダウンロード中..."
FILES=("tgif_daemon.py" "tg_change.py" "web_ui.py")
for f in "${FILES[@]}"; do
    echo "   -> ${f} を取得中..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done

# 5. CLIツールのシンボリックリンク作成
echo "🔗 CLIツールのリンクを作成中..."
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 6. デフォルト設定ファイルの取得 (存在しない場合のみ)
if [ ! -f "${CONF_FILE}" ]; then
    echo "⚙️  デフォルト設定ファイルを生成中..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${CONF_FILE}" "${RAW_URL}/tgifchanger.conf"
fi

# 7. ファイアウォールの開放 (Port 8080)
echo "🛡️  ファイアウォールを構成中 (Port 8080)..."
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT || true
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    if ! grep -q "dport 8080" "$FW_FILE"; then
        echo "iptables -I INPUT -p tcp --dport 8080 -j ACCEPT" | sudo tee -a "$FW_FILE" > /dev/null
    fi
fi

# 8. システムサービス (Systemd) の登録
echo "⚙️  Systemd ユニットを構成中..."

# コアデーモン (起動遅延20秒、ログ遅延解消オプション付)
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

# Web UI ダッシュボード
sudo tee /etc/systemd/system/tgifchanger-web.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Web UI
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/web_ui.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

# 9. サービスの有効化と起動
echo "🚀 サービスを起動中..."
sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py tgifchanger-web
sudo systemctl start tgifchanger-py tgifchanger-web

echo "=================================================="
echo " ✅ インストールが完了しました！"
echo "--------------------------------------------------"
echo " 🌐 Webダッシュボード:"
echo "    http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo " 📋 ログ確認コマンド:"
echo "    journalctl -u tgifchanger-py -f"
echo "=================================================="
