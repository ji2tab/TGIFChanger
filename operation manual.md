# TGIFChanger-Py 操作説明書（Operation Manual）

対象バージョン: v2.3.1（Python 3 Unified Daemon & Smart Installer Edition）
対応環境: MMDVM（Pi-Star / WPSD）
ライセンス: GPL v3
作者: 篠田 一彦 / Kazuhiko Shinoda (JI2TAB)
リポジトリ: https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py は、Pi-Star / WPSD 環境で TGIF ネットワーク運用を自動化するツールです。MMDVMHost のログをインメモリでリアルタイム解析し、通信終了から一定時間後に自動でホームTGへ強制復帰させます。デジピーター運用での「TG戻し忘れ」を防止することが主な目的です。

あわせて、監視中のTG受信状態を Raspberry Pi の GPIO ピンから出力し、音声ガイダンスシステム「OpenCCVoice」（Arduino Nano）との物理連携を行えます。

主な特長:
- Python 3 統合デーモンによる低負荷動作（Pi Zero 等でもCPU負荷ほぼゼロ）
- インメモリタイマーによる API 連打・二重送信の防止
- libgpiod / pinctrl / raspi-gpio / sysfs を自動判定するハイブリッドGPIOエンジン（Pi-Star〜Pi 5 対応）
- Unix ドメインソケット（UDS）によるホットリロード（再起動不要の設定反映）
- フェイルセーフ機能（終了ログ取りこぼし時も最大120秒でGPIOをLOWへ）

---

## 2. システム接続仕様（GPIO 配線）

| Raspberry Pi | Arduino Nano | 役割 |
|---|---|---|
| GPIO17 (Pin 11) | D11 | TG 受信状態（High: 受信中 / Low: 待機） |
| GND (Pin 9) | GND | 共通接地（Common Ground） |

注意事項:
- Raspberry Pi の GPIO は **3.3V 出力** です。Arduino 側は必ず **INPUT モード** で使用してください。
- GPIO17 への HIGH 出力は、設定した **監視TG（WATCH_TG）と一致するTGの受信時のみ** 発生します。他のTGの通信はスルーされます。
- 自局コールサインからの送信は除外されるため、自分の送信中に誤って信号が出ることはありません。

---

## 3. インストール / アップデート

Raspberry Pi（Pi-Star または WPSD）に SSH でログインし、以下を実行します。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | sudo bash
```

- 書き込み許可（rpi-rw）や旧バージョンのクリーンアップはインストーラーが自動で行います。
- **新規インストール時** は対話型セットアップが起動し、「監視TG」「復帰TG」「復帰までの時間」を入力できます（DMRGateway の TGRewrite 設定があれば自動的にデフォルト値を提案）。
- 既存の `/etc/tgifchanger.conf` は上書きされず保持され、新テンプレートは `/etc/tgifchanger.conf.new` として保存されます。

インストーラーの主な動作: 旧シェル版サービスの停止・削除 / Python3 環境準備 / 統合デーモンとCLIツールの配置 / systemd サービス（`tgifchanger-py`）の登録と自動起動設定。

---

## 4. 状態・ログの確認

```bash
# デーモンの稼働状況、現在のタイマー、GPIO状態を JSON で表示
tg_change --status

# 現在の設定一覧を表示
tg_change -c

