#!/bin/bash
# =============================================================================
# TGIFChanger - Automated Installer / Updater
# 
# File:        install.sh
# Version:     v1.2.2
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Installs or updates the TGIFChanger suite on Pi-Star/WPSD.
#              Automatically detects existing installations, safely stops
#              services before updating, and preserves user configurations.
# License:     GPL v3
# =============================================================================

set -e

VERSION="v1.2.2"
INSTALL_DIR="/opt/tgifchanger"
BIN_DIR="/usr/local/bin"
CONF_DIR="/etc"
SYSTEMD_DIR="/etc/systemd/system"
RAW_URL_BASE="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger Installer / Updater ${VERSION}"
echo "=================================================="

# --- 新規/更新の判定 -------------------------------------------------------
if [ -d "$INSTALL_DIR" ]; then
    echo "🔄 既存のインストールを検出しました。アップデートを実行します..."
    IS_UPGRADE=1
else
    echo "🆕 新規インストールを実行します..."
    IS_UPGRADE=0
fi

# --- ファイルシステム書き込み有効化 (Pi-Star のみ) ---------------------------
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 ファイルシステムを書き込みモードへ変更中..."
    sudo rpi-rw
fi

# --- 依存パッケージの確認とインストール --------------------------------------
if ! command -v gpioset >/dev/null 2>&1; then
    echo "📦 GPIO制御に必要な 'gpiod' が見つかりません。インストールします..."
    sudo apt-get update -yq
    sudo apt-get install -yq gpiod || echo "⚠️ gpiod のインストールに失敗しました (sysfsフォールバックで続行します)"
else
    echo "✅ 依存パッケージ 'gpiod' はインストール済みです。"
fi

# --- 既存サービスの安全な停止 (アップデート時必須) ---------------------------
if [ "$IS_UPGRADE" -eq 1 ]; then
    echo "🛑 稼働中のサービスを安全に停止します..."
    for svc in log_monitor auto_tg_restore; do
        if systemctl is-active --quiet "$svc" 2>/dev/null || systemctl is-failed --quiet "$svc" 2>/dev/null; then
            sudo systemctl stop "$svc" || true
            echo "   - $svc 停止完了"
        fi
    done
fi

# --- ディレクトリ作成 ------------------------------------------------------
if [ "$IS_UPGRADE" -eq 0 ]; then
    echo "📁 インストールディレクトリ作成: ${INSTALL_DIR}"
    sudo mkdir -p "$INSTALL_DIR"
fi

# --- ファイル取得 (上書き) -------------------------------------------------
echo "📥 GitHub から最新のスクリプトを取得中..."
for f in tg_change.sh auto_tg_restore.sh log_monitor.sh; do
    echo "   - $f"
    sudo curl -fsSL -o "${INSTALL_DIR}/${f}" "${RAW_URL_BASE}/${f}"
    sudo chmod +x "${INSTALL_DIR}/${f}"
done

echo "   - tgifchanger.conf"
sudo curl -fsSL -o "${INSTALL_DIR}/tgifchanger.conf" "${RAW_URL_BASE}/tgifchanger.conf"

# --- 設定ファイルの保護と配置 ----------------------------------------------
if [ -f "${CONF_DIR}/tgifchanger.conf" ]; then
    echo "🛡️  既存の設定ファイル (${CONF_DIR}/tgifchanger.conf) を検出しました。"
    echo "   -> 現在のユーザー設定をそのまま保持・使用します。"
    echo "   -> 最新のデフォルト設定は tgifchanger.conf.dist として保存されます。"
    sudo mv "${INSTALL_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf.dist"
else
    echo "📝 新規設定ファイルを配置します: ${CONF_DIR}/tgifchanger.conf"
    sudo mv "${INSTALL_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf"
fi

# --- CLI シンボリックリンク作成 --------------------------------------------
echo "🔗 シンボリックリンクを作成・更新中..."
sudo ln -sf "${INSTALL_DIR}/tg_change.sh" "${BIN_DIR}/tg_change"

# --- systemd サービスファイル作成・更新 ------------------------------------
echo "⚙️  systemd ユニットを構成中..."

sudo tee "${SYSTEMD_DIR}/log_monitor.service" >/dev/null <<EOF
[Unit]
Description=TGIFChanger - MMDVM to GPIO Bridge
After=mmdvmhost.service
Wants=mmdvmhost.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/log_monitor.sh
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo tee "${SYSTEMD_DIR}/auto_tg_restore.service" >/dev/null <<EOF
[Unit]
Description=TGIFChanger - Auto TG Restore
After=mmdvmhost.service
Wants=mmdvmhost.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/auto_tg_restore.sh
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# --- サービス有効化・再起動 ------------------------------------------------
echo "🚀 サービスを再構築・起動しています..."
sudo systemctl daemon-reload
sudo systemctl enable log_monitor.service auto_tg_restore.service
sudo systemctl start  log_monitor.service auto_tg_restore.service

echo "=================================================="
if [ "$IS_UPGRADE" -eq 1 ]; then
    echo " ✅ Update Completed Successfully!"
else
    echo " ✅ Installation Completed Successfully!"
fi
echo "--------------------------------------------------"
echo "  Status:"
printf "    log_monitor     : %s\n" "$(systemctl is-active log_monitor)"
printf "    auto_tg_restore : %s\n" "$(systemctl is-active auto_tg_restore)"
echo "--------------------------------------------------"
echo " ログをリアルタイムで確認するには以下のコマンドを実行してください:"
echo "    journalctl -u log_monitor -u auto_tg_restore -f"
echo "=================================================="
