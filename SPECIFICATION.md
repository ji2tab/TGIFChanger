# TGIFChanger-Py 技術仕様書

**Version:** v2.3.1 (Python Unified Daemon Edition)  
**Author:** Kazuhiko Shinoda (JI2TAB)  
**License:** GPL v3

本仕様書は、TGIFChanger-Py v2.3.1 の設計・実装・保守・再実装を目的とした正式技術仕様書である。従来のシェルスクリプト版（v1.x系）からPython3ネイティブデーモンへフルスクラッチされたアーキテクチャを定義する。

---

## 目次

1. [はじめに](#0-はじめに)
2. [システムアーキテクチャ](#1-システムアーキテクチャ)
3. [ソフトウェア詳細仕様](#2-ソフトウェア詳細仕様)
4. [設定ファイル仕様](#3-設定ファイル仕様)
5. [物理・電気仕様](#4-物理電気仕様)
6. [Reliability / systemd 設計](#5-reliability--systemd-設計)
7. [アーキテクチャ刷新の背景](#6-アーキテクチャ刷新の背景-v1x-からの課題解決)
8. [メンテナンスとデバッグ](#7-メンテナンスとデバッグ)
9. [動作環境](#8-動作環境)
10. [付録A. v2.3.1 主な改訂点](#付録a-v231-主な改訂点)
11. [付録B. 著作・ライセンス](#付録b-著作ライセンス)

---

## 改訂履歴

| 版 | 内容 |
|---|---|
| 1.0 | オリジナル版仕様書（sysfs / TG1固定 / Restart=always / /home/pi-star/scripts） |
| proto-1.0.0 | Bashプロト版として改訂。共通設定ファイル導入、libgpiod対応、ログファイル日付追従。 |
| v2.3.1 | Python3による統合デーモン化。tail -Fの廃止（インメモリ監視）、UDS通信、動的TG抽出、対話型インストーラー実装。 |

---

## 0. はじめに

本書は、MMDVM（Pi-Star / WPSD）環境向けトークグループ自動化ツール「TGIFChanger-Py」における技術仕様を定義する。

本ツールセットは、Arduino ベース音声ガイダンスシステム「OpenCCVoice」との物理的連携を前提として設計されている。Raspberry Pi GPIO 出力を OpenCCVoice 側 TM BUSY 入力へ接続することで、DMR 受信状態に応じた音声ガイダンス制御を、ソフトウェアプロトコルを介さず物理層で確実に実現する。

---

## 1. システムアーキテクチャ

本システムは、MMDVMHost が RAMディスク（`/var/log/pi-star/`）上に生成するログファイルを Python によってネイティブかつインメモリで監視するイベント駆動型アーキテクチャを採用する。

複数のシェルスクリプトに分離していた機能を一つのPythonデーモン（`tgif_daemon.py`）に統合し、CPUリソースの消費を極限まで抑えるとともに、Unix Domain Socket (UDS) を用いたセキュアなIPC（プロセス間通信）を実現している。

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
|   +-----------+  writes     +----------------------+   +------------+  |
|   | MMDVMHost |------------>| /var/log/pi-star/    |<---| DMRGateway | |
|   +-----------+             | MMDVM-YYYY-MM-DD.log |   +------------+  |
|         ^                   +----------+-----------+         ^         |
|         |                              |                     |         |
|         | DMR routing                  | Native File I/O     | conf    |
|         |                              | (inode tracking)    | read    |
|         |                              v                     |         |
|   +- - -|- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+  |
|   |  TGIFChanger-Py Suite (/opt/tgifchanger-py/)                    |  |
|   |                                                                 |  |
|   |   +-----------------------+      +---------------+              |  |
|   |   | tgif_daemon.py        |< UDS | tg_change.py  |--HTTP GET--+ |  |
|   |   | (Unified systemd unit)|      | (CLI Tool)    |            | |  |
|   |   +--------+------+-------+      +---------------+            | |  |
|   |            |      |   Timer Thread                            | |  |
|   |            |      +-------------------------------------------+ |  |
|   |     Hybrid GPIO Engine                                          |  |
|   |  (libgpiod/pinctrl/sysfs)                                       |  |
|   |            |                                                    |  |
|   |            v                                                    |  |
|   |   +-----------------+                                           |  |
|   |   | GPIO17 Output   |                                           |  |
|   |   +-----------------+                                           |  |
|   +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+  |
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
+=======================================================================+
```

### 1.2 ファイル配置

FHS に基づき、実行ファイルを `/opt/tgifchanger-py/` に集約する。

| パス | 用途 |
|---|---|
| `/opt/tgifchanger-py/tgif_daemon.py` | 統合デーモン本体 |
| `/opt/tgifchanger-py/tg_change.py` | CLIツール実体 |
| `/usr/local/bin/tg_change` | CLIツール シンボリックリンク |
| `/etc/tgifchanger.conf` | 共通設定ファイル |
| `/run/tgifchanger-py.sock` | UDS (Unix Domain Socket) |
| `/run/tgifchanger-py.lock` | fcntl 排他制御用ロックファイル |
| `/etc/systemd/system/tgifchanger-py.service` | systemd サービス定義 |

---

## 2. ソフトウェア詳細仕様

### 2.1 tgif_daemon.py (統合デーモン)

旧 `log_monitor` と `auto_tg_restore` を統合した中核プログラム。

#### ログ監視と追従 (inodeトラッキング)

- 外部コマンド `tail -F` を用いず、PythonネイティブのファイルI/OでRAMディスク上のログを監視する。
- WPSDが数秒〜数十秒間隔でファイルをローテーション（再作成）する挙動に対して、ファイルの i-node 変更を検知して瞬時に再オープンすることで、パイプ詰まりやフリーズを物理的に排除した。

#### タイマー管理

- PIDファイルによる管理を廃止し、メモリ上で `threading.Timer` を用いて安全に管理する。
- 受信イベントが発生するたびにタイマーを正確にキャンセル・再設定し、TGIF APIへのリクエスト連打（BAN回避）を防ぐ。

#### GPIOバックエンド (ハイブリッド対応)

- 環境に応じて最適なGPIO制御方式を自動判別（auto設定時）する。
  - **libgpiod v1/v2:** Bookworm / Raspberry Pi 5 環境で必須。gpiodetect でBCMチップを動的探索する。
  - **pinctrl / raspi-gpio / sysfs:** レガシー環境 (Buster等) のフォールバック。
- **フェイルセーフ:** ネットワーク瞬断等で終了ログを取りこぼした場合に備え、HIGH状態が 120秒 (デフォルト) 継続すると強制的にLOWへ落とす安全装置を搭載する。

### 2.2 tg_change.py (CLIツール)

TGIF Network API を呼び出してTGを変更する、およびデーモンを制御するCLIツール。

#### デーモン通信 (IPC)

- `/run/tgifchanger-py.sock` を介してデーモンとJSON形式で通信する。

#### ホットリロード機能

- 設定ファイル変更後、デーモンを再起動することなくリアルタイムで設定を反映させる（`-t`, `-w`, `-r` オプション）。

#### 権限チェック

- 脆弱性防止のため自動sudo昇格を廃止し、設定書き込み時は明示的なroot権限を要求する。

#### DMR ID / TG の動的解決

- `/etc/dmrgateway` 内の `[DMR Network *]` セクションを独自パーサで安全に解析し、`Address=tgif.network` の `Id=` を取得する。
- 設定ファイルに監視/復帰TGが未指定の場合、DMRGatewayの TGRewrite 設定から自動的に抽出し、ネットワークの変更に動的に追従する。

---

## 3. 設定ファイル仕様

設定は `/etc/tgifchanger.conf` に集約する。Bash（インストーラ）とPython双方で読み込み可能な `KEY="VALUE"` 形式を厳格に採用する。

| 変数 | 用途 | デフォルト | 備考 |
|---|---|---|---|
| `WATCH_SLOT` | 監視スロット | 2 | |
| `WATCH_TG` | 監視TG | 1 | 未指定時はTGRewriteから抽出 |
| `RESTORE_TG` | 復帰TG | 4000 | 切断TG(4000)をデフォルトとし、未指定時はTGRewriteから抽出 |
| `RESTORE_DELAY` | 復帰待機秒数 | 120 | |
| `GPIO_PIN` | GPIO番号 (BCM) | 17 | |
| `GPIO_BACKEND` | バックエンド | auto | libgpiod, pinctrl, sysfs 等 |
| `GPIO_CHIP` | libgpiod chip名 | auto | gpiochip0, gpiochip4 等 |

---

## 4. 物理・電気仕様

変更なし。proto-1.0.0 仕様に準ずる。

| 項目 | 内容 |
|---|---|
| 制御ピン | Raspberry Pi GPIO17 (Pin 11) <---> Arduino D11 |
| 接地 | Common Ground (Pin 9) |
| GPIO レベル | 3.3V CMOS (Active High) |

> **警告:** Arduino 側から Raspberry Pi GPIO へ 5V を入力してはならない。必ずArduino側をINPUTモードに設定すること。

---

## 5. Reliability / systemd 設計

デーモンは systemd により完全に管理される。

| Directive | 内容 |
|---|---|
| `Restart=on-failure` | エラー終了時のみ再起動。シグナル受信での正常終了時（終了コード0）は再起動しない。システム仕様書§5準拠。 |
| `After=mmdvmhost.service dmrgateway.service` | MMDVM本体の起動完了後に依存して起動。`ExecStartPre=sleep 20` の力技を廃止。 |
| `Type=simple` | 実行後すぐにステータスをActiveとする。Python側で最大120秒間ログファイルの生成を待機するループ機構により衝突を回避。 |
| `Environment=PYTHONUNBUFFERED=1` | バッファリングを無効化し、journalctl へのリアルタイムなログ出力を保証する。 |

**シグナル処理:** SIGTERM / SIGINT 受信時に GPIO を LOW へ安全にリセットし、ソケットやロックファイルをクリーンアップして終了する。

---

## 6. アーキテクチャ刷新の背景 (v1.x からの課題解決)

Bashシェルスクリプト版 (v1.x) は極めて洗練されていたが、WPSD環境において以下の限界（システム的負荷）が判明したため、v2.3.1にてPythonへフルスクラッチを行った。

### 「Fork」による深刻なCPU負荷

`grep` や `awk` を毎秒数十回呼び出すことで、OSカーネルのプロセス生成・破棄が連続し、非力なPi Zero環境ではWPSD本体のモデム処理を阻害する懸念があった。

### 非同期処理の競合とAPI連打

サブシェルによる `sleep` & 処理とPIDファイル管理は、ネットワーク瞬断時に古いタイマーが生き残り、TGIF APIに対して復帰リクエストを異常連打（BAN対象）するリスクが存在した。

### tail -F と RAMディスクの相性

WPSDはSDカード保護のためRAMディスク上で数秒間隔のログローテーションを行う。これに外部コマンドの `tail` を追従させるとパイプバッファが破綻し、読み込みがフリーズする（ブロックされる）原因となっていた。

### 解決策

これらを Python3 のインメモリ処理（正規表現、threading、inodeポーリング）で置換することで、CPU負荷ゼロ・ラグゼロの絶対的な安定性を獲得した。

---

## 7. メンテナンスとデバッグ

### デーモンの状態可視化 (JSON)

CLIからUDS経由で内部状態（タイマー状況、GPIO出力値、稼働バックエンド等）を即座に引き出せる。

```bash
tg_change --status
```

### ログ確認

```bash
journalctl -u tgifchanger-py -f
```

### 設定ファイルの確認

```bash
tg_change -c
```

---

## 8. 動作環境

| 項目 | 対応内容 |
|---|---|
| **Hardware** | Raspberry Pi Zero / Zero 2 W / 3 / 4 / 5 |
| **OS** | Pi-Star (Buster) / WPSD (Bookworm / Bullseye 64-bit) |
| **Runtime** | Python 3.7 以上 (Python 3.11 等 標準搭載環境) |
| **GPIO** | libgpiod v1 / v2（Pi 5 では必須）、または pinctrl 搭載環境 |

---

## 付録A. v2.3.1 主な改訂点

| 項目 | Bashプロト版 (proto-1.0.0) | Python統合版 (v2.3.1) |
|---|---|---|
| **言語・構成** | Bash 複数サービス | Python 3 単一デーモン |
| **ログ監視** | tail -F + grep / awk | Pythonネイティブ (inode監視) |
| **IPC (プロセス間通信)** | PIDファイル / サブシェル | Unix Domain Socket (UDS) |
| **設定反映** | サービスの再起動が必要 | UDS経由の即時ホットリロード |
| **インストール** | cp メインの手動配置 | 対話型スマートインストーラー |
| **TGデフォルト値** | ハードコード固定 | TGRewrite から動的抽出 |
| **安全装置** | なし | 120秒タイムアウトでGPIO LOW強制 |

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
