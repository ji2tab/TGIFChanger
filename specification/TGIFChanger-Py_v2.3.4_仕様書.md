# TGIFChanger-Py ソフトウェア仕様書

**バージョン:** v2.3.4
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py は、Pi-Star / WPSD ホットスポット上で動作する **DMR トークグループ自動切替デーモン**です。TGIF ネットワーク上の通話を検知し、指定時間経過後に既定のトークグループへ自動復帰させます。GPIO ピンを介した OpenCCVoice / Arduino との連携にも対応しています。

### 1.1 主な機能

- MMDVM / DMRGateway ログの常時監視とトークグループ変化の検出
- 指定トークグループ（`WATCH_TG`）への接続検知
- 設定した待機時間（`RESTORE_DELAY` 秒）経過後の自動復帰（`RESTORE_TG`）
- コールサイン・ウォッチドッグ（真の利用者の RF を `CALLSIGN_TIMEOUT` 秒確認できなければ強制復帰）［v2.3.4］
- TGIF API（HTTP POST）を使ったトークグループ強制設定
- GPIO ピン入力による即時トークグループ切替（OpenCCVoice 連携）
- `tg_change` コマンドによる実行時パラメータ変更・ステータス確認
- DMRGateway / MMDVMHost 設定ファイルからの TGRewrite ルール自動抽出

### 1.2 動作環境

| 項目 | 内容 |
|------|------|
| 対応 OS | Pi-Star / WPSD（Raspbian Buster / Bullseye） |
| ハードウェア | Raspberry Pi Zero 2W・Pi 3・Pi 4（armhf / arm64） |
| Python | Python 3.6 以上（外部ライブラリ不要） |
| 依存サービス | MMDVMHost または DMRGateway（ログファイル生成元） |
| ネットワーク | TGIF ネットワーク接続（http://tgif.network:5040/） |

---

## 2. ファイル構成

### 2.1 インストール後のファイル配置

| パス | 説明 |
|------|------|
| `/opt/tgifchanger-py/tgif_daemon.py` | メインデーモンスクリプト |
| `/opt/tgifchanger-py/tg_change.py` | CLI 制御ツール |
| `/etc/tgifchanger.conf` | 設定ファイル（Bash KEY=VALUE 形式） |
| `/etc/systemd/system/tgifchanger-py.service` | systemd ユニットファイル |
| `/usr/local/bin/tg_change` | `tg_change.py` へのシンボリックリンク |

### 2.2 インストールスクリプト (install.sh) のフェーズ

| フェーズ | 処理 | 詳細 |
|---------|------|------|
| 0 | FS 書き込み化 | `rpi-rw` / `mount remount,rw` で Pi-Star 読み取り専用を解除 |
| 1 | 旧版クリーンアップ | 旧サービス停止・ファイル削除（`log_monitor` / `auto_tg_restore` 含む） |
| 2 | Python3 確認 | 未インストールの場合は `apt-get` で自動取得 |
| 3 | ファイル配置 | `--from-github` 指定時または `tgif_daemon.py` 不在時は GitHub から `curl` 取得 |
| 4 | TGRewrite 抽出 | `/etc/dmrgateway` または `/etc/mmdvmhost` から TGIF セクションの TGRewrite を awk で解析 |
| 5 | 設定ファイル生成 | 既存 conf 保持 / 対話入力 / 非対話モード自動採用（抽出値をデフォルト） |
| 6 | systemd 登録 | ユニット作成・`daemon-reload`・`enable`・`restart` |

---

## 3. 設定パラメータ

設定ファイル `/etc/tgifchanger.conf` は Bash KEY=VALUE 形式で記述します。インストーラと `tg_change` コマンドの両方から読み込まれます。

