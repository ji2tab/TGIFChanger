#!/bin/bash

echo "========================================================="
echo " 古いTGIFChanger (Bash版) アンインストールスクリプト"
echo "========================================================="

# 1. システムを書き込み可能モードに変更
echo "▶ [1/4] ファイルシステムを書き込み可能(rpi-rw)に変更しています..."
sudo rpi-rw

# 2. サービスの停止と無効化
echo "▶ [2/4] 古いサービスとプロセスを停止・無効化しています..."
sudo systemctl stop log_monitor.service 2>/dev/null
sudo systemctl stop auto_tg_restore.service 2>/dev/null

sudo systemctl disable log_monitor.service 2>/dev/null
sudo systemctl disable auto_tg_restore.service 2>/dev/null

# プロセスの強制終了とPIDファイルの削除
sudo killall log_monitor.sh 2>/dev/null
sudo killall auto_tg_restore.sh 2>/dev/null
sudo rm -f /run/auto_tg_restore.pid

# 3. サービス定義ファイルの削除とsystemdの再読み込み
echo "▶ [3/4] systemd サービス定義を削除しています..."
sudo rm -f /etc/systemd/system/log_monitor.service
sudo rm -f /etc/systemd/system/auto_tg_restore.service
sudo systemctl daemon-reload

# 4. プログラムおよび設定ファイルの削除
echo "▶ [4/4] 関連ファイルおよび設定を削除しています..."
sudo rm -rf /opt/tgifchanger
sudo rm -f /usr/local/bin/tg_change
sudo rm -f /etc/tgifchanger.conf
sudo rm -f /etc/tgifchanger.conf.dist

echo "========================================================="
echo " アンインストールが完了しました。"
echo " 必要に応じて 'sudo rpi-ro' を実行し、読み取り専用に戻してください。"
echo "========================================================="
