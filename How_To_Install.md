# TGIFChanger-Py インストール＆運用ガイド

このガイドでは、Python版として統合・刷新された TGIFChanger-Py (v2.3.0) の導入から日常のメンテナンス、アンインストールまでの手順を解説します。

## 1. インストール / アップデート手順

Raspberry Pi (Pi-Star または WPSD) に SSH でログインし、以下のコマンドを実行してください。

```bash
# インストーラーを実行（自動で最新版を取得・更新します）
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | sudo bash
```

※Pi-Star環境で必要な書き込み許可（`rpi-rw`）は、インストーラー内部で自動的に行われます。手動での実行は不要です。

### インストーラーの主な動作

- 古いシェル版サービス（`log_monitor`, `auto_tg_restore`）の安全な停止と完全削除
- Python3 環境の確認と準備
- 新しい統合デーモンとCLIツールの配置
- 【新規インストール時】対話型セットアップ: 画面の指示に従い、初期設定（監視TG・復帰TG・復帰時間）を簡単に入力できます。
- 既存の設定ファイル `/etc/tgifchanger.conf` の保護（存在する場合は `.new` テンプレートを生成）
- systemd への単一サービス（`tgifchanger-py`）登録と自動起動設定

## 2. デーモンの状態・ログ確認

システムは1つの統合デーモンとして無駄なく動作します。

### ステータスと設定の確認

```bash
# デーモンの稼働状態、現在のタイマー有無、GPIOの状態を JSON で表示
tg_change --status

# 現在の設定ファイル一覧を表示
tg_change -c
```

### リアルタイムログの監視

```bash
# 監視と復帰のログを表示（終了は Ctrl+C）
journalctl -u tgifchanger-py -f
```

## 3. コマンドライン (CLI) 操作

`tg_change` コマンドを使って、API経由での手動TG切り替えや、設定の即時変更が可能です。

### 手動での TG 切り替え (即時送信)

```bash
# スロット1 を TG168 に変更
tg_change -168

# スロット2 を TG168 に変更
tg_change -168:2
```

### デーモン操作と設定変更

コマンドラインから設定を変更した場合、デーモンと直接通信して即座に動作に反映されるため、サービスの再起動は不要です。 ※設定ファイルの書き換えを伴うため `sudo` が必要です。

```bash
# 進行中の復帰タイマーをキャンセル（停止）
tg_change --cancel

# 監視TGを 1 に変更して保存
sudo tg_change -w 1

# 復帰TGを 168 に変更して保存
sudo tg_change -r 168

# 復帰までの待機時間を 120 秒に変更して保存
sudo tg_change -t 120
```

## 4. サービスの再起動・停止

※ `nano` コマンド等を使用して `/etc/tgifchanger.conf` を直接手動で編集した場合のみ、設定を読み込ませるために再起動が必要です。

```bash
# 再起動
sudo systemctl restart tgifchanger-py

# 停止 / 開始
sudo systemctl stop tgifchanger-py
sudo systemctl start tgifchanger-py
```

## 5. アンインストール手順

以下のコマンド一発で、プログラム本体・サービス・設定ファイルをすべて削除できます。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | sudo bash
```

---

**Author:** Kazuhiko Shinoda (JI2TAB)  
**Version:** v2.3.0