| パラメータ | 型 | デフォルト値 | 説明 |
|-----------|-----|------------|------|
| `LOG_DIR` | 文字列 | `/var/log/pi-star` | MMDVMHost ログファイルのディレクトリ |
| `WATCH_SLOT` | 整数 | `2` | 監視対象の DMR タイムスロット番号 |
| `RESTORE_SLOT` | 整数 | `2` | 復帰操作に使用するタイムスロット番号 |
| `WATCH_TG` | 整数 | （自動抽出） | 監視対象トークグループ番号（TGRewrite から抽出） |
| `RESTORE_TG` | 整数 | `4000` | 自動復帰先トークグループ番号（4000 = Disconnect） |
| `RESTORE_DELAY` | 整数（秒） | `120` | `WATCH_TG` への接続検知後、復帰するまでの待機時間 |
| `CALLSIGN_TIMEOUT` | 整数（秒） | `300` | 真の利用者（RFアクセス局）を確認できなくなってから強制復帰するまでの秒数。`0` で無効 |
| `GPIO_PIN` | 整数 | `17` | GPIO 入力ピン番号（BCM 番号体系） |
| `GPIO_BACKEND` | 文字列 | `auto` | GPIO 制御バックエンド（後述） |
| `GPIO_CHIP` | 文字列 | `auto` | libgpiod 使用時の gpiochip 番号（`auto` で自動判定） |
| `TGIF_API` | URL | （内部規定） | TGIF セッション更新 API エンドポイント |
| `TGIF_API_TIMEOUT` | 整数（秒） | `10` | TGIF API 呼び出しのタイムアウト時間 |

### 3.1 GPIO_BACKEND の選択値

| 値 | 動作 |
|----|------|
| `auto` | `pinctrl` → `raspi-gpio` → `sysfs` の順で利用可能なバックエンドを自動選択（デフォルト） |
| `libgpiod` | libgpiod v1/v2 を使用。Bookworm 環境で推奨。`gpiodetect` で BCM チップを自動判定。 |
| `pinctrl` | `pinctrl` コマンドを強制使用 |
| `raspi-gpio` | `raspi-gpio` コマンドを強制使用 |
| `sysfs` | `/sys/class/gpio` を経由する旧来の sysfs インターフェイスを強制使用 |
| `null` | GPIO を無効化（テスト・デバッグ用） |

---

## 4. TGRewrite 自動抽出ロジック

インストール時に `/etc/dmrgateway`（優先）または `/etc/mmdvmhost` を awk で解析し、TGIF セクションに定義された最初の TGRewrite ルールから `WATCH_TG` と `RESTORE_TG` の推奨値を動的に抽出します。

### 4.1 抽出対象フォーマット

```ini
[DMR Network 3]
Address=tgif.network
TGRewrite0=2,1234,2,4000,1
```

カンマ区切りの**第 2 フィールド**が `WATCH_TG`、**第 4 フィールド**が `RESTORE_TG` として抽出されます。

### 4.2 抽出フロー

| ステップ | 処理 |
|---------|------|
| 1 | `[DMR Network...]` セクション開始を検出し、直前セクションを評価（TGIF かつ TGRewrite あり → 出力） |
| 2 | `Address=tgif.network` を検出した場合のみ `is_tgif` フラグを立てる |
| 3 | 同セクション内の最初の `TGRewriteN=` 行のみを `rewrite` 変数に格納（複数行マージ防止） |
| 4 | ファイル末尾（`END` ブロック）でも未出力のセクションを評価・出力 |
| 5 | 抽出値が空の場合は `WATCH_TG=1`、`RESTORE_TG=4000` をフォールバック値として使用 |

---

## 5. デーモン動作仕様（tgif_daemon.py）

### 5.1 起動シーケンス

1. 設定ファイル `/etc/tgifchanger.conf` を読み込む
2. GPIO バックエンドを初期化する
3. `LOG_DIR` のログファイルを `tail -f` 相当で監視開始
4. systemd によって on-failure 時に 10 秒後に自動再起動

### 5.2 トークグループ切替ロジック

| イベント | 処理 |
|---------|------|
| `WATCH_TG` への接続ログを検出 | `RESTORE_DELAY` 秒のタイマーをリセット（またはセット） |
| タイマー満了（無通話のまま `RESTORE_DELAY` 秒経過） | TGIF API に `RESTORE_TG` を POST して強制切替 |
| GPIO ピン入力 HIGH 検出 | 即時に `WATCH_TG` へ切替（タイマーリセット） |
| TGIF API エラー | タイムアウト（`TGIF_API_TIMEOUT` 秒）後にリトライ、ログ記録 |

### 5.3 ログ確認

