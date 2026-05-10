#!/bin/bash
# =============================================================================
# TGIFChanger-Py - Focused Installer (v2.8.0)
# =============================================================================
set -e
set -u
VERSION="v2.8.0"
NEW_DIR="/opt/tgifchanger-py"
CONF_FILE="/etc/tgifchanger.conf"
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main"

echo "=== TGIFChanger-Py ${VERSION} Focused Installer ==="
if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

# ディレクトリ準備
sudo mkdir -p "$NEW_DIR"

# 必要な2ファイルのみ取得 (Web関連は取得しない)
for f in tgif_daemon.py tg_change.py; do
    echo "📥 Downloading ${f}..."
    sudo curl -H 'Cache-Control: no-cache' -fsSL -o "${NEW_DIR}/${f}" "${RAW_URL}/${f}"
    sudo chmod +x "${NEW_DIR}/${f}"
done

# CLIツールのリンク作成
sudo ln -sf "${NEW_DIR}/tg_change.py" /usr/local/bin/tg_change

# デーモンサービスの登録 (Webサービスは登録しない)
sudo tee /etc/systemd/system/tgifchanger-py.service >/dev/null <<EOF
[Unit]
Description=TGIFChanger-Py Focused Daemon
After=mmdvmhost.service dmrgateway.service
[Service]
ExecStart=/usr/bin/python3 -u ${NEW_DIR}/tgif_daemon.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tgifchanger-py
sudo systemctl start tgifchanger-py

echo "=================================================="
echo " ✅ 導入完了！ (一点集中モード)"
echo " 📋 ログ確認: journalctl -u tgifchanger-py -f"
echo "=================================================="
