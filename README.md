TGIFChanger (for OpenCCVoice & WPSD/Pi-Star)Version v1.2.1 (Dynamic Network Tracking Edition)MMDVM (Pi-Star / WPSD) 環境において、TGIFネットワークの運用を自動化・高度化するためのツールセットです。特に、Arduinoベースの音声ガイダンスシステム 「OpenCCVoice」 との物理連携を想定して設計されています。🌟 主な機能1. TGIF Changer (tg_change)DMRGateway の設定から DMR ID を自動取得し、コマンドラインから TGIF のトークグループを瞬時に切り替えます。2. Auto TG Restore (auto_tg_restore)通信終了から指定秒数（デフォルト120秒）後、自動的にホーム TG へ復帰させます。戻し忘れを防止します。【新機能】 ホームTGの番号は /etc/mmdvmhost の TGRewrite 設定から自動追従します。3. GPIO Bridge (log_monitor)指定 TG の受信ステータスをリアルタイム監視。受信中は Raspberry Pi の GPIO17 を HIGH 出力し、外部機器へステータスを伝達します。【新機能】 監視対象のTG番号も /etc/mmdvmhost から自動で取得・追従します。🆕 v1.2.1 での主な進化（プロト版からの改良）🌐 完全な自動追従 (Dynamic Network Tracking):/etc/mmdvmhost 内から Address=tgif.network を含むセクションを自動で探し出し、監視対象TGと復帰先TGを TGRewrite の値から動的に抽出します。DMR Network の割り当て番号（Network 2, 4, 5など）が変わっても、設定変更なしで追従します。⚡ GPIO制御の堅牢化 (libgpiod v1/v2 Auto-Detect):最新の Pi-Star (Bookworm) や WPSD で採用されている libgpiod v2 の厳格な仕様に完全対応。旧 OS の v1 や sysfs にも自動判定でフォールバックし、あらゆる環境で確実に電圧を出力します。🧠 スマートな復帰除外ロジック:ホームTGや監視対象TGで通信が終了した場合は、不要な復帰タイマーを起動しないよう最適化されました。🧹 クリーンなバックグラウンド処理:プロセス置換や flock による多重起動防止など、長期間の連続稼働に耐えうる堅牢なデーモン設計に移行しました。🛠 システムの仕組みMMDVMHost が書き出すログファイルを tail -F でリアルタイム監視し、特定の文字列をトリガーに動作します。GPIO 出力は物理的な信号として、OpenCCVoice（Arduino Nano 等）の D11 ピン（TM BUSY 入力）へ直接接続して使用することを想定しています。📋 接続仕様 (Hardware Connection)Raspberry Pi と Arduino を以下の通り接続してください。Raspberry Pi (物理ピン)Arduino Nano (ピン)役割Pin 11 (GPIO17)D11TG受信信号 (High: 受信中 / Low: 待機)Pin 9 (GND)GND共通接地 (Common Ground)⚠️ 注意Raspberry Pi の GPIO は 3.3V レベルです。Arduino（5V系）へ入力する場合は、Arduino 側を INPUT モードで使用してください。🚀 導入手順 (Installation)Pi-Star / WPSD に SSH でログインし、以下のコマンドを実行してください。Bashrpi-rw   # Pi-Star のみ（書き込み許可）。WPSDは不要です。
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash
このスクリプトを実行すると、以下の処理が自動で行われます。/opt/tgifchanger/ への各スクリプト配置/etc/tgifchanger.conf の配置/usr/local/bin/tg_change シンボリックリンク作成systemd へのサービス登録と自動起動⚙️ 設定ファイル (/etc/tgifchanger.conf)TG の番号は自動取得されるため、ユーザー設定は非常にシンプルです。Bash# 基本設定
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"

# GPIO設定 (WPSD / Bookworm / Pi-Star 4.3.x 用)
GPIO_PIN="17"
GPIO_BACKEND="libgpiod"
GPIO_CHIP="0"

# 自動復帰設定
RESTORE_DELAY="120"     # 通信終了から復帰までの秒数
RESTORE_SLOT="2"
設定変更後はサービス再起動が必要です:Bashsudo systemctl restart log_monitor auto_tg_restore
⚙️ 管理コマンド状態確認とログ監視Bashsystemctl status log_monitor
journalctl -u log_monitor -f

systemctl status auto_tg_restore
journalctl -u auto_tg_restore -f
(※ journalctl -u log_monitor -u auto_tg_restore -f で両方の連携を同時に監視できます)手動 TG 切替PATH 上から直接実行可能です:Bashtg_change -168          # スロット1 を TG168 に
tg_change -168:2        # スロット2 を TG168 に
🧩 OpenCCVoice 連携本システムは、OpenCCVoice 側の TM BUSY 入力を利用し、TG 受信状態に応じた音声ガイダンス制御を行うために設計されています。TG 受信中は CW 送出禁止ガイダンス再生抑止通信中アナウンス制御などの高度な物理連携が可能です。🖥 対応環境Hardware: Raspberry Pi シリーズ（Zero 2 W / 3 / 4 / 5）OS: - Pi-Star V4.2.3 / V4.3.x (Bullseye / Bookworm)WPSD (64-bit)Dependencies: MMDVMHost / DMRGateway📄 ライセンスGPL v3(OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開します)👤 作者篠田 一彦 / Kazuhiko Shinoda (JI2TAB)Owariasahi City, Aichi, JapanManager of Aichi Digital Communication Ham Club (JJ2YYK)🤝 Special ThanksOpenCCVoice Project ContributorsWPSD & Pi-Star DevelopersMMDVM Community
