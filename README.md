
## 1. README.md 案（リポジトリの顔）

Readmeは、「何ができるか」「どうやって入れるか」を1ページで把握できるように構成します。

```markdown
# TGIFChanger (for OpenCCVoice & WPSD)

MMDVM(WPSD/Pi-Star)とArduinoベースの音声ガイダンス「OpenCCVoice」を連携させ、TGIFネットワークの運用を劇的に便利にするツール群です。

## 🌟 主な機能
1. **TGIF Changer**: コマンドラインから瞬時にTGIFのトークグループを切り替え。
2. **Auto TG Restore**: 通信終了から120秒後に、自動的に指定のホームTGへ復帰（戻し忘れ防止）。
3. **GPIO Bridge (log_monitor)**: TG1受信中にRaspberry PiのGPIO17をHIGH出力。OpenCCVoice(Arduino)と連動し、受信ステータスを可視化・制御。

## 🛠 仕組み
MMDVMのログファイルをリアルタイムに監視し、特定のイベント（受信開始/終了/TG番号）を検知して動作します。GPIO出力は物理的な信号としてArduinoのD11ピンへ送られ、OpenCCVoice側で「Busy信号」として処理されます。

## 🚀 導入手順（クイックスタート）
Pi-Star/WPSDにログインし、以下のコマンドを実行してください。

```bash
rpi-rw
curl -L [https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh](https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh) | bash

```

## 📋 接続仕様 (Hardwire)

* **Raspberry Pi 物理11番(GPIO 17)** ─── **Arduino D11**
* **Raspberry Pi 物理 9番(GND)** ─── **Arduino GND**

## 📄 ライセンス

GPL v3 (OpenCCVoiceプロジェクトに準ずる)

```

---

## 2. 詳細仕様書案（wikiやdocsディレクトリ用）

別途作成する仕様書には、**「なぜその設計なのか」「トラブル時の確認方法」**を詳しく記述します。

### 構成案

#### ## ソフトウェアスタック
* **言語**: Bash Script (Linux標準)
* **依存ツール**: `curl`, `sed`, `awk`, `grep`, `tail`, `bc`, `libgpiod` (または sysfs)
* **動作確認済み環境**: WPSD (Raspberry Pi OSベース), Pi-Star

#### ## 動作詳細 (Mechanism)
1.  **log_monitor (Ver 1.2.2)**
    * `/var/log/pi-star/` 配下の最新のMMDVMログを `tail -f` でオープン。
    * `received voice header` 検知時、対象が **TG1** かつ **Slot 2** であれば `/sys/class/gpio/gpio17/value` を `1` に書き込み。
    * `end of voice transmission` 検知時に `0` にリセット。
2.  **auto_tg_restore**
    * 通信終了イベントから120秒のタイマー（バックグラウンドPID管理）を開始。
    * タイマー動作中に新たな通信があれば、既存のPIDを `kill` してタイマーをリセット。

#### ## ハードウェア・インターフェース
* **ロジック電圧**: 3.3V CMOS
* **信号特性**: Active High（TG1受信中に3.3Vを継続出力）
* **絶縁**: なし（PiとArduinoのGNDを共通にする必要あり。より安全な運用にはフォトカプラの使用を推奨）

#### ## トラブルシューティング
* **GPIOが動かない**: `ls /sys/class/gpio/gpio17` が存在するか確認。
* **サービスが動かない**: `systemctl status log_monitor` でエラーメッセージを確認。
* **APIが通らない**: `/etc/dmrgateway` 内に `[DMR Network 4]` の記述があり、かつ正しいDMR IDが記載されているか確認。

---

### アドバイス：詳細仕様書の管理場所
GitHubであれば、リポジトリの **「Wiki」** 機能を使うか、リポジトリ内に **`docs/`** というフォルダを作って、そこに `specification.md` という名前で保存するのが一般的です。

これらをGitHubに配置するための手順や、さらに肉付けしたい技術的な詳細はありますか？

```
