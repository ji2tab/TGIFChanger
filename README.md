# TGIFChanger-Py (for OpenCCVoice & WPSD/Pi-Star)

**Version v2.3.1 (Python 3 Unified Daemon & Smart Installer Edition)**

TGIFChanger-Py は、MMDVM（Pi-Star / WPSD）環境においてTGIFネットワークの運用を自動化・高度化するためのツールセットです。
Arduinoベースの音声ガイダンスシステム「OpenCCVoice」との物理連携（GPIO制御）を前提に設計されています。

従来のシェルスクリプト版（v1.x）から **Python 3 ネイティブデーモンへと完全フルスクラッチ（v2.x）** され、WPSDのシステムに一切の負荷をかけない圧倒的な軽さと、極めて強固な安定性を実現しました。

---

## ユースケース: デジピーター運用におけるダイナミックTGの戻し忘れ防止

本システムは、デジピーターとして広域ネットワークに常時接続し、地域の待機チャンネル（ホームTG）を維持する装置に最適です。

`DMRGateway` にて `PassAll` を有効にすることで、ユーザーは無線機のダイヤル操作のみで世界中の任意のTGへ一時的（ダイナミック）に接続して交信を楽しめます。しかし、交信終了後にTGを戻し忘れると、本来の待ち受けTG（ホームTG）のトラフィックがローカルに降りてこなくなるという「戻し忘れ」問題が発生します。

本ツールは、MMDVMのログから通信状態をインメモリでリアルタイムに解析し、通信終了から指定時間（デフォルト 120秒）後に自動でホームTGへ強制復帰させます。

---

## 🚀 v2.3.1 の進化ポイント (旧シェルスクリプト版からの改善)

### 1. Python 3 統合デーモンによる圧倒的な低負荷

- 従来の `tail -F` や `grep` によるプロセス生成（Fork）を廃止。メモリ上のログを直接解析することで、Raspberry Pi Zero 等の非力な環境でもCPU負荷をほぼゼロに抑えました。
- WPSDの頻繁なログローテーション（RAMディスク上のi-node変更）にも、パイプ詰まりを起こすことなく瞬時に追従します。

### 2. 正確なタイマー管理とAPI連打の防止

- 安全なインメモリタイマースレッドを実装。ネットワークの瞬断時でも、TGIF APIへの復帰リクエスト（HTTP）の二重送信や連打を完全に防ぎます。

### 3. 究極のGPIOエンジン (ハイブリッド対応)

- `libgpiod` v1/v2、`pinctrl`、`raspi-gpio`、`sysfs` を自動判定するハイブリッドエンジンを搭載。
- 最新の Raspberry Pi 5 (Bookworm) から従来の Pi-Star (Buster) まで、環境を問わず安定してGPIOピンを駆動します。
- **フェイルセーフ機能搭載**: 万が一終了ログを取りこぼしても、最大120秒で強制的にGPIOをLOWに落とす安全装置が働きます。

### 4. Unixドメインソケット (UDS) とホットリロード

- CLIツールとデーモン間の通信にUDSを採用。デーモンを再起動することなく、コマンドラインから設定（監視TGや復帰時間）を即座に変更・反映できます。

---

## システム概要と接続仕様

MMDVMHost が出力するログをリアルタイムで監視し、受信状態に応じてRaspberry PiのGPIOピンを制御します。GPIO出力はOpenCCVoice側の TM BUSY 入力（Arduino Nano の D11）へ接続する想定です。

| Raspberry Pi | Arduino Nano | 役割 |
|---|---|---|
| GPIO17 (Pin 11) | D11 | TG 受信状態 (High: 受信中 / Low: 待機) |
| GND (Pin 9) | GND | 共通接地 (Common Ground) |

> **注意:**
> Raspberry Pi の GPIO は **3.3V 出力** です。
> Arduino 側は必ず **INPUT モード** で使用してください。

### GPIO出力の動作条件

GPIO17 への信号出力は、設定した **監視TG（WATCH_TG）と一致するTGの受信時のみ** 発生します。
例えば TG1 で待ち受けている場合、TG1 の通信を受信したときだけ GPIO17 が HIGH（3.3V）になり、OpenCCVoice 等の外部装置へ起動信号が送られます。
他のTGの通信はスルーされ、GPIO は反応しません。また、**自局コールサインからの送信は除外**されるため、自分の送信中に誤って信号が出ることもありません。

---

## 導入手順 (インストール)

Raspberry Pi (Pi-Star または WPSD) に SSH でログインし、以下のコマンドを実行してください。
※ `rpi-rw` (書き込み可能モードへの変更) や旧バージョンのクリーンアップは、インストーラーが自動で行います。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | sudo bash
```

### 💡 対話型セットアップ (新規インストール時)

新規インストールの場合、インストール中にプロンプトが一時停止し、「監視TG」「復帰TG」「復帰までの時間」 を対話形式で入力できます。
（DMRGatewayの TGRewrite 設定が存在する場合は、そこから自動的にデフォルト値を抽出して提案します）

---

## 運用コマンド (CLIツール)

システムは統合された tg_change コマンドで操作します。

### 1. ステータスとログの確認

```bash
# デーモンの稼働状況、現在のタイマー、GPIO状態をJSONで確認
tg_change --status

# リアルタイム動作ログの監視
journalctl -u tgifchanger-py -f
```

### 2. 手動での TG 切り替え (即時送信)

```bash
# スロット1を TG168 に変更
tg_change -168

# スロット2を TG168 に変更
tg_change -168:2
```

### 3. デーモン操作と設定変更 (root権限必須)

設定を変更すると、デーモンへ自動で設定リロード (Hot Reload) がかかるため、サービスの再起動は不要です。

```bash
# 動作中の自動復帰タイマーをキャンセル
tg_change --cancel

# 監視TG (WATCH_TG) を変更
sudo tg_change -w 168

# 復帰TG (RESTORE_TG) を変更
sudo tg_change -r 44833

# 復帰までの待機時間 (秒) を変更
sudo tg_change -t 90

# 現在の設定一覧を確認
tg_change -c
```

---

## 設定ファイル

設定は `/etc/tgifchanger.conf` に集約されています。

※CLIツール (`sudo tg_change -w` 等) を使わずに、`nano` コマンド等で手動編集した場合は、デーモンに設定を読み込ませるために以下のコマンドでサービスを再起動してください。

```bash
sudo systemctl restart tgifchanger-py
```

---

## 削除手順 (アンインストール)

システムから TGIFChanger のプログラム本体、サービス、設定ファイルをすべて跡形もなく完全に削除する場合は、以下のコマンドを実行してください。
※ 書き込み制限の解除 (`rpi-rw`) も自動で行われます。

```bash
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/uninstall.sh | sudo bash
```

---

## ライセンス

**GPL v3**

OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開しています。

---

## 作者

**篠田 一彦 / Kazuhiko Shinoda (JI2TAB)**  
愛知県尾張旭市 (Owariasahi City, Aichi, Japan)  
Aichi Digital Communication Ham Club (JJ2YYK) 管理人

### Special Thanks

- OpenCCVoice Project Contributors
- WPSD and Pi-Star Developers
- MMDVM Community
