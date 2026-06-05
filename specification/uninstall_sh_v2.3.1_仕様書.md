# uninstall.sh ソフトウェア仕様書

**ファイル:** `uninstall.sh`
**バージョン:** v2.3.1
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py の完全アンインストーラです。すべてのプログラム本体・systemd サービス定義・一時ファイル・設定ファイルを削除します。旧バージョン（`log_monitor`・`auto_tg_restore`）のファイルも対象に含まれます。

---

## 2. 実行方法

```bash
sudo bash uninstall.sh
```

- root 権限が必要です（非 root の場合はエラー終了）
- `set -euo pipefail` により、エラー発生時は即座に終了します
- 実行後 **5 秒のカウントダウン**があります。`Ctrl+C` でキャンセル可能です

---

## 3. 処理フロー

### 前処理 — Pi-Star Read-Only 回避

`sleep 5` のカウントダウン後、最初に Pi-Star の読み取り専用ファイルシステムを書き込み可能へ切り替えます。`install.sh` と同じフォールバック順で試行します。

| 試行順 | 条件 | 実行コマンド |
|--------|------|------------|
| 1 | `/usr/local/sbin/rpi-rw` が実行可能 | `/usr/local/sbin/rpi-rw` |
| 2 | `rpi-rw` が PATH 上に存在 | `rpi-rw` |
| 3 | 上記いずれも不在 | `mount -o remount,rw /` および `mount -o remount,rw /boot` |

各コマンドは失敗しても `|| true` で継続します。

---

### ステップ 1 — サービスの停止と無効化

旧バージョンを含む全関連サービスを停止・無効化します。

停止・無効化対象:

- `log_monitor`
- `auto_tg_restore`
- `tgifchanger-py`

各 `systemctl stop` / `systemctl disable` は失敗しても継続します（サービスが存在しない環境でもエラーになりません）。

---

### ステップ 2 — systemd サービスファイルの削除

削除するサービスファイル:

```
/etc/systemd/system/log_monitor.service
/etc/systemd/system/auto_tg_restore.service
/etc/systemd/system/tgifchanger-py.service
```

削除後に `systemctl daemon-reload` を実行してサービス定義の変更を systemd へ反映します。

---

### ステップ 3 — プログラム本体の削除

削除するディレクトリ・ファイル:

| パス | 内容 |
|------|------|
| `/opt/tgifchanger/` | 旧バージョンのプログラムディレクトリ（`rm -rf`） |
| `/opt/tgifchanger-py/` | 現バージョンのプログラムディレクトリ（`rm -rf`） |
| `/usr/local/bin/tg_change` | CLI ツールへのシンボリックリンク |

---

### ステップ 4 — 一時ファイルの削除

実行時に生成される一時ファイルを削除します。

| パス | 内容 |
|------|------|
| `/run/tgifchanger-py.sock` | Unix ドメインソケット |
| `/run/tgifchanger-py.lock` | 多重起動防止ロックファイル |
| `/run/tgifchanger.cmd` | 旧バージョンのコマンドファイル |
| `/run/auto_tg_restore.pid` | 旧バージョンの PID ファイル |

---

### ステップ 5 — 設定ファイルの完全削除

削除する設定ファイル:

| パス | 内容 |
|------|------|
| `/etc/tgifchanger.conf` | メイン設定ファイル |
| `/etc/tgifchanger.conf.new` | アップグレード用差分テンプレート |

> **注意:** 設定ファイルはバックアップなしで完全に削除されます。再インストール時は `install.sh` による設定ファイルの再生成が必要です。

---

## 4. 削除対象の全ファイル一覧

| カテゴリ | パス |
|---------|------|
| サービス定義 | `/etc/systemd/system/log_monitor.service` |
| サービス定義 | `/etc/systemd/system/auto_tg_restore.service` |
| サービス定義 | `/etc/systemd/system/tgifchanger-py.service` |
| プログラム本体 | `/opt/tgifchanger/`（旧） |
| プログラム本体 | `/opt/tgifchanger-py/` |
| CLI リンク | `/usr/local/bin/tg_change` |
| 一時ファイル | `/run/tgifchanger-py.sock` |
| 一時ファイル | `/run/tgifchanger-py.lock` |
| 一時ファイル | `/run/tgifchanger.cmd`（旧） |
| 一時ファイル | `/run/auto_tg_restore.pid`（旧） |
| 設定ファイル | `/etc/tgifchanger.conf` |
| 設定ファイル | `/etc/tgifchanger.conf.new` |

---

## 5. 依存コマンド

| コマンド | 用途 | 必須 |
|---------|------|------|
| `systemctl` | サービス停止・無効化・daemon-reload | ✅ |
| `rm` | ファイル・ディレクトリ削除 | ✅ |
| `rpi-rw` / `mount` | FS 書き込み化 | Pi-Star 環境のみ |
