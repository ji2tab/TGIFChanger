#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Professional Installer (v2.9.5)
# =============================================================================
set -e
NEW_DIR="/opt/tgifchanger-py"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=== TGIFChanger-Py v2.9.5 Professional Installer ==="

# 1. Python3 の存在チェック (デグレ防止)
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ エラー: python3 が見つかりません。インストールしてください。"
    exit 1
fi

# 2. 書き込み権限の確保
if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# 3. 既存サービスの停止
sudo systemctl stop tgifchanger-py 2>/dev/null || true
sudo mkdir -p "$NEW_DIR"

# 4. 最新スクリプトの取得
for f in tgif_daemon.py tg_change.py; do
    echo "📥 Downloading $f..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done

# 5. シンボリックリンクの作成 (CLIツールとして利用可能に)
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# 6. サービス定義 (20秒待機 + 自動再起動を完備)
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Classic Daemon
After=mmdvmhost.service dmrgateway.service
[Service]
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
RestartSec=10
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py
sudo systemctl start tgifchanger-py

echo "=================================================="
echo " ✅ 導入完了: 全機能が正常にインストールされました"
echo " 📋 ログ確認: journalctl -u tgifchanger-py -f"
echo "=================================================="
