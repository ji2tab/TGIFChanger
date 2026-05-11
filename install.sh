#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer & Migrator
#
# File:        install.sh
# Version:     v2.3.0
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Changes from v2.1.7 (Gemini):
#   - ExecStartPre=/bin/sleep 20 廃止 → After= 依存関係で解決
#   - Restart=on-failure に変更 (仕様書§5準拠)
#   - Type=notify → Type=simple (sd_notify未実装のため)
#   - 旧 v2.x (tgifchanger-py) と旧 proto (log_monitor/auto_tg_restore) の
#     両方を削除するクリーンアップを維持
#   - [NEW] 究極の設定ファイル（テンプレート）の完全組み込み
# =============================================================================

set -euo pipefail

VERSION="v2.3.0"
INSTALL_DIR="/opt/tgifchanger-py"
CONF_FILE="/etc/tgifchanger.conf"
SERVICE="tgifchanger-py"
SYMLINK="/usr/local/bin/tg_change"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " TGIFChanger-Py (${VERSION}) Smart Installer"
echo "=================================================="

if [[ "${EUID}" -ne 0 ]]; then
    echo "❌ root権限で実行してください: sudo bash $0"
    exit 1
fi

if command -v rpi-rw >/dev/null 2>&1; then rpi-rw || true; fi

# ------------------------------------------------------------------
# 1. 旧バージョンのクリーンアップ
#    - Gemini版 v2.x (tgifchanger-py サービス / /opt/tgifchanger-py)
#    - proto-1.0.0 bash版 (log_monitor / auto_tg_restore)
#    - proto-1.0.0 python版 (/opt/tgifchanger)
# ------------------------------------------------------------------
echo "🧹 旧バージョンのクリーンアップ..."
for svc in log_monitor auto_tg_restore tgifchanger-py; do
    systemctl stop    "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
done
rm -f /etc/systemd/system/log_monitor.service \
      /etc/systemd/system/auto_tg_restore.service \
      /etc/systemd/system/tgifchanger-py.service
# 旧ディレクトリ (proto-1.0.0 は /opt/tgifchanger, Gemini版は /opt/tgifchanger-py)
rm -rf /opt/tgifchanger /opt/tgifchanger-py

# ------------------------------------------------------------------
# 2. Python3 確認
# ------------------------------------------------------------------
echo "📦 Python3 確認..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "   Python3 が見つかりません。インストールします..."
    apt-get update -yq || true
    apt-get install -yq python3 || true
else
    PY_VER=$(python3 -c "import sys; print('%d.%d'%sys.version_info[:2])")
    echo "   ✅ Python ${PY_VER} 確認済み"
fi

# ------------------------------------------------------------------
# 3. ファイル配置
# ------------------------------------------------------------------
echo "📁 インストール先: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# GitHub から直接取得する場合
if [[ "${1:-}" == "--from-github" ]]; then
    echo "📥 GitHub から最新ファイルを取得..."
    for f in tgif_daemon.py tg_change.py; do
        curl -H 'Cache-Control: no-cache' -fsSL \
             -o "${INSTALL_DIR}/${f}" "${RAW_URL}/${f}"
        chmod +x "${INSTALL_DIR}/${f}"
    done
else
    # ローカルファイルからインストール (デフォルト)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "📂 ローカルファイルからインストール: ${SCRIPT_DIR}"
    for f in tgif_daemon.py tg_change.py; do
        cp "${SCRIPT_DIR}/${f}" "${INSTALL_DIR}/${f}"
        chmod +x "${INSTALL_DIR}/${f}"
    done
fi

# CLIシンボリックリンク
ln -sf "${INSTALL_DIR}/tg_change.py" "${SYMLINK}"
echo "🔗 シンボリックリンク: ${SYMLINK}"

# ------------------------------------------------------------------
# 4. 設定ファイル (究極のテンプレート生成)
# ------------------------------------------------------------------
if [[ -f "${CONF_FILE}" ]]; then
    echo "📝 既存 ${CONF_FILE} を保持します。"
    echo "   新オプションの確認用テンプレートを ${CONF_FILE}.new に保存:"
    cat > "${CONF_FILE}.new" <<'EOF'
# TGIFChanger 設定ファイル (v2.3.0)
#
# Bash KEY=VALUE 形式。両方の環境で読み込み可能:
#   sudo bash install.sh     (インストール)
#   tg_change --status       (ステータス確認)
#   sudo tg_change -w 168    (設定変更)
#
# 設定変更後: sudo systemctl restart tgifchanger-py

LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
WATCH_TG="1"
RESTORE_TG="168"
RESTORE_DELAY="120"
GPIO_PIN="17"

# --- GPIO Backend (ハイブリッド対応) ---
# 
# GPIO_BACKEND:
#   "auto"     (デフォルト)
#              → pinctrl / raspi-gpio / sysfs を順に試す
#              → Pi-Star(Buster) on Pi Zero 2W で動作実績あり
#   "libgpiod"
#              → libgpiod v1/v2 を使用
#              → Bookworm / Pi5 環境に推奨 (仕様書§6)
#              → gpiodetect で gpiochip を自動判定
#   "pinctrl", "raspi-gpio", "sysfs", "null"
#              → 強制指定
#
GPIO_BACKEND="auto"

# GPIO_CHIP (libgpiod使用時のみ有効):
#   "auto"     (デフォルト) → gpiodetect で BCM チップを探す
#                            Pi4以前: gpiochip0
#                            Pi5:    gpiochip4
#   "0", "4"   → explicit chip number
#   "gpiochip0", "gpiochip4" → chip name
#
GPIO_CHIP="auto"

# --- TGIF API ---
TGIF_API="http://tgif.network:5040/api/sessions/update"
TGIF_API_TIMEOUT="10"

# --- ファイルパス ---
MMDVM_CONF="/etc/mmdvmhost"
DMRGATEWAY_CONF="/etc/dmrgateway"
EOF
else
    echo "📝 設定ファイルを新規作成: ${CONF_FILE}"
    cat > "${CONF_FILE}" <<'EOF'
# TGIFChanger 設定ファイル (v2.3.0)
#
# Bash KEY=VALUE 形式。両方の環境で読み込み可能:
#   sudo bash install.sh     (インストール)
#   tg_change --status       (ステータス確認)
#   sudo tg_change -w 168    (設定変更)
#
# 設定変更後: sudo systemctl restart tgifchanger-py

LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
WATCH_TG="1"
RESTORE_TG="168"
RESTORE_DELAY="120"
GPIO_PIN="17"

# --- GPIO Backend (ハイブリッド対応) ---
# 
# GPIO_BACKEND:
#   "auto"     (デフォルト)
#              → pinctrl / raspi-gpio / sysfs を順に試す
#              → Pi-Star(Buster) on Pi Zero 2W で動作実績あり
#   "libgpiod"
#              → libgpiod v1/v2 を使用
#              → Bookworm / Pi5 環境に推奨 (仕様書§6)
#              → gpiodetect で gpiochip を自動判定
#   "pinctrl", "raspi-gpio", "sysfs", "null"
#              → 強制指定
#
GPIO_BACKEND="auto"

# GPIO_CHIP (libgpiod使用時のみ有効):
#   "auto"     (デフォルト) → gpiodetect で BCM チップを探す
#                            Pi4以前: gpiochip0
#                            Pi5:    gpiochip4
#   "0", "4"   → explicit chip number
#   "gpiochip0", "gpiochip4" → chip name
#
GPIO_CHIP="auto"

# --- TGIF API ---
TGIF_API="http://tgif.network:5040/api/sessions/update"
TGIF_API_TIMEOUT="10"

# --- ファイルパス ---
MMDVM_CONF="/etc/mmdvmhost"
DMRGATEWAY_CONF="/etc/dmrgateway"
EOF
    chmod 644 "${CONF_FILE}"
fi

# ------------------------------------------------------------------
# 5. systemd ユニット
#    - After= に mmdvmhost と dmrgateway を列挙して boot delay 不要にする
#    - Restart=on-failure (正常停止では再起動しない)
# ------------------------------------------------------------------
echo "⚙️  systemd ユニットを登録..."
cat > /etc/systemd/system/tgifchanger-py.service <<EOF
[Unit]
Description=TGIFChanger-Py Unified Daemon (v${VERSION})
Documentation=https://github.com/ji2tab/TGIFChanger
After=network-online.target mmdvmhost.service dmrgateway.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/tgif_daemon.py
Restart=on-failure
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tgifchanger-py
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tgifchanger-py
systemctl restart tgifchanger-py

echo "=================================================="
echo " ✅ TGIFChanger-Py ${VERSION} インストール完了"
echo "--------------------------------------------------"
echo " ログ確認:    journalctl -u tgifchanger-py -f"
echo " ステータス:  tg_change --status"
echo " 設定確認:    tg_change -c"
echo " 設定ファイル: ${CONF_FILE}"
echo "=================================================="
