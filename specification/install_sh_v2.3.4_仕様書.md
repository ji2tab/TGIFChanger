# install.sh ソフトウェア仕様書

**ファイル:** `install.sh`
**バージョン:** v2.3.4
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py のスマートインストーラ兼マイグレーターです。旧バージョンの自動クリーンアップ、Python3 の確認、ファイル配置、設定ファイルの生成、systemd サービス登録までを一括で行います。

### v2.3.4 での変更点

- 対話型セットアップに「コールサイン監視時間（`CALLSIGN_TIMEOUT`）」のプロンプトを追加（デフォルト 300秒、非対話実行時も 300秒を採用）
- 生成する設定ファイルテンプレートに `CALLSIGN_TIMEOUT` 行を追加
- Pi 5 / `gpiochip4` 等の記述を削除し、対象を Raspberry Pi Zero〜4 に整理

### v2.3.1 での変更点

- DMRGateway / MMDVMHost の TGRewrite ルールを自動スキャンし、対話型プロンプトのデフォルト値として動的にサジェストする機能を追加
- TGRewrite 抽出時に複数行が結合されるバグを修正
- 復帰デフォルト値を TG168 から TG4000（Disconnect）へ変更
- パイプ実行時における Pi-Star `rpi-rw` の完全回避ロジックを実装

---

## 2. 実行方法

```bash
# ローカルファイルからインストール（tgif_daemon.py が同ディレクトリに存在する場合）
sudo bash install.sh

# GitHub から最新版を直接取得してインストール
sudo bash install.sh --from-github
```

- root 権限が必要です（非 root の場合はエラー終了）
- `set -euo pipefail` により、エラー発生時は即座に終了します

---

## 3. スクリプト変数

| 変数 | 値 | 説明 |
|------|----|------|
| `VERSION` | `v2.3.4` | インストーラバージョン |
| `INSTALL_DIR` | `/opt/tgifchanger-py` | プログラム配置先ディレクトリ |
| `CONF_FILE` | `/etc/tgifchanger.conf` | 設定ファイルパス |
| `SERVICE` | `tgifchanger-py` | systemd サービス名 |
| `SYMLINK` | `/usr/local/bin/tg_change` | CLI ツールへのシンボリックリンクパス |
| `RAW_URL` | `https://raw.githubusercontent.com/ji2tab/TGIFChanger/main` | GitHub Raw コンテンツのベース URL |

---

## 4. 処理フェーズ

### フェーズ 0 — Pi-Star Read-Only 完全回避

Pi-Star は起動時にファイルシステムを読み取り専用にマウントするため、書き込み可能モードへ切り替えます。

以下の順で試行します:

1. `/usr/local/sbin/rpi-rw` が実行可能であれば実行
2. `command -v rpi-rw` で `rpi-rw` が PATH 上にあれば実行
3. いずれも存在しない場合は `mount -o remount,rw /` および `mount -o remount,rw /boot` を実行

各コマンドは失敗しても `|| true` で継続します（パイプ実行時の `set -e` 終了を防ぐため）。

---

### フェーズ 1 — 旧バージョンのクリーンアップ

旧バージョン（`log_monitor`・`auto_tg_restore`）を含むすべての関連サービスを停止・無効化し、ファイルを削除します。

停止・無効化対象サービス:

- `log_monitor`
- `auto_tg_restore`
- `tgifchanger-py`

削除するファイル・ディレクトリ:

```
/etc/systemd/system/log_monitor.service
/etc/systemd/system/auto_tg_restore.service
/etc/systemd/system/tgifchanger-py.service
/opt/tgifchanger/      （旧バージョンのディレクトリ）
/opt/tgifchanger-py/   （現バージョンのディレクトリ）
```

各 `systemctl` は失敗しても継続します。

---

### フェーズ 2 — Python3 確認

`command -v python3` で Python3 の存在を確認します。

- **存在する場合:** バージョン番号をログ出力して続行
- **存在しない場合:** `apt-get update` → `apt-get install -yq python3` を実行（失敗しても継続）

---

### フェーズ 3 — ファイル配置

`INSTALL_DIR` を `mkdir -p` で作成後、以下の条件でファイルを取得します。

| 条件 | 動作 |
|------|------|
| 引数 `--from-github` が指定されている | GitHub から `curl` で取得 |
| カレントディレクトリに `tgif_daemon.py` が存在しない | GitHub から `curl` で取得 |
| 上記以外（ローカルにファイルが存在） | スクリプトと同ディレクトリからコピー |

取得・コピー対象ファイル:

- `tgif_daemon.py`
- `tg_change.py`

両ファイルに `chmod +x` を付与後、`tg_change.py` から `SYMLINK` へシンボリックリンクを作成します（既存時は `ln -sf` で上書き）。

GitHub からの取得コマンド:

```bash
curl -H 'Cache-Control: no-cache' -fsSL -o "${INSTALL_DIR}/${f}" "${RAW_URL}/${f}"
```

---

### フェーズ 4 — TGRewrite ルールの動的抽出

