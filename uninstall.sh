#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Uninstaller
# Description: Complete removal of services, files, and firewall rules.
# =============================================================================

echo "🗑️  Uninstalling TGIFChanger-Py..."

if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# 1. サービスの停止と無効化
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true

# 2. ファイルの削除
sudo rm -f /etc/systemd/system/tgifchanger-py.service
sudo rm -f /etc/systemd/system/tgifchanger-web.service
sudo rm -f /usr/local/bin/tg_change
sudo rm -rf /opt/tgifchanger-py
# 設定ファイルは残したい場合はここをコメントアウトしてください
sudo rm -f /etc/tgifchanger.conf

# 3. ファイアウォール設定の削除
echo "🛡️  Cleaning up Firewall rules..."
# 現在のルールから削除
sudo iptables -D INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true

# WPSDの永続設定ファイルから削除
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    sudo sed -i '/dport 8080/d' "$FW_FILE"
    echo "   -> Removed from $FW_FILE"
fi

sudo systemctl daemon-reload

echo "=================================================="
echo " ✨ Uninstall Completed Successfully."
echo "=================================================="
