# TGIFChanger 技術仕様書

- **Version:** proto-1.0.0
- **Author:** Kazuhiko Shinoda (JI2TAB)
- **License:** GPL v3

> 本仕様書は、TGIFChanger proto-1.0.0 の設計・実装・保守・再実装を目的とした正式技術仕様書である。

---

## 目次

- 0. はじめに
- 1. システムアーキテクチャ
- 2. ソフトウェア詳細仕様
- 3. 設定ファイル仕様
- 4. 物理・電気仕様
- 5. Reliability / systemd 設計
- 6. GPIO 制御トラブルと対策
- 7. メンテナンスとデバッグ
- 8. 動作環境
- 付録A. proto-1.0.0 主な改訂点
- 付録B. 著作・ライセンス

---

## 改訂履歴

| 版 | 内容 |
|---|---|
| 1.0 (初版) | オリジナル版仕様書（sysfs / TG1固定 / Restart=always / /home/pi-star/scripts）|
| proto-1.0.0 | プロト版として全面改訂。共通設定ファイル導入、libgpiod対応、ログファイル日付追従、PID追跡改善、WATCH_TG設定可変化、配置先 /opt/tgifchanger/ 等。|

---

## 0. はじめに

本書は、MMDVM（Pi-Star / WPSD）環境向けトークグループ自動化ツール「TGIFChanger」の
proto-1.0.0 における技術仕様を定義する。

本ツールセットは、Arduino ベース音声ガイダンスシステム「OpenCCVoice」との
物理的連携を前提として設計されている。

Raspberry Pi GPIO 出力を OpenCCVoice 側 TM BUSY 入力へ接続することで、
DMR 受信状態に応じた音声ガイダンス制御を、
ソフトウェアプロトコルを介さず物理層で確実に実現する。

本仕様書はオリジナル版仕様書を全面改訂したものであり、
proto-1.0.0 で導入された各種改良事項を絶対仕様として記述する。

---

## 1. システムアーキテクチャ

本システムは、MMDVMHost が生成するログファイルをイベントソースとし、
Bash スクリプト群を systemd 配下のデーモンとして動作させる
軽量イベント駆動型アーキテクチャを採用する。

OS の標準機能（systemd, sysfs, libgpiod）を最大限活用し、
独自のメッセージブローカーや常駐データベースを必要としない。

### 1.1 システム構成図

```
 +-------------+
 | DMR Radio   |  RF
 | Network     |~~~~~~+
 +-------------+      |
                      v
+========================================================================+
|  Raspberry Pi (Pi-Star / WPSD)                                         |
|                                                                        |
|   +-----------+   writes    +----------------------+    +------------+ |
|   | MMDVMHost |------------>| /var/log/pi-star/    |<---| DMRGateway | |
|   +-----------+             | MMDVM-YYYY-MM-DD.log |    +------------+ |
|         ^                   +----------+-----------+          ^        |
|         |                       |     |                       |        |
|         | DMR routing           |     | tail -F               |        |
|         |                tail -F|     |                       | control|
|         |                       v     v                       |        |
|   +- - -|- - - - - - - - - - - - - - - - - - - - - - - - - - -|- - -+  |
|   |  TGIFChanger Suite (/opt/tgifchanger/)                    |     |  |
|   |                                                           |     |  |
|   |   +-----------------+      +---------------+             |     |  |
|   |   | log_monitor     |      | tg_change     |--HTTP GET---+     |  |
|   |   | (systemd unit)  |      | (CLI/internal)|                   |  |
|   |   +--------+--------+      +-------+-------+                   |  |
|   |            | libgpiod              ^                           |  |
|   |            | / sysfs               | invokes                   |  |
|   |            v               +-------+----------+                |  |
|   |   +-----------------+      | auto_tg_restore  |                |  |
|   |   | (see GPIO17     |      | (systemd unit)   |                |  |
|   |   |  below)         |      +------------------+                |  |
|   |   +-----------------+                                          |  |
|   +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - --+  |
|                                                                        |
|   +------------------+                                                 |
|   | /etc/            |---reads---> [log_monitor / auto_tg_restore /    |
|   | tgifchanger.conf |              tg_change]                         |
|   +------------------+                                                 |
|                                                                        |
|   +-------------------+                                                |
|   | GPIO17 (Pin 11)   |==== Signal Wire (3.3V) ===+                    |
|   | 3.3V CMOS         |==== Common GND ============|====+              |
|   | Active High       |                            |    |              |
|   +-------------------+                            |    |              |
+============================================ ====== | == | =============+
                                                     v    v
+=======================================================================+
|  Arduino Nano (OpenCCVoice)                                           |
|                                                                       |
|   +-------------------+                                               |
|   | D11               |                                               |
|   | TM BUSY Input     |                                               |
|   | INPUT mode        |                                               |
|   +---------+---------+                                               |
|             |                                                         |
|             v                                                         |
|   +-----------------------+                                           |
|   | OpenCCVoice Firmware  |                                           |
|   | (ATmega328P / 5V)     |                                           |
|   +----+-----------+------+                                           |
|        |           |                                                  |
|        v           v                                                  |
|   +---------+  +-----------+                                          |
|   |DFPlayer |  |PTT Control|                                          |
|   | Mini    |  |           |                                          |
|   +---------+  +-----------+                                          |
+=======================================================================+

凡例:
  ----> : データフロー（ログ書き込み / tail 監視 / API 呼び出し等）
  - -> : 設定参照、論理依存関係（reads / control）
  ==== : 物理信号（3.3V GPIO 出力 → Arduino 入力）
  ~~~~ : RF 信号
```

