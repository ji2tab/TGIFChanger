#!/bin/bash
# =============================================================================
# TGIFChanger Installer (Optimized for .sh extensions)
# -----------------------------------------------------------------------------
# Usage:
#   curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh \
#     | bash
#
# 本スクリプトは Pi-Star / WPSD の両環境で動作します。
# 実行ファイルはすべて .sh 拡張子を付与して配置されます。
# =============================================================================

set -e

VERSION="proto-1.1.0"
INSTALL_DIR="/opt/tgifchanger"
BIN_DIR="/usr/local/bin"
CONF_DIR="/etc"
SYSTEMD_DIR="/etc/systemd/system"
# リポジトリのURLに合わせて適宜変更してください
RAW_URL_BASE="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger Installer ${VERSION}"
echo "=================================================="

# --- ファイルシステム書き込み有効化 (Pi-Star のみ) ---------------------------
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 ファイルシステムを書き込みモードへ..."
    rpi-rw
fi

# --- 既存サービス停止 ------------------------------------------------------
for svc in log_monitor auto_tg_restore; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "⏸  既存サービス停止: $svc"
        sudo systemctl stop "$svc" || true
    fi
done

# --- ディレクトリ作成 ------------------------------------------------------
echo "📁 インストールディレクトリ作成: ${INSTALL_DIR}"
sudo mkdir -p "$INSTALL_DIR"

# --- ファイル取得 ----------------------------------------------------------
echo "📥 GitHub から最新の .sh ファイルを取得中..."
# リポジトリ上のファイル名が .sh であることを前提としています
for f in tg_change.sh auto_tg_restore.sh log_monitor.sh; do
    echo "   - $f"
    sudo curl -fsSL -o "${INSTALL_DIR}/${f}" "${RAW_URL_BASE}/${f}"
    sudo chmod +x "${INSTALL_DIR}/${f}"
done

echo "   - tgifchanger.conf"
sudo curl -fsSL -o "${INSTALL_DIR}/tgifchanger.conf" "${RAW_URL_BASE}/tgifchanger.conf"

# --- 設定ファイルの配置 ----------------------------------------------------
if [ -f "${CONF_DIR}/tgifchanger.conf" ]; then
    echo "ℹ️  既存の ${CONF_DIR}/tgifchanger.conf は保持します。"
    sudo cp "${INSTALL_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf.dist"
else
    sudo cp "${INSTALL_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf"
fi

# --- CLI シンボリックリンク作成 (.shなしで叩けるように設定) ----------------
echo "🔗 シンボリックリンク作成: ${BIN_DIR}/tg_change"
sudo ln -sf "${INSTALL_DIR}/tg_change.sh" "${BIN_DIR}/tg_change"

# --- systemd サービスファイル作成 (ExecStartを.shに更新) -------------------
echo "⚙️  systemd ユニットを登録中..."

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

# --- サービス有効化・起動 --------------------------------------------------
echo "🚀 サービスをリロード・起動..."
sudo systemctl daemon-reload
sudo systemctl enable log_monitor.service auto_tg_restore.service
sudo systemctl start  log_monitor.service auto_tg_restore.service

echo "=================================================="
echo " ✅ Installation Completed"
echo "--------------------------------------------------"
echo "  Status:"
printf "    log_monitor      : %s\n" "$(systemctl is-active log_monitor)"
printf "    auto_tg_restore  : %s\n" "$(systemctl is-active auto_tg_restore)"
echo "--------------------------------------------------"
echo " ログ確認:"
echo "   journalctl -u log_monitor -f"
echo "=================================================="