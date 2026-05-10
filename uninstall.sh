#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Professional Uninstaller (v2.6.4)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: This script performs a safe and complete removal of the 
#              TGIFChanger-Py suite, reverting all system changes, 
#              firewall rules, and cleaning up service definitions.
# =============================================================================

# --- エラーハンドリング設定 ---
set -u  # 未定義変数の参照をエラーにする

echo "=================================================="
echo "  🗑️  TGIFChanger-Py 完全削除プロセスを開始します"
echo "=================================================="

# 0. 実行権限の確認 (Root必須)
if [[ $EUID -ne 0 ]]; then
   echo "❌ このスクリプトは sudo または root 権限で実行してください。"
   exit 1
fi

# 1. WPSD/Pi-Star を書き込み可能(RW)モードへ移行
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 システムを書き込み可能(RW)モードに設定しています..."
    rpi-rw
fi

# 2. サービスの停止と自動起動の解除
echo "🛑 実行中のサービスを停止しています..."
SERVICES=("tgifchanger-py" "tgifchanger-web")

for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
        echo "   -> ${svc} を停止中..."
        systemctl stop "$svc" 2>/dev/null || true
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        echo "   -> ${svc} の自動起動を解除中..."
        systemctl disable "$svc" 2>/dev/null || true
    fi
done

# 3. ユニットファイルの削除
echo "📄 システム定義ファイルを削除しています..."
UNIT_FILES=("/etc/systemd/system/tgifchanger-py.service" "/etc/systemd/system/tgifchanger-web.service")

for file in "${UNIT_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   -> 削除: ${file}"
        rm -f "$file"
    fi
done

echo "🔄 システムマネージャーの設定をリロード中..."
systemctl daemon-reload

# 4. 実行ファイル、シンボリックリンク、ソースの削除
echo "📁 プログラム本体と関連ファイルを削除しています..."

# CLIツールのリンク削除
if [ -L "/usr/local/bin/tg_change" ]; then
    echo "   -> リンク削除: /usr/local/bin/tg_change"
    rm -f "/usr/local/bin/tg_change"
fi

# インストールディレクトリの削除
if [ -d "/opt/tgifchanger-py" ]; then
    echo "   -> ディレクトリ削除: /opt/tgifchanger-py"
    rm -rf "/opt/tgifchanger-py"
fi

# 一時ファイル(FIFO)の削除
if [ -p "/run/tgifchanger.cmd" ]; then
    echo "   -> 一時ファイル削除: /run/tgifchanger.cmd"
    rm -f "/run/tgifchanger.cmd"
fi

# 5. ファイアウォール設定の復元 (Port 8080)
echo "🛡️  ファイアウォール設定を復元しています..."

# 現在のメモリ上のルールから削除
if iptables -L INPUT -n | grep -q "dpt:8080"; then
    echo "   -> iptables ルールを削除中..."
    iptables -D INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
fi

# 永続化ファイル(WPSD専用)からの削除
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    if grep -q "dport 8080" "$FW_FILE"; then
        echo "   -> ${FW_FILE} から定義を削除中..."
        # 8080番に関する行を物理的に削除
        sed -i '/dport 8080/d' "$FW_FILE"
    fi
fi

# 6. 設定ファイルの取り扱い
# ※ ユーザーの資産(設定)であるため、慎重に確認
CONF_FILE="/etc/tgifchanger.conf"
if [ -f "$CONF_FILE" ]; then
    echo "📝 設定ファイル(${CONF_FILE})は保持しました。"
    echo "   (完全に削除する場合は sudo rm ${CONF_FILE} を手動で実行してください)"
fi

echo "=================================================="
echo "  ✨ アンインストールが正常に完了しました。"
echo "  システムは元のクリーンな状態に戻りました。"
echo "=================================================="