### 1.2 データフロー

1. DMR 音声信号を MMDVMHost が受信
2. MMDVMHost がログファイルへ出力
3. `log_monitor` が `tail -F` で監視
4. TG 判定条件一致時に GPIO 制御
5. 通信終了検出時に restore timer 開始
6. タイマー満了後 `tg_change` 実行
7. TGIF API 呼び出しにより TG 復帰

### 1.3 構成要素

| 要素 | 役割 | 実行形態 |
|---|---|---|
| `log_monitor` | MMDVMHost ログを監視し、特定TG受信時に GPIO を制御 | systemd 常駐 |
| `auto_tg_restore` | 通信終了後に自動的にホームTGへ復帰 | systemd 常駐 |
| `tg_change` | TGIF API を呼び出して TG を即時変更 | オンデマンド |
| `/etc/tgifchanger.conf` | 共通設定ファイル | テキスト |

### 1.4 ファイル配置

proto-1.0.0 では FHS に基づき、実行ファイルを `/opt/tgifchanger/` に集約する。
オリジナル版で使用していた `/home/pi-star/scripts/` は使用せず、1製品1ディレクトリとする。

| パス | 用途 |
|---|---|
| `/opt/tgifchanger/` | 本体配置ディレクトリ |
| `/etc/tgifchanger.conf` | 共通設定ファイル |
| `/usr/local/bin/tg_change` | CLI symlink |
| `/etc/systemd/system/` | service unit |

---

## 2. ソフトウェア詳細仕様

### 2.1 log_monitor

MMDVMHost ログをリアルタイムで監視し、指定 TG の受信状態を GPIO 出力へ反映する。

#### 監視対象

| 項目 | 内容 |
|---|---|
| ログディレクトリ | `/var/log/pi-star/` |
| 監視方式 | `tail -F` |
| 入力形式 | `MMDVM-YYYY-MM-DD.log` |

#### 判定条件

| イベント | マッチ条件（AND結合）|
|---|---|
| 受信開始 | `received.*voice header` AND `Slot ${WATCH_SLOT},` AND `to TG ${WATCH_TG}` |
| 受信終了 | `end of voice transmission` AND `Slot ${WATCH_SLOT},` AND `to TG ${WATCH_TG}` |

### 2.2 GPIO backend

proto-1.0.0 では libgpiod を優先採用する。

| backend | 用途 |
|---|---|
| `libgpiod` | Bookworm / WPSD 推奨 |
| `sysfs` | legacy fallback |
| `auto` | 自動判定（デフォルト）|

