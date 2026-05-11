#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Uninstaller
#
# File:        uninstall.sh
# Version:     v2.3.1
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Description: TGIFChanger のすべてのプログラム、サービス、および
#              設定ファイル (tgifchanger.conf) を完全に削除します。
# =============================================================================

set -euo pipefail

echo "=================================================="
echo " TGIFChanger-Py Uninstaller"
echo "=================================================="
echo "⚠️  警告:"
echo "この操作は TGIFChanger のすべてのプログラムと"
echo "設定ファイル (/etc/tgifchanger.conf) を完全に削除します。"
echo ""

# root権限の確認
if [[ "${EUID}" -ne 0 ]]; then
    echo "❌ root権限で実行してください: sudo bash $0"
    exit 1
fi

echo "⏳ 5秒後にアンインストールを開始します... (キャンセルは Ctrl+C)"
sleep 5

# Pi-Star環境での読み取り専用ファイルシステム完全回避
echo "🔓 ファイルシステムを書き込み可能モードに変更しています..."
if [ -x /usr/local/sbin/rpi-rw ]; then
    /usr/local/sbin/rpi-rw || true
elif command -v rpi-rw >/dev/null 2>&1; then
    rpi-rw || true
else
    mount -o remount,rw / 2>/dev/null || true
    mount -o remount,rw /boot 2>/dev/null || true
fi

# 1. サービスの停止と無効化 (新旧すべてのサービスを対象)
echo "🛑 サービスと関連プロセスを強制停止しています..."
for svc in log_monitor auto_tg_restore tgifchanger-py; do
    systemctl stop    "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
done

# 2. systemd サービスファイルの削除
echo "🗑️  systemd サービス定義を削除しています..."
rm -f /etc/systemd/system/log_monitor.service \
      /etc/systemd/system/auto_tg_restore.service \
      /etc/systemd/system/tgifchanger-py.service

systemctl daemon-reload

# 3. プログラム本体ディレクトリとコマンドの削除
echo "🗑️  プログラム本体とシンボリックリンクを削除しています..."
rm -rf /opt/tgifchanger /opt/tgifchanger-py
rm -f /usr/local/bin/tg_change

# 4. 一時ファイル(ソケット、ロックファイル等)の削除
echo "🗑️  一時ファイルを削除しています..."
rm -f /run/tgifchanger-py.sock \
      /run/tgifchanger-py.lock \
      /run/tgifchanger.cmd \
      /run/auto_tg_restore.pid

# 5. 設定ファイルの完全削除
echo "🗑️  設定ファイルを完全に削除しています..."
rm -f /etc/tgifchanger.conf /etc/tgifchanger.conf.new

echo "=================================================="
echo " ✅ TGIFChanger-Py のアンインストールが完了しました。"
echo "=================================================="
