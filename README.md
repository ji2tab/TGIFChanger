<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>TGIFChanger for OpenCCVoice &amp; WPSD/Pi-Star</title>
</head>
<body>

<h1>TGIFChanger (for OpenCCVoice &amp; WPSD/Pi-Star)</h1>

<p><strong>Version v1.2.1 (Dynamic Network Tracking Edition)</strong></p>

<p>
TGIFChanger は、MMDVM（Pi-Star / WPSD）環境において
TGIF ネットワークの運用を自動化・高度化するためのツールセットです。
</p>

<p>
Arduino ベースの音声ガイダンスシステム OpenCCVoice との
物理連携を前提に設計されています。
</p>

<hr>

<h2>主な機能</h2>

<h3>TGIF Changer (tg_change)</h3>

<p>
DMRGateway の設定から DMR ID を自動取得し、
コマンドライン操作で TGIF のトークグループを即時に切り替えます。
</p>

<h3>Auto TG Restore (auto_tg_restore)</h3>

<p>
通信終了から指定秒数（デフォルト 120 秒）後、
自動的にホーム TG へ復帰します。
</p>

<p>
v1.2.1 以降では、ホーム TG 番号を
<code>/etc/mmdvmhost</code> の TGRewrite 設定から自動取得・追従します。
</p>

<h3>GPIO Bridge (log_monitor)</h3>

<p>
指定 TG の受信状態をリアルタイムで監視します。
受信中は Raspberry Pi の GPIO17 を HIGH 出力し、
外部機器へ状態を通知します。
</p>

<p>
v1.2.1 以降では、監視対象 TG 番号も
<code>/etc/mmdvmhost</code> から自動取得・追従します。
</p>

<hr>

<h2>v1.2.1 の主な変更点</h2>

<ul>
    <li>
        Dynamic Network Tracking
        <ul>
            <li>/etc/mmdvmhost から TGIF ネットワーク設定を自動検出</li>
            <li>TGRewrite 設定から監視 TG および復帰 TG を動的に取得</li>
            <li>DMR Network 番号変更の影響を受けない設計</li>
        </ul>
    </li>
    <li>
        GPIO 制御の堅牢化
        <ul>
            <li>libgpiod v2（Bookworm / WPSD）対応</li>
            <li>旧環境向けに libgpiod v1 / sysfs へ自動フォールバック</li>
        </ul>
    </li>
    <li>
        スマート復帰制御
        <ul>
            <li>ホーム TG または監視 TG で通信終了した場合、復帰処理を抑止</li>
        </ul>
    </li>
    <li>
        長期運用向け改善
        <ul>
            <li>flock による多重起動防止</li>
            <li>ログ日付ローテーションへの自動追従</li>
        </ul>
    </li>
</ul>

<hr>

<h2>システム概要</h2>

<p>
MMDVMHost が出力するログを tail -F によりリアルタイム監視し、
特定のログ行をトリガとして各処理を実行します。
</p>

<p>
GPIO 出力は OpenCCVoice 側の TM BUSY 入力
（Arduino Nano の D11）へ接続する想定です。
</p>

<hr>

<h2>接続仕様</h2>

<table border="1">
    <thead>
        <tr>
            <th>Raspberry Pi</th>
            <th>Arduino Nano</th>
            <th>役割</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>GPIO17 (Pin 11)</td>
            <td>D11</td>
            <td>TG 受信状態</td>
        </tr>
        <tr>
            <td>GND (Pin 9)</td>
            <td>GND</td>
            <td>共通接地</td>
        </tr>
    </tbody>
</table>

<p>注意点:</p>

<ul>
    <li>Raspberry Pi の GPIO は 3.3V 出力です</li>
    <li>Arduino 側は INPUT モードで使用してください</li>
</ul>

<hr>

<h2>導入手順</h2>

<pre>
rpi-rw
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash
</pre>

<p>
Pi-Star 環境では rpi-rw が必要です。
WPSD では不要です。
</p>

<hr>

<h2>設定ファイル</h2>

<p>設定は <code>/etc/tgifchanger.conf</code> に集約されています。</p>

<pre>
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
GPIO_PIN="17"
GPIO_BACKEND="libgpiod"
GPIO_CHIP="0"
RESTORE_DELAY="120"
RESTORE_SLOT="2"
</pre>

<p>設定変更後はサービスを再起動してください。</p>

<pre>
sudo systemctl restart log_monitor auto_tg_restore
</pre>

<hr>

<h2>ライセンス</h2>

<p>
GPL v3<br>
OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開しています。
</p>

<hr>

<h2>作者</h2>

<p>
篠田 一彦 / Kazuhiko Shinoda (JI2TAB)<br>
愛知県尾張旭市<br>
Aichi Digital Communication Ham Club (JJ2YYK)
</p>

<hr>

<h2>Special Thanks</h2>

<ul>
    <li>OpenCCVoice Project Contributors</li>
    <li>WPSD and Pi-Star Developers</li>
    <li>MMDVM Community</li>
</ul>

</body>
</html>
