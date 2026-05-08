# TGIFChanger 技術仕様書

- **Version:** proto-1.0.0
- **Author:** Kazuhiko Shinoda (JI2TAB)
- **License:** GPL v3

---

## 改訂履歴

| 版 | 内容 |
|---|---|
| 1.0 (初版) | オリジナル版仕様書 (sysfs / TG1固定 / Restart=always / `/home/pi-star/scripts`) |
| proto-1.0.0 | プロト版として全面改訂。共通設定ファイル導入、libgpiod対応、ログファイル日付追従、PID追跡改善、WATCH_TG設定可変化、配置先 `/opt/tgifchanger/` 等。 |

---

## 0. はじめに

本書は、MMDVM (Pi-Star / WPSD) 環境向けトークグループ自動化ツール「TGIFChanger」のプロト版 (proto-1.0.0) における技術仕様を定める。

本ツールセットは、Arduinoベースの音声ガイダンスシステム「OpenCCVoice」との物理的な連携を前提として設計されている。Raspberry Pi の GPIO 出力を OpenCCVoice 側の TM BUSY 入力に直結することにより、DMR 受信状態に応じた音声ガイダンス制御を、ソフトウェアプロトコルを介さず物理層で確実に実現することを目的とする。

本仕様書はオリジナル版仕様書を全面改訂したものであり、proto-1.0.0 で導入された各種改良事項を絶対仕様として記述する。

---

## 1. システムアーキテクチャ

本システムは、MMDVMHost が生成するログファイルをイベントソースとし、Bash スクリプト群が systemd 配下のデーモンとして動作する軽量なイベント駆動型アーキテクチャを採用する。OS の標準機能 (systemd, sysfs, libgpiod) を最大限活用し、独自のメッセージブローカーや常駐 DB を必要としない。

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
|         |                       |     |                       |       |
|         | DMR routing           |     | tail -F               |       |
|         |                tail -F|     |                       |control|
|         |                       v     v                       |       |
|   +- - -|- - - - - - - - - - - - - - - - - - - - - - - - - - -|- - +  |
|   |  TGIFChanger Suite (/opt/tgifchanger/)                    |    |  |
|   |                                                           |    |  |
|   |   +-----------------+      +---------------+              |    |  |
|   |   | log_monitor     |      | tg_change     |--HTTP GET----+    |  |
|   |   | (systemd unit)  |      | (CLI/internal)|                   |  |
|   |   +--------+--------+      +-------+-------+                   |  |
|   |            | libgpiod              ^                           |  |
|   |            | / sysfs                |  invokes                 |  |
|   |            v                +-------+----------+               |  |
|   |   +-----------------+       | auto_tg_restore  |               |  |
|   |   | (see GPIO17     |       | (systemd unit)   |               |  |
|   |   |  below)         |       +------------------+               |  |
|   |   +-----------------+                                          |  |
|   +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +  |
|                                                                        |
|   +------------------+                                                 |
|   | /etc/            |---reads--> [log_monitor / auto_tg_restore /     |
|   | tgifchanger.conf |             tg_change ]                         |
|   +------------------+                                                 |
|                                                                        |
|   +-------------------+                                                |
|   | /usr/local/bin/   |---symlink--> /opt/tgifchanger/tg_change        |
|   | tg_change         |                                                |
|   +-------------------+                                                |
|                                                                        |
|   +-------------------+                                                |
|   | GPIO17 (Pin 11)   |==== Signal Wire (3.3V) ===+                    |
|   | 3.3V CMOS         |==== Common GND ===========|====+               |
|   | Active High       |                           |    |               |
|   +-------------------+                           |    |               |
+============================================ ===== | == | ==============+
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
  ----> : データフロー (ログ書き込み / tail 監視 / API 呼び出し等)
  - -> : 設定参照、論理依存関係 (reads / control)
  ==== : 物理信号 (3.3V GPIO 出力 → Arduino 入力)
  ~~~~ : RF 信号
