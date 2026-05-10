#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Focused Uninstaller (v2.8.0)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: Minimalist removal script for the focused daemon system.
# =============================================================================

echo "=================================================="
echo " 🗑️  TGIFChanger-Py (Focused) を削除します"
echo "=================================================="

# Pi-Starを書き込み可能モードへ
if command -v rpi-rw >/dev/null 2>&1; then
    sudo rpi-rw
fi

# 1. サービスの停止と無効化
echo "🛑 サービスを停止中..."
sudo systemctl stop tgifchanger-py 2>/dev/null || true
sudo systemctl disable tgifchanger-py 2>/dev/null || true

# 2. ユニットファイルの物理削除
echo "📄 サービス定義ファイルを削除中..."
sudo rm -f /etc/systemd/system/tgifchanger-py.service
sudo systemctl daemon-reload

# 3. 実行ファイル・リンク・ディレクトリの削除
echo "📁 プログラム本体を削除中..."
sudo rm -f /usr/local/bin/tg_change
sudo rm -rf /opt/tgifchanger-py

# 4. 設定ファイルの扱い
echo "📝 設定ファイル (/etc/tgifchanger.conf) は保持しました。"
echo "   (これも消す場合は sudo rm /etc/tgifchanger.conf を実行してください)"

echo "=================================================="
echo " ✨ 削除完了。システムはクリーンになりました。"
echo "=================================================="
