# TGIFChanger (for OpenCCVoice & WPSD)

MMDVM(WPSD/Pi-Star)環境において、TGIFネットワークの運用を自動化・高度化するためのツールセットです。
特に、Arduinoベースの音声ガイダンスシステム **「OpenCCVoice」** との物理連携を想定して設計されています。

## 🌟 主な機能

1. **TGIF Changer (`tg_change`)**
   - DMRGatewayの設定からIDを自動取得し、コマンドラインからTGIFのトークグループを瞬時に切り替えます。
2. **Auto TG Restore (`auto_tg_restore`)**
   - 通信終了から120秒後、自動的に指定のホームTG（デフォルト：TG168）へ復帰。戻し忘れを防止します。
3. **GPIO Bridge (`log_monitor`)**
   - TG1の受信ステータスをリアルタイム監視。受信中はRaspberry PiのGPIO17をHIGH出力し、外部機器へステータスを伝達します。

## 🛠 システムの仕組み

MMDVMHostが書き出すログファイルを `tail -f` でリアルタイム監視し、特定の文字列をトリガーに動作します。
GPIO出力は物理的な信号として、OpenCCVoice（Arduino Nano等）のD11ピン（TM BUSY入力）へ直接接続して使用することを想定しています。

## 📋 接続仕様 (Hardware Connection)

Raspberry PiとArduinoを以下の通り接続してください。

| Raspberry Pi (物理ピン) | Arduino Nano (ピン) | 役割 |
|:---|:---|:---|
| **Pin 11 (GPIO 17)** | **D11** | TG1受信信号 (High: 受信中 / Low: 待機) |
| **Pin 9 (GND)** | **GND** | 共通接地 (Common Ground) |

> **注意**: Raspberry PiのGPIOは3.3Vレベルです。Arduino(5V系)へ入力する場合は、Arduino側を `INPUT` モードで使用してください。

## 🚀 導入手順 (Installation)

Pi-Star / WPSDにSSHでログインし、以下のコマンドを実行してください。

```bash
rpi-rw
curl -L [https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh](https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh) | bash

このスクリプトを実行すると、以下の処理が自動で行われます。

/home/pi-star/scripts/ へのファイル配置

実行権限の付与

Systemdへのサービス登録（OS起動時の自動バックグラウンド実行開始）

⚙️ 管理コマンド
各サービスの状態確認や再起動は以下のコマンドで行います。

状態確認: systemctl status log_monitor / systemctl status auto_tg_restore

ログ確認: journalctl -u log_monitor -f

手動切替: /home/pi-star/scripts/tg_change -44011

📄 ライセンス
GPL v3 (OpenCCVoiceプロジェクトの理念に基づき、オープンソースとして公開します)

👤 作者
Kazuhiko Shinoda (JI2TAB)

Owariasahi City, Aichi, Japan

Manager of Aichi Digital Communication Ham Club (JJ2YYK)