インストール時に既存の DMRGateway / MMDVMHost 設定から `WATCH_TG` と `RESTORE_TG` の推奨値を自動抽出します。

#### 抽出ファイルの優先順位

1. `/etc/dmrgateway`（優先）
2. `/etc/mmdvmhost`（フォールバック）

#### 抽出対象フォーマット

```ini
[DMR Network N]
Address=tgif.network
TGRewrite0=2,<WATCH_TG>,2,<RESTORE_TG>,1
```

カンマ区切りの**第 2 フィールド** → `DETECTED_WATCH`、**第 4 フィールド** → `DETECTED_RESTORE` として抽出します。

#### awk スクリプトの動作

| ステップ | 処理 |
|---------|------|
| 1 | `[DMR Network...]` セクション開始を検出。直前のセクションが TGIF かつ TGRewrite を持つなら即出力・終了 |
| 2 | `Address=tgif.network` を含む行を検出したら `is_tgif` フラグをセット |
| 3 | `TGRewriteN=` の**最初の 1 行のみ**を `rewrite` 変数へ格納（複数行マージ防止） |
| 4 | 別セクション開始（`^\[` ）でも評価・出力（TGIF セクションが最終セクションの場合も対応） |
| 5 | ファイル末尾の `END` ブロックでも未出力セクションを評価・出力 |

#### フォールバック値

抽出に失敗した場合（ファイル不在・値が空）:

| 変数 | フォールバック値 |
|------|----------------|
| `DETECTED_WATCH` | `1` |
| `DETECTED_RESTORE` | `4000` |

---

### フェーズ 5 — 設定ファイル生成

#### 既存の設定ファイルが存在する場合

`/etc/tgifchanger.conf` を**そのまま保持**し、新バージョン用のテンプレートを `/etc/tgifchanger.conf.new` として保存します（差分確認用）。テンプレートには抽出した推奨値が埋め込まれます。

#### 設定ファイルが存在しない場合

端末（tty）の接続状態に応じて動作が分岐します。

**対話モード**（`[ -t 0 ] || [ -c /dev/tty ]` が真の場合）:

入力を `/dev/tty` から直接読み取ることで、パイプ経由の実行でも対話が成立します。

| プロンプト | 対応パラメータ | デフォルト |
|-----------|--------------|-----------|
| `▶ 監視TG (WATCH_TG)` | `WATCH_TG` | 抽出値（`DETECTED_WATCH`） |
| `▶ 復帰TG (RESTORE_TG)` | `RESTORE_TG` | 抽出値（`DETECTED_RESTORE`） |
| `▶ 復帰までの時間(秒) (RESTORE_DELAY)` | `RESTORE_DELAY` | `120` |
| `▶ コールサイン監視時間(秒) (CALLSIGN_TIMEOUT)` | `CALLSIGN_TIMEOUT` | `300`（`0` で無効） |

**非対話モード**（CI・パイプ実行など）:

警告を出力し、抽出した推奨値をすべて自動採用します。

#### 生成される設定ファイルの内容

```bash
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_SLOT="2"
WATCH_TG="<入力値または抽出値>"
RESTORE_TG="<入力値または抽出値>"
RESTORE_DELAY="<入力値または 120>"
CALLSIGN_TIMEOUT="<入力値または 300>"
GPIO_PIN="17"
GPIO_BACKEND="auto"
GPIO_CHIP="auto"
TGIF_API="http://tgif.network:5040/api/sessions/update"
TGIF_API_TIMEOUT="10"
```

パーミッション: `644`

---

### フェーズ 6 — systemd ユニット登録

以下の内容で `/etc/systemd/system/tgifchanger-py.service` を生成します。

```ini
[Unit]
Description=TGIFChanger-Py Unified Daemon (v2.3.4)
Documentation=https://github.com/ji2tab/TGIFChanger
After=network-online.target mmdvmhost.service dmrgateway.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/tgifchanger-py/tgif_daemon.py
Restart=on-failure
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tgifchanger-py
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

生成後に以下を実行します:

```bash
systemctl daemon-reload
systemctl enable tgifchanger-py
systemctl restart tgifchanger-py
```

---

## 5. インストール完了後の確認コマンド

| コマンド | 用途 |
|---------|------|
| `journalctl -u tgifchanger-py -f` | リアルタイムログ確認 |
| `tg_change --status` | デーモン動作状態確認 |
| `tg_change -c` | 設定ファイル内容確認 |

---

## 6. 依存コマンド

| コマンド | 用途 | 必須 |
|---------|------|------|
| `systemctl` | サービス管理 | ✅ |
| `python3` | デーモン実行環境 | ✅（不在時は自動インストール） |
| `curl` | GitHub からのファイル取得 | `--from-github` 時のみ |
| `awk` | TGRewrite ルール抽出 | 設定ファイル存在時のみ |
| `rpi-rw` / `mount` | FS 書き込み化 | Pi-Star 環境のみ |
| `apt-get` | Python3 自動インストール | Python3 不在時のみ |
