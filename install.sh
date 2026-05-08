# 1. 書き込みモードに変更
rpi-rw

# 2. 作業ディレクトリへ移動（なければ作成）
INSTALL_DIR="/home/pi-star/scripts"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 3. GitHubから最新のファイルを一括取得
echo "📥 Downloading files from GitHub..."
RAW_URL="https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/TGIFChenger"
curl -s -L -O "${RAW_URL}/tg_change"
curl -s -L -O "${RAW_URL}/auto_tg_restore"
curl -s -L -O "${RAW_URL}/log_monitor"

# 4. 実行権限の付与
chmod +x tg_change auto_tg_restore log_monitor

# 5. Systemd サービスファイルの作成 (log_monitor 用)
echo "⚙️  Registering log_monitor service..."
sudo bash -c "cat << EOF > /etc/systemd/system/log_monitor.service
[Unit]
Description=MMDVM to GPIO Bridge Service
After=mmdvmhost.service

[Service]
ExecStart=${INSTALL_DIR}/log_monitor
Restart=always
User=root
StandardOutput=null

[Install]
WantedBy=multi-user.target
EOF"

# 6. Systemd サービスファイルの作成 (auto_tg_restore 用)
echo "⚙️  Registering auto_tg_restore service..."
sudo bash -c "cat << EOF > /etc/systemd/system/auto_tg_restore.service
[Unit]
Description=Auto TG Restore Service
After=mmdvmhost.service

[Service]
ExecStart=${INSTALL_DIR}/auto_tg_restore
Restart=always
User=root
StandardOutput=null

[Install]
WantedBy=multi-user.target
EOF"

# 7. サービスの有効化と起動
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable log_monitor.service
sudo systemctl enable auto_tg_restore.service
sudo systemctl start log_monitor.service
sudo systemctl start auto_tg_restore.service

# 8. 完了報告
echo "------------------------------------------------"
echo "✅ Setup Completed!"
echo "Location: ${INSTALL_DIR}"
echo "Status log_monitor: \$(systemctl is-active log_monitor)"
echo "Status auto_restore: \$(systemctl is-active auto_tg_restore)"
echo "------------------------------------------------"
