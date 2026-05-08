# TGIFChanger (for OpenCCVoice & WPSD)

**Prototype Version `proto-1.0.0`**

MMDVM (Pi-Star / WPSD) 環境において、TGIFネットワークの運用を自動化・高度化するためのツールセットです。
特に、Arduinoベースの音声ガイダンスシステム **「OpenCCVoice」** との物理連携を想定して設計されています。

---

## 🌟 主な機能

### 1. TGIF Changer (`tg_change`)

DMRGateway の設定から DMR ID を自動取得し、コマンドラインから TGIF のトークグループを瞬時に切り替えます。

### 2. Auto TG Restore (`auto_tg_restore`)

通信終了から指定秒数（デフォルト120秒）後、自動的に指定のホーム TG（デフォルト：TG168）へ復帰させます。戻し忘れを防止します。

### 3. GPIO Bridge (`log_monitor`)

指定 TG（デフォルト：TG1）の受信ステータスをリアルタイム監視。受信中は Raspberry Pi の GPIO17 を HIGH 出力し、外部機器へステータスを伝達します。

---

## 🆕 プロト版 (proto-1.0.0) での主な変更点

旧版から以下の改良が入っています:

- **共通設定ファイル `/etc/tgifchanger.conf`** を導入。3スクリプトで共有
- **`auto_tg_restore`**: プロセス置換 (`< <(...)`) により `while` ループを親シェルに保持し、復帰タイマーの PID 追跡を確実化
- **多重起動防止**: `flock` による排他制御
- **ログファイル日付切替に追従**: 中長期起動でも `MMDVM-YYYY-MM-DD.log` の切替を自動検出
- **GPIO制御**: `libgpiod` (`gpioset`) を優先採用、未インストール環境では `sysfs` に自動フォールバック
- **WATCH_TG 設定可変**: `log_monitor` で監視する TG を `/etc/tgifchanger.conf` から変更可能（旧版は TG1 固定）
- **systemd ユニット改善**: `Restart=on-failure` / `journal` 出力により可観測性向上

---

## 🛠 システムの仕組み

MMDVMHost が書き出すログファイルを `tail -F` でリアルタイム監視し、特定の文字列をトリガーに動作します。

GPIO 出力は物理的な信号として、OpenCCVoice（Arduino Nano 等）の D11 ピン（TM BUSY 入力）へ直接接続して使用することを想定しています。

---

## 📋 接続仕様 (Hardware Connection)

Raspberry Pi と Arduino を以下の通り接続してください。

| Raspberry Pi (物理ピン) | Arduino Nano (ピン) | 役割 |
|:---:|:---:|:---:|
| **Pin 11 (GPIO17)** | **D11** | TG受信信号 (High: 受信中 / Low: 待機) |
| **Pin 9 (GND)** | **GND** | 共通接地 (Common Ground) |

> ⚠️ **注意**
> Raspberry Pi の GPIO は 3.3V レベルです。Arduino（5V系）へ入力する場合は、Arduino 側を `INPUT` モードで使用してください。

---

## 🚀 導入手順 (Installation)

Pi-Star / WPSD に SSH でログインし、以下のコマンドを実行してください。

```bash
rpi-rw   # Pi-Star のみ。WPSDは不要
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash
```

このスクリプトを実行すると、以下の処理が自動で行われます。

1. `/home/pi-star/scripts/` への各スクリプト配置
2. `/etc/tgifchanger.conf` の配置（既存ファイルは保護、新版は `.dist` として保存）
3. 実行権限の付与
4. systemd へのサービス登録（OS起動時の自動バックグラウンド実行開始）

---

## ⚙️ 設定ファイル

すべての設定は `/etc/tgifchanger.conf` に集約されています:

```bash
# 監視スロット (1 or 2)
WATCH_SLOT="2"

# 自動復帰
RESTORE_DELAY="120"      # 通信終了から復帰までの秒数
RESTORE_TG="168"         # 復帰先 TG
RESTORE_SLOT="2"

# GPIO ブリッジ
WATCH_TG="1"             # 受信検出対象 TG
GPIO_PIN="17"            # 出力ピン (BCM 番号)
GPIO_BACKEND="auto"      # auto / libgpiod / sysfs
GPIO_CHIP="auto"         # libgpiod 使用時の chip 名
```

設定変更後はサービス再起動が必要です:

```bash
sudo systemctl restart log_monitor auto_tg_restore
```

---

## ⚙️ 管理コマンド

### 状態確認

```bash
systemctl status log_monitor
systemctl status auto_tg_restore
```

### ログ確認

```bash
journalctl -u log_monitor -f
journalctl -u auto_tg_restore -f
```

### 手動 TG 切替

```bash
/home/pi-star/scripts/tg_change -44011        # スロット1 を TG44011 に
/home/pi-star/scripts/tg_change -168:2        # スロット2 を TG168 に
```

### サービス再起動

```bash
sudo systemctl restart log_monitor auto_tg_restore
```

---

## 📁 インストールされる主なファイル

```text
/home/pi-star/scripts/tg_change
/home/pi-star/scripts/auto_tg_restore
/home/pi-star/scripts/log_monitor

/etc/tgifchanger.conf

/etc/systemd/system/log_monitor.service
/etc/systemd/system/auto_tg_restore.service
```

---

## 🔧 動作概要

### tg_change

TGIF API へリクエストを送り、トークグループを即時変更します。

```bash
/home/pi-star/scripts/tg_change -44011
```

DMR ID は `/etc/dmrgateway` の `[DMR Network 4]` セクションから自動取得し、見つからない場合は `/etc/mmdvmhost` から取得します。

### auto_tg_restore

最後の通信終了から `RESTORE_DELAY` 秒経過すると、自動的にホーム TG へ戻します。

- **Default Home TG**: `168`
- **Default Wait Time**: `120秒`

### log_monitor

MMDVMHost ログを監視し、`WATCH_TG` 受信中に `GPIO_PIN` を HIGH 出力します。

| 状態 | GPIO 出力 |
| --- | --- |
| `WATCH_TG` 受信中 | **HIGH** |
| 待機中 | **LOW** |

---

## 🧩 OpenCCVoice 連携

本システムは、OpenCCVoice 側の TM BUSY 入力を利用し、TG 受信状態に応じた音声ガイダンス制御を行うために設計されています。

- TG 受信中は CW 送出禁止
- ガイダンス再生抑止
- 通信中アナウンス制御

などの高度な連携が可能です。

---

## 🖥 対応環境

- Raspberry Pi シリーズ（Zero 2 W / 3 / 4 / 5）
- Pi-Star V4.2.3 (32-bit Bullseye)
- WPSD (64-bit)
- MMDVMHost / DMRGateway

GPIO制御は Bookworm 以降の `libgpiod` を優先利用し、Bullseye の `sysfs` にも自動フォールバックします。

---

## 📄 ライセンス

GPL v3

(OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開します)

---

## 👤 作者

### 篠田 一彦 / Kazuhiko Shinoda (JI2TAB)

- Owariasahi City, Aichi, Japan
- Manager of Aichi Digital Communication Ham Club (JJ2YYK)

---

## 🤝 Special Thanks

- OpenCCVoice Project Contributors
- WPSD Developers
- Pi-Star Community
- MMDVM Developers
