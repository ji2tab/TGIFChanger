#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer & Migrator
#
# File:        install.sh
# Version:     v2.3.1
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Changes from v2.3.0:
#   - DMRGateway / MMDVMHost の TGRewrite ルールを自動スキャンし、
#     対話型プロンプトのデフォルト値として動的にサジェストする機能を追加
#   - ベースの復帰デフォルト値を 168 から 4000 (Disconnect) へ変更
# =============================================================================

set -euo pipefail

VERSION="v2.3.1"
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
# ------------------------------------------------------------------
echo "🧹 旧バージョンのクリーンアップ..."
for svc in log_monitor auto_tg_restore tgifchanger-py; do
    systemctl stop    "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
done
rm -f /etc/systemd/system/log_monitor.service \
      /etc/systemd/system/auto_tg_restore.service \
      /etc/systemd/system/tgifchanger-py.service
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

if [[ "${1:-}" == "--from-github" ]] || [[ ! -f "./tgif_daemon.py" ]]; then
    echo "📥 GitHub から最新ファイルを取得..."
    for f in tgif_daemon.py tg_change.py; do
        curl -H 'Cache-Control: no-cache' -fsSL \
             -o "${INSTALL_DIR}/${f}" "${RAW_URL}/${f}"
        chmod +x "${INSTALL_DIR}/${f}"
    done
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
    echo "📂 ローカルファイルからインストール: ${SCRIPT_DIR}"
    for f in tgif_daemon.py tg_change.py; do
        cp "${SCRIPT_DIR}/${f}" "${INSTALL_DIR}/${f}"
        chmod +x "${INSTALL_DIR}/${f}"
    done
fi

ln -sf "${INSTALL_DIR}/tg_change.py" "${SYMLINK}"
echo "🔗 シンボリックリンク: ${SYMLINK}"

# ------------------------------------------------------------------
# 4. TGRewrite ルールの動的抽出 (DMRGateway / MMDVMHost)
# ------------------------------------------------------------------
DETECTED_WATCH="1"
DETECTED_RESTORE="4000"

# ブロック解析で TGRewrite を安全に抽出するawkスクリプト
EXTRACT_AWK='
    /^\[/ {
        if (is_tgif && rewrite != "") { print rewrite; exit }
        is_tgif=0; rewrite=""
    }
    /Address=tgif\.network/ { is_tgif=1 }
    /^TGRewrite[0-9]*=/ && rewrite=="" { split($0,a,"="); rewrite=a[2] }
    END { if (is_tgif && rewrite != "") print rewrite }
'

if [ -f "/etc/dmrgateway" ]; then
    REWRITE_RULE=$(awk "$EXTRACT_AWK" /etc/dmrgateway 2>/dev/null || true)
    if [ -n "$REWRITE_RULE" ]; then
        DETECTED_WATCH=$(echo "$REWRITE_RULE" | cut -d',' -f2 | tr -dc '0-9')
        DETECTED_RESTORE=$(echo "$REWRITE_RULE" | cut -d',' -f4 | tr -dc '0-9')
    fi
elif [ -f "/etc/mmdvmhost" ]; then
    REWRITE_RULE=$(awk "$EXTRACT_AWK" /etc/mmdvmhost 2>/dev/null || true)
    if [ -n "$REWRITE_RULE" ]; then
        DETECTED_WATCH=$(echo "$REWRITE_RULE" | cut -d',' -f2 | tr -dc '0-9')
        DETECTED_RESTORE=$(echo "$REWRITE_RULE" | cut -d',' -f4 | tr -dc '0-9')
    fi
fi

[ -z "$DETECTED_WATCH" ] && DETECTED_WATCH="1"
[ -z "$DETECTED_RESTORE" ] && DETECTED_RESTORE="4000"


# ------------------------------------------------------------------
# 5. 設定ファイル (対話型テンプレート生成)
# ------------------------------------------------------------------
if [[ -f "${CONF_FILE}" ]]; then
    echo "📝 既存 ${CONF_FILE} を保持します。"
    echo "   新オプションの確認用テンプレートを ${CONF_FILE}.new に保存:"
    cat > "${CONF_FILE}.new" <<EOF
# TGIFChanger 設定ファイル (v2.3.1)
#
# Bash KEY=VALUE 形式。両方の環境で読み込み可能:
#   sudo bash install.sh     (インストール)
#   tg_change --status       (ステータス確認)
#   sudo tg_change -w 4000   (設定変更)
#
# 【設定の反映について】
# tg_change コマンドを使って変更した場合は、デーモンに即時反映されます。
# nano 等でこのファイルを直接手動編集した場合のみ、以下のコマンドで再起動してください:
# sudo systemctl restart tgifchanger-py

LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
WATCH_TG="${DETECTED_WATCH}"
RESTORE_TG="${DETECTED_RESTORE}"
RESTORE_DELAY="120"
GPIO_PIN="17"

# --- GPIO Backend (ハイブリッド対応) ---
GPIO_BACKEND="auto"
GPIO_CHIP="auto"

# --- TGIF API ---
TGIF_API="http://tgif.network:5040/api/sessions/update"
TGIF_API_TIMEOUT="10"
EOF
else
    echo "📝 設定ファイルを新規作成します。"
    
    if [ -t 0 ] || [ -c /dev/tty ]; then
        echo ""
        echo "💡 動作設定を入力してください（そのままEnterでシステム抽出の推奨値が採用されます）"
        
        read -p "▶ 監視TG (WATCH_TG) [推奨値: ${DETECTED_WATCH}]: " INPUT_WATCH_TG </dev/tty || true
        WATCH_TG="${INPUT_WATCH_TG:-$DETECTED_WATCH}"

        read -p "▶ 復帰TG (RESTORE_TG) [推奨値: ${DETECTED_RESTORE}]: " INPUT_RESTORE_TG </dev/tty || true
        RESTORE_TG="${INPUT_RESTORE_TG:-$DETECTED_RESTORE}"

        read -p "▶ 復帰までの時間(秒) (RESTORE_DELAY) [デフォルト: 120]: " INPUT_RESTORE_DELAY </dev/tty || true
        RESTORE_DELAY="${INPUT_RESTORE_DELAY:-120}"
        echo ""
    else
        echo "⚠️ 非対話モードで実行されています。自動抽出された推奨値を採用します。"
        WATCH_TG="${DETECTED_WATCH}"
        RESTORE_TG="${DETECTED_RESTORE}"
        RESTORE_DELAY="120"
    fi

    cat > "${CONF_FILE}" <<EOF
# TGIFChanger 設定ファイル (v2.3.1)
#
# Bash KEY=VALUE 形式。両方の環境で読み込み可能:
#   sudo bash install.sh     (インストール)
#   tg_change --status       (ステータス確認)
#   sudo tg_change -w 4000   (設定変更)
#
# 【設定の反映について】
# tg_change コマンドを使って変更した場合は、デーモンに即時反映されます。
# nano 等でこのファイルを直接手動編集した場合のみ、以下のコマンドで再起動してください:
# sudo systemctl restart tgifchanger-py

LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
WATCH_TG="${WATCH_TG}"
RESTORE_TG="${RESTORE_TG}"
RESTORE_DELAY="${RESTORE_DELAY}"
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
EOF
    chmod 644 "${CONF_FILE}"
fi

# ------------------------------------------------------------------
# 6. systemd ユニット
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
