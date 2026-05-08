#!/bin/bash
# =============================================================================
# TGIFChanger Installer (Prototype)
# -----------------------------------------------------------------------------
# Usage:
#   curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh \
#     | bash
#
# 本スクリプトは Pi-Star / WPSD の両環境で動作します。
#
# Layout:
#   /opt/tgifchanger/           実行ファイル本体
#   /etc/tgifchanger.conf       設定ファイル
#   /usr/local/bin/tg_change    CLIエントリ (symlink)
#   /etc/systemd/system/*.service  systemd ユニット
# =============================================================================

set -e

VERSION="proto-1.0.0"
INSTALL_DIR="/opt/tgifchanger"
BIN_DIR="/usr/local/bin"
CONF_DIR="/etc"
SYSTEMD_DIR="/etc/systemd/system"
RAW_URL_BASE="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger Installer ${VERSION}"
echo "=================================================="

# --- ファイルシステム書き込み有効化 (Pi-Star のみ rpi-rw 提供) ---------------
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 ファイルシステムを書き込みモードへ..."
    rpi-rw
fi

# --- 必須コマンド確認 -------------------------------------------------------
for cmd in curl sudo systemctl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "❌ エラー: $cmd が見つかりません。"
        exit 1
    fi
done

# --- libgpiod の推奨インストール (任意) -------------------------------------
if ! command -v gpioset >/dev/null 2>&1; then
    echo "ℹ️  libgpiod (gpioset) が見つかりません。"
    echo "   sysfs フォールバックで動作しますが、Bookworm 以降では"
    echo "   'sudo apt-get install -y gpiod' を推奨します。"
fi

# --- 既存サービス停止 (再インストール対応) ---------------------------------
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
echo "📥 GitHub からファイルを取得中..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

for f in tg_change auto_tg_restore log_monitor; do
    echo "   - $f"
    curl -fsSL -o "${TMP_DIR}/${f}" "${RAW_URL_BASE}/${f}"
done

echo "   - tgifchanger.conf"
curl -fsSL -o "${TMP_DIR}/tgifchanger.conf" "${RAW_URL_BASE}/tgifchanger.conf"

# --- 配置 ------------------------------------------------------------------
echo "📦 ${INSTALL_DIR} に配置..."
sudo install -m 0755 "${TMP_DIR}/tg_change"        "${INSTALL_DIR}/tg_change"
sudo install -m 0755 "${TMP_DIR}/auto_tg_restore"  "${INSTALL_DIR}/auto_tg_restore"
sudo install -m 0755 "${TMP_DIR}/log_monitor"      "${INSTALL_DIR}/log_monitor"

# 既存設定ファイルがあれば保護、なければ配置
if [ -f "${CONF_DIR}/tgifchanger.conf" ]; then
    echo "ℹ️  既存の ${CONF_DIR}/tgifchanger.conf は保持します。"
    echo "   新しいデフォルトは ${CONF_DIR}/tgifchanger.conf.dist にあります。"
    sudo install -m 0644 "${TMP_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf.dist"
else
    sudo install -m 0644 "${TMP_DIR}/tgifchanger.conf" "${CONF_DIR}/tgifchanger.conf"
fi

# --- CLI シンボリックリンク作成 --------------------------------------------
echo "🔗 シンボリックリンク作成: ${BIN_DIR}/tg_change"
sudo ln -sf "${INSTALL_DIR}/tg_change" "${BIN_DIR}/tg_change"

# --- systemd サービスファイル作成 ------------------------------------------
echo "⚙️  log_monitor.service を登録..."
sudo tee "${SYSTEMD_DIR}/log_monitor.service" >/dev/null <<EOF
[Unit]
Description=TGIFChanger - MMDVM to GPIO Bridge
After=mmdvmhost.service
Wants=mmdvmhost.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/log_monitor
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "⚙️  auto_tg_restore.service を登録..."
sudo tee "${SYSTEMD_DIR}/auto_tg_restore.service" >/dev/null <<EOF
[Unit]
Description=TGIFChanger - Auto TG Restore
After=mmdvmhost.service
Wants=mmdvmhost.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/auto_tg_restore
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# --- サービス有効化・起動 --------------------------------------------------
echo "🚀 サービスを有効化・起動..."
sudo systemctl daemon-reload
sudo systemctl enable log_monitor.service auto_tg_restore.service
sudo systemctl start  log_monitor.service auto_tg_restore.service

# --- 完了報告 ---------------------------------------------------------------
echo "=================================================="
echo " ✅ Installation Completed"
echo "--------------------------------------------------"
echo "  Install Dir : ${INSTALL_DIR}"
echo "  CLI Symlink : ${BIN_DIR}/tg_change"
echo "  Config File : ${CONF_DIR}/tgifchanger.conf"
echo "  Status:"
printf "    log_monitor      : %s\n" "$(systemctl is-active log_monitor)"
printf "    auto_tg_restore  : %s\n" "$(systemctl is-active auto_tg_restore)"
echo "--------------------------------------------------"
echo " ログ確認:"
echo "   journalctl -u log_monitor -f"
echo "   journalctl -u auto_tg_restore -f"
echo " 手動TG切替 (例: ホームTG 168 へ戻す):"
echo "   tg_change -168"
echo "=================================================="