# リアルタイム動作ログの監視（終了は Ctrl+C）
journalctl -u tgifchanger-py -f
```

---

## 5. 運用コマンド（CLI）

操作は統合された `tg_change` コマンドで行います。

### 5.1 手動でのTG切り替え（即時送信）

```bash
tg_change -168       # スロット1 を TG168 に変更
tg_change -168:2     # スロット2 を TG168 に変更
```

### 5.2 タイマー操作・設定変更

設定を変更するとデーモンへ自動でホットリロードがかかるため、**サービスの再起動は不要** です。
設定ファイルの書き換えを伴う操作には `sudo` が必要です。

```bash
tg_change --cancel       # 進行中の自動復帰タイマーをキャンセル
sudo tg_change -w 168    # 監視TG（WATCH_TG）を変更
sudo tg_change -r 44833  # 復帰TG（RESTORE_TG）を変更
sudo tg_change -t 90     # 復帰までの待機時間（秒）を変更
```

---

## 6. 設定ファイル

設定は `/etc/tgifchanger.conf` に集約されています（`KEY="value"` 形式）。このファイルは install.sh / tgif_daemon.py / tg_change.py の3コンポーネントから共通して読み込まれます。

| パラメータ | サンプル値 | 変更コマンド | 説明 |
|---|---|---|---|
| LOG_DIR | /var/log/pi-star | 手動編集のみ | MMDVM ログディレクトリ |
| WATCH_SLOT | 2 | 手動編集のみ | 監視タイムスロット（1 または 2） |
| RESTORE_SLOT | 2 | 手動編集のみ | 復帰タイムスロット（1 または 2） |
| WATCH_TG | 1 | `tg_change -w <TG>` | 監視トークグループ（空なら TGRewrite から自動抽出） |
| RESTORE_TG | 168 | `tg_change -r <TG>` | 復帰先TG（4000 で TGIF 切断。空ならフォールバック 4000） |
| RESTORE_DELAY | 120 | `tg_change -t <秒>` | 復帰までの待機時間（秒） |
| GPIO_PIN | 17 | 手動編集のみ | GPIO 出力ピン番号（BCM） |
| GPIO_BACKEND | auto | 手動編集のみ | GPIO バックエンド（auto / libgpiod / pinctrl / raspi-gpio / sysfs / null） |
| GPIO_CHIP | auto | 手動編集のみ | gpiochip 番号（GPIO_BACKEND=libgpiod のとき有効） |
| TGIF_API | http://tgif.network:5040/api/sessions/update | 手動編集のみ | TGIF API エンドポイント |
| TGIF_API_TIMEOUT | 10 | 手動編集のみ | API タイムアウト（秒） |

補足:
- `tg_change -w/-r/-t` での変更はデーモンへ即時反映されます（reload 自動送信）。
- アップグレード時、既存の設定ファイルは上書きされず保持され、新テンプレートは `/etc/tgifchanger.conf.new` として別保存されます。差分を確認して必要なパラメータを手動でマージしてください。
- `tg_change` による書き込みは排他ロック（fcntl.flock）とアトミック書き込み（os.replace）で保護されています。

### 6.1 設定ファイルを直接編集する場合の手順

`tg_change` コマンドが用意されていないパラメータ（LOG_DIR / WATCH_SLOT / RESTORE_SLOT / GPIO_PIN / GPIO_BACKEND / GPIO_CHIP / TGIF_API / TGIF_API_TIMEOUT）は、`/etc/tgifchanger.conf` を直接編集します。直接編集した場合はデーモンへ自動反映されないため、最後にサービスの再起動が必要です。

```bash
# 1. Pi-Star の場合、書き込み可能モードへ変更
rpi-rw

# 2. エディタで設定ファイルを開いて編集
sudo nano /etc/tgifchanger.conf

# 3. 編集後、保存して終了（nano は Ctrl+O → Enter → Ctrl+X）

# 4. デーモンに設定を読み込ませるためサービスを再起動
sudo systemctl restart tgifchanger-py

# 5. 反映結果を確認
tg_change -c
```

注意: WATCH_TG / RESTORE_TG / RESTORE_DELAY は専用コマンド（`tg_change -w/-r/-t`）で変更すると再起動不要で即時反映されるため、通常はコマンドでの変更を推奨します。

---

## 7. サービス操作

```bash
sudo systemctl restart tgifchanger-py   # 再起動
sudo systemctl stop tgifchanger-py      # 停止
sudo systemctl start tgifchanger-py     # 開始
```

---

## 8. アンインストール

プログラム本体・サービス・設定ファイルをすべて削除します（rpi-rw 解除も自動）。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | sudo bash
```

---

## 9. 動作の仕組み（補足）

1. MMDVMHost のログを監視し、`WATCH_TG` の voice header 検出時に GPIO を HIGH にして復帰タイマーをキャンセルします。
2. `WATCH_TG` / `RESTORE_TG` 以外のTGでの通話終了を検知すると、`RESTORE_DELAY` 秒後に `RESTORE_TG` へ自動復帰します。
3. 復帰リクエストは `{TGIF_API}/{DMR_ID}/{SLOT_INDEX}/{TG番号}` の形式で送信されます（SLOT_INDEX = スロット番号 − 1）。
