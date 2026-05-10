#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Smart Installer (v2.6.4)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: This script automates the full deployment of the TGIFChanger-Py 
#              suite on WPSD/Pi-Star systems, including core daemon, 
#              CLI tools, Web UI, and firewall configurations.
# =============================================================================

# --- エラーハンドリング ---
set -e          # コマンドが失敗したら即終了
set -u          # 未定義の変数を使用したらエラー

# --- 定数定義 ---
VERSION="v2.6.4"
NEW_DIR="/opt/tgifchanger-py"
CONF_FILE="/etc/tgifchanger.conf"
BIN_LINK="/usr/local/bin/tg_change"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=================================================="
echo " 🚀 TGIFChanger-Py ${VERSION} Full Installer"
echo "=================================================="

# 0. Root権限チェック
if [[ $EUID -ne 0 ]]; then
   echo "❌ このスクリプトは sudo または root 権限で実行してください。"
   exit 1
fi

# 1. WPSD/Pi-Star を書き込み可能(RW)モードへ移行
if command -v rpi-rw >/dev/null 2>&1; then
    echo "🔓 ディスクを書き込み可能(RW)モードに切り替えています..."
    rpi-rw
fi

# 2. 既存の古いサービスを停止・解除
echo "🛑 既存サービスをクリーンアップしています..."
SERVICES=("tgifchanger-py" "tgifchanger-web")
for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
        systemctl stop "$svc" 2>/dev/null || true
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        systemctl disable "$svc" 2>/dev/null || true
    fi
done

# 3. インストールディレクトリの準備
if [ ! -d "$NEW_DIR" ]; then
    echo "📁 ディレクトリを作成中: ${NEW_DIR}"
    mkdir -p "$NEW_DIR"
fi

# 4. GitHubから最新ソースコードを取得 (キャッシュ回避)
echo "📥 最新のスクリプト群をダウンロードしています..."
FILES=("tgif_daemon.py" "tg_change.py" "web_ui.py")
for f in "${FILES[@]}"; do
    echo "   -> ${f} を取得中..."
    curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    chmod +x "${NEW_DIR}/${f}"
done

# 5. CLIツールのシンボリックリンク作成
echo "🔗 CLIツールへのパスを設定中..."
ln -sf "${NEW_DIR}/tg_change.py" "$BIN_LINK"

# 6. 設定ファイルの配備 (存在しない場合のみデフォルトを取得)
if [ ! -f "$CONF_FILE" ]; then
    echo "⚙️  デフォルト設定ファイルを配備しています..."
    curl -H 'Cache-Control: no-cache' -fsSL -o "$CONF_FILE" "${RAW_URL}/tgifchanger.conf"
fi

# 7. ファイアウォールの開放 (Port 8080)
echo "🛡️  ファイアウォールを構成中 (Port 8080)..."
# メモリ上のルールに即時適用
iptables -I INPUT -p tcp --dport 8080 -j ACCEPT || true

# WPSDの永続化ファイルへの追記
FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    if ! grep -q "dport 8080" "$FW_FILE"; then
        echo "iptables -I INPUT -p tcp --dport 8080 -j ACCEPT" | tee -a "$FW_FILE" > /dev/null
        echo "   -> ${FW_FILE} にルールを追記しました。"
    fi
fi

# 8. Systemd サービスユニットの登録
echo "⚙️  システムサービスを登録しています..."

# --- A. メインデーモン (起動遅延20秒 / ログのリアルタイム出力モード) ---
cat <<EOF | tee /etc/systemd/system/tgifchanger-py.service >/dev/null
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

# --- B. Web UI サービス ---
cat <<EOF | tee /etc/systemd/system/tgifchanger-web.service >/dev/null
[Unit]
Description=TGIFChanger-Py Web UI
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/web_ui.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

# 9. サービスの有効化と起動
echo "🚀 サービスを有効化して起動しています..."
systemctl daemon-reload
systemctl enable tgifchanger-py tgifchanger-web
systemctl start tgifchanger-py tgifchanger-web

echo "=================================================="
echo " ✅ インストールが正常に完了しました！"
echo "--------------------------------------------------"
echo " 🌐 WebダッシュボードURL:"
echo "    http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo " 📋 リアルタイムログ確認コマンド:"
echo "    journalctl -u tgifchanger-py -f"
echo "=================================================="