```bash
# リアルタイムログ追跡
journalctl -u tgifchanger-py -f

# 本日分ログ表示
journalctl -u tgifchanger-py --since today
```

---

## 6. CLI ツール（tg_change）

シンボリックリンク `/usr/local/bin/tg_change` 経由で `tg_change.py` を呼び出します。設定変更はデーモンに即時反映されます。

| コマンド例 | 説明 |
|-----------|------|
| `tg_change --status` | 現在の動作状態とアクティブ設定値を表示 |
| `tg_change -c` | 設定ファイルの内容を表示 |
| `tg_change -w <TG番号>` | `WATCH_TG` を変更（即時反映） |
| `tg_change -r <TG番号>` | `RESTORE_TG` を変更（即時反映） |
| `tg_change -t <秒>` | `RESTORE_DELAY` を変更（即時反映） |
| `tg_change -k <秒>` | `CALLSIGN_TIMEOUT` を変更（即時反映、`0` で無効） |

> **設定反映のルール:**
> `tg_change` コマンド経由の変更はデーモンに即時反映されます。
> `/etc/tgifchanger.conf` を手動編集した場合は `sudo systemctl restart tgifchanger-py` で再起動が必要です。

---

## 7. systemd サービス定義

| ディレクティブ | 値と説明 |
|--------------|---------|
| `Type` | `simple` — フォアグラウンドで常駐 |
| `ExecStart` | `/usr/bin/python3 /opt/tgifchanger-py/tgif_daemon.py` |
| `Restart` | `on-failure` — 異常終了時のみ再起動 |
| `RestartSec` | `10` — 再起動まで 10 秒待機 |
| `After` | `network-online.target mmdvmhost.service dmrgateway.service` |
| `Wants` | `network-online.target` |
| `User` | `root`（GPIO / ログアクセスに root 権限が必要） |
| `StandardOutput` | `journal`（systemd ログに統合） |
| `PYTHONUNBUFFERED` | `1`（ログのバッファリング無効、リアルタイム出力） |

---

## 8. インストール・アンインストール手順

### 8.1 インストール

```bash
# ローカルファイルからインストール
sudo bash install.sh

# GitHub から最新版を直接取得してインストール
sudo bash install.sh --from-github
```

### 8.2 アンインストール

```bash
sudo systemctl stop tgifchanger-py
sudo systemctl disable tgifchanger-py
sudo rm -f /etc/systemd/system/tgifchanger-py.service
sudo rm -rf /opt/tgifchanger-py
sudo rm -f /usr/local/bin/tg_change
sudo rm -f /etc/tgifchanger.conf
sudo systemctl daemon-reload
```

---

## 9. バージョン履歴

### v2.3.4

- コールサイン・ウォッチドッグ（真の利用者監視 / `CALLSIGN_TIMEOUT`）を追加。RFアクセス局を一定時間確認できなければネット通話継続中でも強制復帰
- `tg_change -k <秒>` オプションを追加（`0` で無効、`RESTORE_DELAY` 未満で警告）
- `install.sh` の対話セットアップに「コールサイン監視時間」を追加、設定テンプレートに `CALLSIGN_TIMEOUT` を追加
- Pi 5 / `gpiochip4` の記述を削除し、対象を Raspberry Pi Zero〜4 に整理

### v2.3.3

- logrotate 切替時のレースコンディションを修正（`get_latest()` 空応答・`os.stat()` 例外の堅牢化）

### v2.3.2

- 設定ファイル書き込みのアトミック化（`fcntl.flock` 排他ロック＋`os.replace`）

### v2.3.1

- DMRGateway / MMDVMHost の TGRewrite ルール自動スキャン機能を追加（インストール時のデフォルト値に動的サジェスト）
- TGRewrite 抽出時に複数行が結合されるバグを修正
- 復帰デフォルト値を TG168 から TG4000（Disconnect）へ変更
- パイプ実行時における Pi-Star `rpi-rw` の完全回避ロジックを実装

### v2.3.0

- ベースラインリリース

---

> 本仕様書は `install.sh` v2.3.4 のソースコードを元に作成しました。`tgif_daemon.py` および `tg_change.py` の詳細仕様については、各スクリプトの docstring またはリポジトリの README を参照してください。
