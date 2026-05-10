# TGIFChanger インストール＆運用ガイド

このガイドでは、TGIFChanger の導入から日常のメンテナンス、アンインストールまでの手順を解説します。

---

## 1. インストール / アップデート手順

Raspberry Pi (Pi-Star または WPSD) に SSH でログインし、以下のコマンドを実行してください。

```bash
# Pi-Star の場合は書き込み許可を与えます（WPSD では不要）
rpi-rw

# インストーラーを実行（自動で最新版を取得・更新します）
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash
```

インストーラーの主な動作:

- 依存パッケージ `gpiod` の自動インストール
- 既存サービスの安全な停止とファイルの上書き更新
- 既存の設定ファイル `/etc/tgifchanger.conf` の保護
- systemd へのサービス登録と自動起動設定

---

## 2. よく使う管理コマンド

### ログの確認

```bash
# 監視と復帰のログを同時に表示（終了は Ctrl+C）
journalctl -u log_monitor -u auto_tg_restore -f
```

### サービスの操作

設定ファイルを変更した後は必ず再起動してください。

```bash
# 再起動（設定を反映させる）
sudo systemctl restart log_monitor auto_tg_restore

# 停止
sudo systemctl stop log_monitor auto_tg_restore

# 開始
sudo systemctl start log_monitor auto_tg_restore
```

---

## 3. 手動での TG 切り替え

```bash
# スロット1 を TG168 に変更
tg_change -168

# スロット2 を TG168 に変更
tg_change -168:2
```

---

## 4. アンインストール手順

以下のコマンド一発で、プログラム本体・サービス・設定ファイルをすべて削除できます。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | bash
```

---

Author: Kazuhiko Shinoda (JI2TAB) / v1.2.4
