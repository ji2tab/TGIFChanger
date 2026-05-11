# TGIFChanger-Py アンインストールガイド

このガイドでは、システムから **TGIFChanger-Py** のすべてのプログラム、サービス、および設定ファイルを完全に削除（クリーンアップ）する手順を解説します。

⚠️ **注意:** この操作を行うと、ご自身で設定した `/etc/tgifchanger.conf` も含めて完全に削除されます。設定を残しておきたい場合は、事前にバックアップを取得してください。

---

## 1. ワンライナーによる完全アンインストール

Raspberry Pi (Pi-Star または WPSD) に SSH でログインし、以下のコマンドを1行実行するだけで、全自動でアンインストールが完了します。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | sudo bash
```

※Pi-Star環境で必要な書き込み許可（`rpi-rw`）は、アンインストーラー内部で自動的に行われます。手動で実行する必要はありません。

## 2. アンインストーラーが実行する処理の詳細

上記のスクリプトは、システムを安全かつクリーンな状態に戻すため、以下の処理を自動で行います。

### 1. サービスの強制停止と無効化

- 動作中の `tgifchanger-py` サービス（および旧版の `log_monitor`, `auto_tg_restore`）を停止し、自動起動を無効化します。

### 2. systemd サービス定義の削除

- `/etc/systemd/system/` に登録された関連サービスファイルをすべて削除します。

### 3. プログラム本体とコマンドの削除

- 実行ファイル群（`/opt/tgifchanger-py/` および旧版 `/opt/tgifchanger/`）をディレクトリごと削除します。
- CLIツールのシンボリックリンク（`/usr/local/bin/tg_change`）を削除します。

### 4. 一時ファイル（ソケット・ロック）の削除

- プロセス間通信に使われる `/run/tgifchanger-py.sock` などの不要な一時ファイルをクリーンアップします。

### 5. 設定ファイルの完全削除

- `/etc/tgifchanger.conf` およびバックアップ（`.new`）を削除します。

## 3. 手動でアンインストールする場合

もしワンライナー実行（`curl | bash`）を使わずに手動で削除したい場合は、以下のコマンドを順に実行してください。

```bash
# 1. 書き込み可能モードへ変更 (Pi-Starのみ)
sudo rpi-rw

# 2. サービスの停止と無効化
sudo systemctl stop tgifchanger-py
sudo systemctl disable tgifchanger-py

# 3. 関連ファイルの削除
sudo rm -f /etc/systemd/system/tgifchanger-py.service
sudo rm -rf /opt/tgifchanger-py
sudo rm -f /usr/local/bin/tg_change
sudo rm -f /run/tgifchanger-py.*
sudo rm -f /etc/tgifchanger.conf*

# 4. systemdの再読み込み
sudo systemctl daemon-reload
```

---

**Author:** Kazuhiko Shinoda (JI2TAB)  
**Version:** v2.3.1
