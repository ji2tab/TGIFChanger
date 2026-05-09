# TGIFChanger (for OpenCCVoice & WPSD/Pi-Star)

**Version v1.2.4 (Ultimate GPIO Engine & Config Priority Edition)**

TGIFChanger は、MMDVM（Pi-Star / WPSD）環境において
TGIF ネットワークの運用を自動化・高度化するためのツールセットです。
Arduino ベースの音声ガイダンスシステム OpenCCVoice との
物理連携を前提に設計されています。

---

## ユースケース: デジピーター運用におけるダイナミック TG の戻し忘れ防止

本システムは、デジピーターとして広域ネットワーク（TGIF 等）に常時接続し、
地域の待機チャンネル（ホーム TG）を維持する装置に最適です。

`DMRGateway` にて `PassAll`（`PassAllPC1=2` / `PassAllTG1=2` など）を有効にすることで、
ユーザーは無線機のダイヤル操作のみで世界中の任意の TG へ一時的（ダイナミック）に接続して
交信を楽しむことができます。
しかし、交信終了後に TG を戻し忘れると、本来の待ち受け TG（ホーム TG）のトラフィックが
ローカルに降りてこなくなるという「戻し忘れ」問題が発生します。

本ツールは、通信終了を自動検知し、指定時間（デフォルト 120 秒）後に自動でホーム TG
（`TGRewrite` で固定した TG）へ強制復帰させます。
これにより、管理者の手を煩わせることなく、デジピーターを常に正しい待機状態に保つことができます。

---

## 主な機能

### TGIF Changer (`tg_change`)

DMRGateway の設定から DMR ID を自動取得し、
コマンドライン操作で TGIF のトークグループを即時に切り替えます。

### Auto TG Restore (`auto_tg_restore`)

通信終了から指定秒数（デフォルト 120 秒）後、自動的にホーム TG へ復帰します。
設定ファイル（`tgifchanger.conf`）での手動指定を最優先とし、
未指定の場合は `/etc/mmdvmhost` から自動で追従します。

### GPIO Bridge (`log_monitor`)

指定 TG の受信状態をリアルタイムで監視します。
受信中は Raspberry Pi の GPIO17 を HIGH 出力し、外部機器へ状態を通知します。
監視対象 TG 番号は設定ファイルを最優先とし、未指定の場合は `/etc/mmdvmhost` から自動取得・追従します。

---

## v1.2.4 の主な変更点

- **Ultimate GPIO Engine 搭載**
    - `pinctrl`、`raspi-gpio`、`libgpiod v2`、`sysfs` から環境に最適な GPIO 制御コマンドを自動判別
    - WPSD や最新の Bookworm 環境でも、エラーなく確実に電圧を保持
- **設定ファイル絶対優先ロジック**
    - `/etc/tgifchanger.conf` に明記された TG 番号を最優先で適用する堅牢な設計に変更
    - WPSD などの複雑な環境でも意図した TG で確実に動作
- **Dynamic Network Tracking**
    - `TGRewrite` 設定から監視 TG および復帰 TG を動的に取得
    - DMR Network 番号（Network 4 など）の変更に影響されない柔軟な運用が可能
- **スマート復帰制御**
    - ホーム TG または監視 TG で通信終了した場合、不要なタイマー起動（復帰処理）を自動抑止
- **長期運用向け改善**
    - `flock` による多重起動の完全防止
    - ログファイルの日付ローテーション（日跨ぎ）への自動追従

---

## システム概要

MMDVMHost が出力するログを `tail -F` によりリアルタイム監視し、
特定のログ行をトリガとして各処理を実行する軽量なイベント駆動型アーキテクチャです。
GPIO 出力は OpenCCVoice 側の TM BUSY 入力（Arduino Nano の D11）へ接続する想定です。

---

## 接続仕様

| Raspberry Pi | Arduino Nano | 役割 |
|---|---|---|
| GPIO17 (Pin 11) | D11 | TG 受信状態 (High: 受信中 / Low: 待機) |
| GND (Pin 9) | GND | 共通接地 (Common Ground) |

> **注意:**
> Raspberry Pi の GPIO は **3.3V 出力** です。
> Arduino 側は必ず **INPUT モード** で使用してください。

---

## 導入手順 (インストール)

Raspberry Pi に SSH ログインし、以下のコマンドを実行してください。

```bash
# Pi-Star の場合のみ必要（WPSD では不要）
rpi-rw

curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash
```

---

## 削除手順 (アンインストール)

システムから TGIFChanger のプログラム本体、サービス、設定ファイルをすべて完全に削除し、
クリーンな状態に戻す場合は以下のコマンドを実行してください。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | bash
```

---

## 設定ファイル

設定は `/etc/tgifchanger.conf` に集約されています。

```bash
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
GPIO_PIN="17"
GPIO_CHIP="0"
RESTORE_DELAY="120"
TGIF_API="http://tgif.network:5040/api/sessions/update"

# WPSD 環境などで特定の TG へ強制固定したい場合は以下のコメントを外して設定します
# WATCH_TG="168"
# RESTORE_TG="168"
```

設定変更後は、以下のコマンドでサービスを再起動して反映させてください。

```bash
sudo systemctl restart log_monitor auto_tg_restore
```

---

## ライセンス

GPL v3
OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開しています。

---

## 作者

**篠田 一彦 / Kazuhiko Shinoda (JI2TAB)**
愛知県尾張旭市 (Owariasahi City, Aichi, Japan)
Aichi Digital Communication Ham Club (JJ2YYK) 管理人

---

## Special Thanks

- OpenCCVoice Project Contributors
- WPSD and Pi-Star Developers
- MMDVM Community