```

### 1.2 構成要素

| 要素 | 役割 | 実行形態 |
|---|---|---|
| `log_monitor` | MMDVMHost ログを監視し、特定TG受信時に GPIO を制御 | systemd 常駐 |
| `auto_tg_restore` | 通信終了から一定時間後に自動的にホームTGへ復帰 | systemd 常駐 |
| `tg_change` | TGIF API を呼び出してTGを即時変更 (CLI) | オンデマンド実行 |
| `/etc/tgifchanger.conf` | 3スクリプト共通の設定ファイル | テキストファイル |

### 1.3 ファイル配置 (FHS 準拠)

proto-1.0.0 では FHS (Filesystem Hierarchy Standard) に基づき、以下の配置を採用する。

| パス | 役割 |
|---|---|
| `/opt/tgifchanger/` | 実行ファイル本体 (自己完結型サードパーティパッケージとして配置) |
| `/etc/tgifchanger.conf` | 設定ファイル |
| `/usr/local/bin/tg_change` | `tg_change` への symlink (PATH 上から直接実行可能にするため) |
| `/etc/systemd/system/*.service` | systemd ユニット定義 |

> オリジナル版では `/home/pi-star/scripts/` に配置していたが、Pi-Star 本体スクリプト群との混在を避けるため、proto-1.0.0 では `/opt/tgifchanger/` (1製品1ディレクトリ) に変更した。アンインストール時は `sudo rm -rf /opt/tgifchanger` で完結する。

### 1.4 データフロー

- RF 経由で受信した DMR 信号は MMDVMHost によりログとして記録される (`/var/log/pi-star/MMDVM-YYYY-MM-DD.log`)。
- `log_monitor` および `auto_tg_restore` は当該ログを `tail -F` でリアルタイム追跡し、特定文字列パターンをイベントとして検出する。
- `log_monitor` はイベント検出時に GPIO 出力を制御し、OpenCCVoice 側の TM BUSY 入力に通知する。
- `auto_tg_restore` はイベント検出時にタイマーを開始し、所定時間経過後に `tg_change` を起動して TGIF API へリクエストを送出する。
- `tg_change` は手動 CLI 実行も可能であり、運用者の即時操作にも対応する。

### 1.5 設計原則

- **軽量性**: 追加デーモン不要。Bash + 標準UNIXユーティリティで完結。
- **耐障害性**: systemd の `Restart=on-failure` による自動復旧、`flock` による多重起動防止。
- **可搬性**: Pi-Star (32-bit Bullseye) と WPSD (64-bit) の両環境で動作。
- **可観測性**: 全ログを `journalctl` で参照可能。
- **設定外出し**: 動作パラメータは `/etc/tgifchanger.conf` に集約し、コード変更なしで運用調整可能。
- **FHS 準拠**: 配置先を OS 標準のディレクトリ階層規約に従う。

---

## 2. ソフトウェア詳細仕様

### 2.1 log_monitor (GPIO連動エンジン)

MMDVMHost ログをリアルタイム監視し、指定 TG (デフォルト TG1) の受信状態を Raspberry Pi の GPIO 出力ピンに反映するブリッジデーモン。

#### 2.1.1 監視対象

- ログディレクトリ: `/var/log/pi-star/` (`LOG_DIR` で変更可)
- ログファイル: `MMDVM-YYYY-MM-DD.log` (最新ファイルを自動選択)
- 監視手法: `tail -F` によるファイル末尾の常時追跡。プロセス置換 `< <(...)` を介して親シェルの `read` で読み取る。

#### 2.1.2 判定アルゴリズム

受信開始・終了の判定は MMDVMHost のログ書式に依存する。スロットおよび TG 番号は設定ファイル (`WATCH_SLOT`, `WATCH_TG`) により可変である。

| イベント | マッチ条件 (AND結合) |
|---|---|
| 受信開始 | `received.*voice header` AND `Slot ${WATCH_SLOT},` AND `to TG ${WATCH_TG}` |
| 受信終了 | `end of voice transmission` AND `Slot ${WATCH_SLOT},` AND `to TG ${WATCH_TG}` |

#### 2.1.3 GPIO 制御 (proto-1.0.0 改訂)

GPIO バックエンドは libgpiod (`gpioset`) を優先採用し、未インストール環境では sysfs (`/sys/class/gpio`) に自動フォールバックする。設定ファイルの `GPIO_BACKEND` で明示指定も可能 (`auto` / `libgpiod` / `sysfs`)。

Raspberry Pi 5 では GPIO チップが `gpiochip4` (BCM2712) に変更されているが、`gpiodetect` により自動判別する。

> ⚠️ オリジナル版では sysfs 直書きを「堅牢性」として明記していたが、Bookworm 以降の標準は libgpiod であり、sysfs インターフェースは将来的に廃止予定であるため、proto-1.0.0 では libgpiod 優先とした。

#### 2.1.4 ログファイル日付切替への追従 (proto-1.0.0 新規)

MMDVMHost は日付ごとに新しいログファイル (`MMDVM-YYYY-MM-DD.log`) を生成する。proto-1.0.0 では `read -t 5` によりタイムアウト付き読み取りを行い、定期的に最新ログファイルを再評価して `tail` を再起動する。これにより日跨ぎ運用でもイベントを取りこぼさない。

---

### 2.2 auto_tg_restore (復帰管理タイマー)

通信終了イベントを契機としたタイマー起動と、タイマー満了時のホーム TG 復帰を担うデーモン。

#### 2.2.1 プロセス管理

- PIDファイル: `/run/auto_tg_restore.pid` (`/run` が利用不可なら `/tmp` にフォールバック)
- ロックファイル: `/run/auto_tg_restore.lock` (`flock` による排他制御)

#### 2.2.2 タイマー制御アルゴリズム (proto-1.0.0 改訂)

通信終了イベント発生時の動作:

1. 既存の PID ファイルを参照し、待機中サブシェルが存在する場合は `SIGTERM` で停止する (最大1秒待機後 `SIGKILL`)。
2. 新規にバックグラウンドサブシェルを生成し、`(sleep $RESTORE_DELAY && tg_change -$RESTORE_TG:$RESTORE_SLOT)` を実行する。
3. サブシェルの PID を `$!` で取得し、PID ファイルへ書き出す。

#### 2.2.3 PID追跡問題の解決 (proto-1.0.0 改訂)

オリジナル版では `tail | while read` 構文を採用していたため、`while` ループがサブシェル内で実行され、その中で生成したバックグラウンドプロセスの PID が親シェルから追跡不能となる潜在不具合が存在した。

proto-1.0.0 ではプロセス置換 `< <(...)` を採用し、`tail` プロセスを別途起動して FIFO 経由で行を流し込む方式に変更した。これにより `while` ループ自体が親シェルで実行され、`$!` によるバックグラウンド PID 取得が確実に動作する。

```bash
# proto-1.0.0 採用方式 (一部抜粋)
exec 3< <(tail -n 0 -F "$current_file")
while read -r -t 5 line <&3; do
    # ... 親シェル内で schedule_restore を呼び出し可能
done
```

---

### 2.3 tg_change (APIブリッジ)

TGIF Network の HTTP API を呼び出してトークグループ切替を行う CLI ツール。`/usr/local/bin/tg_change` シンボリックリンク経由で PATH 上から直接実行可能。

#### 2.3.1 DMR ID 自動取得

API リクエスト URL に必要な DMR ID は以下の優先順位で取得する:

1. `/etc/dmrgateway` の `[DMR Network 4]` (TGIF) セクションから `sed -n '/\[DMR Network 4\]/,/^\[/p'` により当該セクションを抽出し、最初の `Id=` 行を取得。
2. 上記で取得失敗時、`/etc/mmdvmhost` の `Id=` を取得 (フォールバック)。
3. 両方失敗時はエラー終了。

#### 2.3.2 通信プロトコル

| 項目 | 内容 |
|---|---|
| メソッド | HTTP GET |
| ベースURL | `http://tgif.network:5040/api/sessions/update` |
| URLパス | `{DMR_ID}/{slot_idx}/{TG}` (slot_idx は 0-indexed) |
| タイムアウト | 10秒 (`TGIF_API_TIMEOUT` で変更可) |
| 成功判定 | HTTP ステータスコード 2xx |

#### 2.3.3 引数仕様

| 書式 | 意味 |
|---|---|
| `tg_change -<TG>` | スロット1 を指定TGに変更 |
| `tg_change -<TG>:<slot>` | 指定スロットを指定TGに変更 |
| `tg_change -h \| --help` | ヘルプ表示 |

---

## 3. 設定ファイル仕様

proto-1.0.0 では3スクリプトの動作パラメータを `/etc/tgifchanger.conf` に集約した。本ファイルは Bash の `source` 形式で読み込まれる。

### 3.1 パラメータ一覧

| パラメータ | デフォルト | 用途 |
|---|---|---|
| `LOG_DIR` | `/var/log/pi-star` | MMDVMHost ログディレクトリ |
| `WATCH_SLOT` | `2` | 監視対象 DMR スロット (1 or 2) |
| `RESTORE_DELAY` | `120` | 通信終了から復帰までの秒数 |
| `RESTORE_TG` | `168` | 復帰先 TG |
| `RESTORE_SLOT` | `2` | 復帰先スロット |
| `WATCH_TG` | `1` | GPIO ブリッジで検出する TG |
| `GPIO_PIN` | `17` | GPIO 出力ピン (BCM 番号) |
| `GPIO_BACKEND` | `auto` | `auto` / `libgpiod` / `sysfs` |
| `GPIO_CHIP` | `auto` | libgpiod 使用時のチップ名 |
| `TGIF_API` | `http://tgif.network:5040/api/sessions/update` | TGIF API エンドポイント |
| `TGIF_API_TIMEOUT` | `10` | API リクエストタイムアウト (秒) |

### 3.2 設定変更時の手順

設定ファイル変更後は、変更が反映されるよう常駐サービスを再起動する必要がある。

```bash
sudo systemctl restart log_monitor auto_tg_restore
```

---

## 4. 物理・電気仕様 (Interface Specification)

### 4.1 Raspberry Pi GPIO 出力

| 項目 | 仕様 |
|---|---|
| ポート | GPIO 17 (BCM) / 物理11番ピン |
| 定格電圧 | 3.3V CMOS |
| 最大電流 (推奨) | 16mA (Raspberry Pi 安全圏内) |
| ロジック | 正論理 (Active High: 受信中 = HIGH) |
| 制御方式 | libgpiod (`gpioset`) 優先 / sysfs フォールバック |

### 4.2 Arduino Nano 入力 (OpenCCVoice 側)

| 項目 | 仕様 |
|---|---|
| ポート | Digital 11 (TM BUSY 入力) |
| 設定 | `pinMode(11, INPUT)` または `INPUT_PULLUP` |
| ロジック | `TMBUSY_ACTIVE_HIGH = true` |
| VCC | 5V (ATmega328P 標準動作電圧) |

### 4.3 配線

| Raspberry Pi (物理ピン) | Arduino Nano (ピン) | 役割 |
|---|---|---|
| Pin 11 (GPIO17) | D11 | TG受信信号 (HIGH:受信中 / LOW:待機) |
| Pin 9 (GND) | GND | 共通接地 (Common Ground) |

> ⚠️ **電圧レベル注意**: Raspberry Pi の GPIO は 3.3V レベルである。Arduino Nano の DC 入力は 5V系であるが、INPUT モードでは 2.0V 以上を HIGH として認識するため、レベル変換器なしで直結可能である。ただし Arduino から Raspberry Pi への 5V 出力は GPIO 破損の可能性があるため絶対に行わないこと。

---

## 5. 運用の安定性向上 (Reliability)

### 5.1 systemd によるサービス管理

`log_monitor` および `auto_tg_restore` は systemd ユニットとして登録され、OS と同期した自律管理が行われる。

| ディレクティブ | 値 | 目的 |
|---|---|---|
| `Type` | `simple` | メインプロセス即時起動 |
| `After` | `mmdvmhost.service` | MMDVM 起動完了後に開始 |
| `Wants` | `mmdvmhost.service` | 弱依存関係を表明 |
| `Restart` | `on-failure` | 異常終了時のみ自動再起動 (proto-1.0.0 改訂) |
| `RestartSec` | `5` | 再起動までの待機時間 (秒) |
| `StandardOutput` | `journal` | `journalctl` で確認可能 (proto-1.0.0 改訂) |
| `User` | `root` | GPIO 制御に必要 |

> ⚠️ オリジナル版では `Restart=always` を採用していたが、proto-1.0.0 では正常停止 (`sudo systemctl stop`) 時に再起動しないよう `Restart=on-failure` に改訂した。これによりメンテナンス時の意図しない自動再起動を防止する。

### 5.2 シグナルハンドリング

両デーモンは `SIGINT` / `SIGTERM` を `trap` 関数でハンドリングする。

- `log_monitor`: GPIO を強制的に LOW にリセットしてから終了。
- `auto_tg_restore`: 待機中の復帰タイマーをキャンセルしてから終了。

### 5.3 多重起動防止 (proto-1.0.0 新規)

`auto_tg_restore` は `flock` を用いた排他制御を実装する。これにより手動起動と systemd 経由起動の競合や、再インストール時の二重起動を防止する。

```bash
exec 9>"$LOCK_FILE"
if ! flock -n 9; then exit 1; fi
```

---

## 6. メンテナンスとデバッグ

### 6.1 ログ確認

```bash
journalctl -u log_monitor -f
journalctl -u auto_tg_restore -f
```

### 6.2 サービス状態確認

```bash
systemctl status log_monitor
systemctl status auto_tg_restore
```

### 6.3 手動 TG 切替

シンボリックリンクが作成されているため、PATH 上から直接実行可能:

```bash
tg_change -168          # スロット1 を TG168 (ホームTG) に
tg_change -168:2        # スロット2 を TG168 に
```

直接パス指定も可:

```bash
/opt/tgifchanger/tg_change -168
```

### 6.4 GPIO 状態確認

libgpiod 使用時:

```bash
gpioget gpiochip0 17
```

sysfs 使用時:

```bash
cat /sys/class/gpio/gpio17/value
```

### 6.5 トラブルシューティング

| 症状 | 確認・対処 |
|---|---|
| GPIO が反応しない | (1) `journalctl -u log_monitor` で起動メッセージ確認 / (2) `GPIO_BACKEND` 値確認 / (3) `gpiodetect` で chip 認識確認 |
| TG が復帰しない | (1) `journalctl -u auto_tg_restore` でタイマー起動確認 / (2) `tg_change` を手動実行して API 疎通確認 / (3) DMR ID 取得確認 |
| DMR ID 取得失敗 | `/etc/dmrgateway` の `[DMR Network 4]` セクションに `Id=` 行があるか確認 |
| 二重起動エラー | `/run/auto_tg_restore.lock` を確認。古いロックは `sudo rm /run/auto_tg_restore.lock` で削除可 |
| `tg_change: command not found` | `/usr/local/bin/tg_change` symlink の有無を `ls -l` で確認。無ければ `sudo ln -sf /opt/tgifchanger/tg_change /usr/local/bin/tg_change` |

---

## 7. 動作環境

| 項目 | 対応バージョン / 仕様 |
|---|---|
| ハードウェア | Raspberry Pi Zero 2 W / 3 / 4 / 5 |
| OS (Pi-Star) | Pi-Star V4.2.3 (32-bit Bullseye / armv7l) |
| OS (WPSD) | WPSD (64-bit / aarch64) |
| MMDVMHost | 全バージョン (ログ書式互換性のあるもの) |
| DMRGateway | TGIF Network (DMR Network 4) 設定済 |
| Bash | 5.0 以上 |
| libgpiod (推奨) | `gpiod` パッケージ (`apt install gpiod`) |

---

## 付録A. proto-1.0.0 における主な改訂事項

| 項目 | オリジナル版 | proto-1.0.0 |
|---|---|---|
| 設定管理 | 各スクリプト先頭にハードコード | `/etc/tgifchanger.conf` に集約 |
| 配置先 | `/home/pi-star/scripts/` | `/opt/tgifchanger/` (FHS 準拠) |
| CLI 起動 | フルパス指定が必要 | `/usr/local/bin/tg_change` symlink で PATH 上から実行可 |
| GPIO 制御 | sysfs 直書きのみ | libgpiod 優先 / sysfs フォールバック |
| `WATCH_TG` | TG1 ハードコード | 設定ファイルで可変 |
| PID 追跡 | `tail \| while read` (サブシェル化) | プロセス置換 `< <(...)` で親シェル保持 |
| 多重起動防止 | なし | `flock` による排他制御 |
| ログファイル切替追従 | 未対応 (起動時のファイルのみ) | `read -t 5` で定期再評価して `tail` 再起動 |
| systemd Restart | `always` | `on-failure` |
| ログ出力 | `StandardOutput=null` | `StandardOutput=journal` |
| PIDファイル | `/tmp/auto_tg_restore.pid` | `/run/auto_tg_restore.pid` (フォールバック `/tmp`) |
| HTTP メソッド表記 | POST/GET (記述ミス) | GET (実装と整合) |

---

## 付録B. アンインストール手順

```bash
# サービス停止・無効化
sudo systemctl stop    log_monitor auto_tg_restore
sudo systemctl disable log_monitor auto_tg_restore

# unit ファイル削除
sudo rm /etc/systemd/system/log_monitor.service
sudo rm /etc/systemd/system/auto_tg_restore.service
sudo systemctl daemon-reload

# 本体・symlink・設定ファイル削除
sudo rm -rf /opt/tgifchanger
sudo rm -f  /usr/local/bin/tg_change
sudo rm -f  /etc/tgifchanger.conf /etc/tgifchanger.conf.dist
```

---

## 付録C. 著作・ライセンス

**ライセンス:** GPL v3 (OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開する)

**著作:** 篠田 一彦 / Kazuhiko Shinoda (JI2TAB)

- Owariasahi City, Aichi, Japan
- Manager of Aichi Digital Communication Ham Club (JJ2YYK)

**Special Thanks:**

- OpenCCVoice Project Contributors
- WPSD Developers
- Pi-Star Community
- MMDVM Developers
