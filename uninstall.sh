#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Uninstaller (v2.6.2)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Safely removes all components of the TGIFChanger-Py suite
#              and reverts system changes including firewall rules.
# =============================================================================

echo "=================================================="
echo " 🗑️  TGIFChanger-Py アンインストールを開始します"
echo "=================================================="

# WPSD/Pi-Star を書き込み可能モードへ
if command -v rpi-rw >/dev/null 2>&1; then
    sudo rpi-rw
fi

# 1. サービスの停止と無効化
echo "🛑 サービスを停止中..."
sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true

# 2. ユニットファイルの削除
echo "📄 サービス定義を削除中..."
sudo rm -f /etc/systemd/system/tgifchanger-py.service
sudo rm -f /etc/systemd/system/tgifchanger-web.service
sudo systemctl daemon-reload

# 3. 実行ファイルとシンボリックリンクの削除
echo "📁 インストールファイルを削除中..."
sudo rm -f /usr/local/bin/tg_change
sudo rm -rf /opt/tgifchanger-py

# 4. ファイアウォール設定の復元
echo "🛡️  ファイアウォール設定を復元中..."
# 現在のルールから削除
sudo iptables -D INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
# 永続ファイルから削除
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    sudo sed -i '/dport 8080/d' "$FW_FILE"
fi

# 5. 設定ファイルの取り扱い
# ※ 設定ファイルを残したい場合は、以下の行をコメントアウトしてください。
# sudo rm -f /etc/tgifchanger.conf

echo "=================================================="
echo " ✨ アンインストールが正常に完了しました。"
echo "=================================================="
