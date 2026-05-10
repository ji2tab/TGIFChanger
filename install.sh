#!/bin/bash
# =============================================================================
# TGIFChanger-Py Smart Installer
# Version: v2.2.0
# =============================================================================

REPO_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"
INSTALL_DIR="/opt/tgifchanger-py"

echo "🚀 TGIFChanger-Py (v2.2.0) のインストールを開始します..."

# 1. 書き込み可能モードへ変更
if command -v rpi-rw >/dev/null 2>&1; then
    rpi-rw
fi

# 2. 旧サービスの停止と完全削除
echo "🧹 古いバージョンをクリーンアップしています..."
systemctl stop log_monitor auto_tg_restore tgifchanger-py tg_change 2>/dev/null
systemctl disable log_monitor auto_tg_restore tg_change 2>/dev/null
rm -f /etc/systemd/system/log_monitor.service /etc/systemd/system/auto_tg_restore.service
rm -rf /opt/tgifchanger

# 3. ディレクトリ作成とファイルのダウンロード
echo "📦 最新のファイルをダウンロードしています..."
mkdir -p "$INSTALL_DIR"
curl -sL "${REPO_URL}/tgif_daemon.py" -o "${INSTALL_DIR}/tgif_daemon.py"
curl -sL "${REPO_URL}/tg_change.py" -o "${INSTALL_DIR}/tg_change.py"

# 4. 権限設定とシンボリックリンク作成
chmod +x ${INSTALL_DIR}/*.py
ln -sf "${INSTALL_DIR}/tg_change.py" /usr/local/bin/tg_change

# 5. systemd サービスの登録 (20秒の遅延起動付き)
echo "⚙️ systemd サービスを構成しています..."
cat <<EOF > /etc/systemd/system/tgifchanger-py.service
[Unit]
Description=TGIFChanger-Py Unified Daemon
After=mmdvmhost.service dmrgateway.service network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/tgif_daemon.py
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 6. サービスの有効化と起動
systemctl daemon-reload
systemctl enable tgifchanger-py
systemctl start tgifchanger-py

# 7. 読み取り専用モードへ戻す
if command -v rpi-ro >/dev/null 2>&1; then
    rpi-ro
fi

echo "✅ インストールが完了しました！"
echo "👉 動作確認: journalctl -u tgifchanger-py -f"
echo "👉 CLIツール: tg_change -h"
