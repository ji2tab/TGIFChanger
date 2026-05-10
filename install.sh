#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer & Migrator
# 
# File:        install.sh
# Version:     v2.5.0 (Web UI Integration Edition)
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Complete installation of the TGIFChanger-Py suite, including:
#              - tgif_daemon (Core Service with 20s Boot Delay)
#              - tg_change (CLI Config Tool)
#              - web_ui (Web Dashboard on Port 8080)
# License:     GPL v3
# =============================================================================

set -e
VERSION="v2.5.0"
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger-Py (${VERSION}) Full Suite Installer"
echo "=================================================="

if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# 1. 古いサービスの停止とクリーンアップ
echo "🧹 旧バージョンのクリーンアップを実行中..."
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true

# 2. Python環境の確認
echo "📦 Python環境を確認中..."
if ! command -v python3 >/dev/null 2>&1; then
    sudo apt-get update -yq || true
    sudo apt-get install -yq python3 || true
else
    echo "   -> ✅ Python3 は既にインストールされています"
fi

# 3. インストールディレクトリとファイルの取得
echo "📁 インストールディレクトリ構成: $NEW_DIR"
sudo mkdir -p "$NEW_DIR"

echo "📥 最新のスクリプト群をGitHubから取得中..."
# daemon, cli, web_ui の3つを取得
for f in tgif_daemon.py tg_change.py web_ui.py; do
    echo "   -> $f をダウンロード中..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done

# CLIツールのシンボリックリンク作成
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 設定ファイル (既存の設定があれば保護)
if [ ! -f "/etc/tgifchanger.conf" ]; then
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "/etc/tgifchanger.conf" "${RAW_URL}/tgifchanger.conf"
fi

# =====================================================================
# 4. システムサービスの登録
# =====================================================================

# A. コアデーモン (20秒の起動遅延付き)
echo "⚙️  コアデーモンを構成中 (Boot Delay: 20s)..."
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 ${NEW_DIR}/tgif_daemon.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

# B. Web UI ダッシュボード (Port 8080)
echo "⚙️  Webダッシュボードを構成中 (Port 8080)..."
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

# 5. サービスの有効化と起動
echo "🚀 サービスを起動中..."
sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py tgifchanger-web
sudo systemctl start tgifchanger-py tgifchanger-web

echo "=================================================="
echo " ✅ 全機能のインストールが完了しました！"
echo "--------------------------------------------------"
echo " 🌐 Web管理画面へのアクセス:"
echo "    http://$(hostname).local:8080"
echo "    または http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo " ⌨️  コマンドライン操作:"
echo "    tg_change -c  (設定の確認)"
echo "=================================================="
