#!/bin/bash
# =============================================================================
# TGIFChanger - Automated Uninstaller
# 
# File:        uninstall.sh
# Version:     v1.2.4
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Completely removes TGIFChanger, systemd services, and user
#              configurations to restore the system to a clean state.
# License:     GPL v3
# =============================================================================

set -e

INSTALL_DIR="/opt/tgifchanger"
BIN_DIR="/usr/local/bin"
CONF_DIR="/etc"
SYSTEMD_DIR="/etc/systemd/system"

echo "=================================================="
echo " TGIFChanger Uninstaller"
echo "=================================================="
echo "⚠️ 警告: この操作は TGIFChanger のすべてのプログラムと"
echo "         設定ファイル (tgifchanger.conf) を完全に削除します。"
echo "         5秒後にアンインストールを開始します... (キャンセルは Ctrl+C)"
sleep 5

# --- ファイルシステム書き込み有効化 (Pi-Star のみ) ---------------------------
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 ファイルシステムを書き込みモードへ変更中..."
    sudo rpi-rw
fi

# --- サービスの停止と自動起動の解除 ----------------------------------------
echo "🛑 サービスと関連プロセスを強制停止しています..."
for svc in log_monitor auto_tg_restore; do
    if systemctl is-active --quiet "$svc" 2>/dev/null || systemctl is-failed --quiet "$svc" 2>/dev/null; then
        sudo systemctl stop "$svc" || true
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        sudo systemctl disable "$svc" || true
    fi
    # ゾンビプロセス対策の念押し
    sudo killall "${svc}.sh" 2>/dev/null || true
done
sudo rm -f /run/auto_tg_restore.pid

# --- systemd サービスファイルの削除 ----------------------------------------
echo "🗑️ systemd サービス定義を削除しています..."
sudo rm -f "${SYSTEMD_DIR}/log_monitor.service"
sudo rm -f "${SYSTEMD_DIR}/auto_tg_restore.service"
sudo systemctl daemon-reload

# --- プログラム本体とコマンドリンクの削除 ----------------------------------
echo "🗑️ プログラムディレクトリとコマンドリンクを削除しています..."
if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
fi
sudo rm -f "${BIN_DIR}/tg_change"

# --- 設定ファイルの削除 ----------------------------------------------------
echo "🗑️ 設定ファイルを削除しています..."
sudo rm -f "${CONF_DIR}/tgifchanger.conf"
sudo rm -f "${CONF_DIR}/tgifchanger.conf.dist"

echo "=================================================="
echo " ✅ Uninstallation Completed Successfully!"
echo "--------------------------------------------------"
echo " システムは完全にクリーンな状態に戻りました。"
echo " 再度インストールを行う場合は以下のコマンドを実行してください："
echo " curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash"
echo "=================================================="