### 2.3 auto_tg_restore

通信終了イベントを契機として復帰タイマーを開始し、満了時に `tg_change` を呼び出す。

proto-1.0.0 ではプロセス置換を採用し、
`tail | while read` におけるサブシェル PID 問題を根本的に解決した。

```bash
exec 3< <(tail -n 0 -F "$current_file")
while read -r -t 5 line <&3; do
    schedule_restore
done
```

### 2.4 tg_change

TGIF Network API を呼び出してトークグループ変更を行う CLI ツール。

#### 通信仕様

| 項目 | 内容 |
|---|---|
| Method | HTTP GET |
| Endpoint | `http://tgif.network:5040/api/sessions/update` |
| URL パス | `{DMR_ID}/{slot_idx}/{TG}`（slot_idx は 0-indexed）|
| Timeout | 10 sec |
| 成功判定 | HTTP 2xx |

#### DMR ID 取得順序

1. `/etc/dmrgateway` の `[DMR Network 4]` セクションから抽出
2. `/etc/mmdvmhost` の `Id=` 行（フォールバック）
3. 両方失敗時はエラー終了

---

## 3. 設定ファイル仕様

設定は `/etc/tgifchanger.conf` に集約する。Bash の `source` 形式で読み込まれる。

| 変数 | 用途 | デフォルト |
|---|---|---|
| `WATCH_SLOT` | 監視対象スロット | `2` |
| `WATCH_TG` | 監視対象 TG | `1` |
| `RESTORE_DELAY` | 復帰待機秒数 | `120` |
| `RESTORE_TG` | 復帰 TG | `168` |
| `RESTORE_SLOT` | 復帰スロット | `2` |
| `GPIO_PIN` | GPIO 番号（BCM）| `17` |
| `GPIO_BACKEND` | backend 選択 | `auto` |
| `GPIO_CHIP` | libgpiod chip 名 | `auto` |
| `LOG_DIR` | ログディレクトリ | `/var/log/pi-star` |

設定変更後はサービス再起動が必要:

```bash
sudo systemctl restart log_monitor auto_tg_restore
```

---

## 4. 物理・電気仕様

### GPIO 接続

| Raspberry Pi | Arduino Nano | 用途 |
|---|---|---|
| GPIO17 (Pin 11) | D11 | TM BUSY |
| GND (Pin 9) | GND | Common Ground |

### 電圧仕様

| 項目 | 内容 |
|---|---|
| GPIO レベル | 3.3V CMOS |
| Arduino HIGH 判定 | 約 2V 以上 |
| 接続方式 | 直結可能 |

> **警告:** Arduino 側から Raspberry Pi GPIO へ 5V を入力してはならない。GPIO 破損の可能性がある。

---

## 5. Reliability / systemd 設計

| Directive | 内容 |
|---|---|
| `Restart=on-failure` | 異常終了時のみ再起動（正常停止では再起動しない）|
| `After=mmdvmhost.service` | MMDVM 起動完了後に開始 |
| `User=root` | GPIO 制御権限 |
| `StandardOutput=journal` | `journalctl` で確認可能 |

- `SIGINT` / `SIGTERM` を `trap` でハンドリングし、終了時に GPIO を LOW へリセットする
- `flock` による多重起動防止を実装

```bash
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 1
fi
```

---

## 6. GPIO 制御トラブルと対策

proto-1.0.0 開発中、Bookworm 系および Raspberry Pi 5 環境において、
GPIO 制御に関する複数の問題が確認された。

### 6.1 発生した症状

- GPIO が変化しない
- `gpioset` 実行後すぐ LOW に戻る
- systemd 実行時のみ動作しない
- Pi4 では動作するが Pi5 で失敗する
- sysfs GPIO が利用不能

### 6.2 原因分析

#### A. sysfs GPIO の非推奨化

Bookworm 系 Linux では `/sys/class/gpio` は legacy 扱いとなり、
libgpiod が正式 GPIO API となった。
systemd 常駐デーモンとして使用すると、export/unexport の競合、
状態残留、再起動後の不整合など、長期運用に耐えない問題が顕在化した。

