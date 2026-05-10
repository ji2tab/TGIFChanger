#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer & Migrator
# Version:     v2.0.0
# =============================================================================

set -e
VERSION="v2.0.0"
OLD_DIR="/opt/tgifchanger"
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger-Py (v2.0.0) Smart Installer"
echo "=================================================="

if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# 1. 古いシェル版の残骸を完全に掃除する (Migration)
echo "🧹 旧バージョンのクリーンアップを実行中..."
sudo systemctl stop log_monitor auto_tg_restore tgifchanger-py 2>/dev/null || true
sudo systemctl disable log_monitor auto_tg_restore 2>/dev/null || true
sudo rm -f /etc/systemd/system/log_monitor.service /etc/systemd/system/auto_tg_restore.service
sudo rm -rf "$OLD_DIR"

# 2. Python依存関係の確認
echo "📦 Python環境を確認中..."
sudo apt-get update -yq || true
sudo apt-get install -yq python3 || true

# 3. 新しいディレクトリへのインストール
echo "📁 インストールディレクトリ作成: $NEW_DIR"
sudo mkdir -p "$NEW_DIR"

echo "📥 最新のPythonスクリプトを取得中..."
for f in tgif_daemon.py tg_change.py; do
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 設定ファイル (既存の設定を保護)
if [ ! -f "/etc/tgifchanger.conf" ]; then
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "/etc/tgifchanger.conf" "${RAW_URL}/tgifchanger.conf"
fi

# 4. 新しい単一サービス (tgifchanger-py.service) の登録
echo "⚙️  systemd ユニットを構成中..."
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service
Wants=mmdvmhost.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${NEW_DIR}/tgif_daemon.py
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py
sudo systemctl start tgifchanger-py

echo "=================================================="
echo " ✅ Python Edition Migration Completed!"
echo "--------------------------------------------------"
echo " ログ確認コマンド:"
echo "    journalctl -u tgifchanger-py -f"
echo "=================================================="