#### B. Raspberry Pi 5 の gpiochip 変更

```
Pi4 以前 : gpiochip0
Pi5 系   : gpiochip4
```

固定 chip 指定では Pi5 環境で動作しない場合があった。

#### C. libgpiod v2 の保持仕様

libgpiod v2 では単発実行の場合、プロセス終了時に GPIO 状態が解放される。
HIGH を維持するにはプロセスをバックグラウンドで生存させる必要がある。

#### D. libgpiod v1 / v2 の書式差異

| バージョン | 書式 |
|---|---|
| v1 | `gpioset gpiochip0 17=1` |
| v2 | `gpioset -c gpiochip0 17=1` |

#### E. systemd 実行権限

GPIO アクセス権限が実行ユーザーに依存していた。

### 6.3 採用した対策

| 対策 | 内容 |
|---|---|
| backend 自動化 | libgpiod / sysfs fallback |
| gpiochip 自動判定 | `gpiodetect` 利用 |
| v1/v2 自動判別 | `gpioset --version` で判定 |
| root 実行 | systemd `User=root` |
| PID 保持方式 | HIGH 時はバックグラウンドプロセスを保持し続ける |

> **教訓:** GPIO は単なるハード制御ではなく OS 依存のソフト資源である。
> 世代を跨ぐ運用では抽象化レイヤが必須である。

---

## 7. メンテナンスとデバッグ

### ログ確認

```bash
journalctl -u log_monitor -f
journalctl -u auto_tg_restore -f
```

### サービス状態確認

```bash
systemctl status log_monitor
systemctl status auto_tg_restore
```

### GPIO 状態確認

```bash
gpioget -c gpiochip0 17
```

### 手動 TG 切替

```bash
tg_change -168
tg_change -168:2
```

### トラブルシューティング

| 症状 | 確認・対処 |
|---|---|
| GPIO が反応しない | `journalctl -u log_monitor` でバックエンド確認 / `gpiodetect` で chip 確認 |
| TG が復帰しない | `tg_change` を手動実行して API 疎通確認 / DMR ID 取得確認 |
| DMR ID 取得失敗 | `/etc/dmrgateway` の `[DMR Network 4]` に `Id=` 行があるか確認 |
| 二重起動エラー | `sudo rm /run/auto_tg_restore.lock` で古いロックを削除 |

---

## 8. 動作環境

| 項目 | 対応内容 |
|---|---|
| Hardware | Raspberry Pi Zero 2 W / 3 / 4 / 5 |
| OS | Pi-Star V4.2.3（32-bit Bullseye）/ WPSD（64-bit）|
| Bash | 5.0 以上 |
| GPIO | libgpiod 推奨（`apt install gpiod`）|
| MMDVMHost | ログ書式互換性のある全バージョン |

---

## 付録A. proto-1.0.0 主な改訂点

| 旧仕様 | proto-1.0.0 |
|---|---|
| sysfs 固定 | libgpiod 優先 / sysfs フォールバック |
| TG1 固定 | `WATCH_TG` 設定可変 |
| `Restart=always` | `Restart=on-failure` |
| `/home/pi-star/scripts/` | `/opt/tgifchanger/`（FHS 準拠）|
| `tail \| while read`（サブシェル化）| プロセス置換 `< <(...)` で親シェル保持 |
| 多重起動防止なし | `flock` による排他制御 |
| ログファイル切替未対応 | `read -t 5` で定期再評価 |
| `StandardOutput=null` | `StandardOutput=journal` |
| HTTP POST/GET（記述ミス）| HTTP GET（実装と整合）|

---

## 付録B. 著作・ライセンス

**ライセンス:** GPL v3
OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開する。

**著作:** 篠田 一彦 / Kazuhiko Shinoda (JI2TAB)
Owariasahi City, Aichi, Japan
Aichi Digital Communication Ham Club (JJ2YYK)

**Special Thanks:**

- OpenCCVoice Project Contributors
- WPSD Developers
- Pi-Star Community
- MMDVM Developers
