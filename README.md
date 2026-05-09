<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>TGIFChanger for OpenCCVoice &amp; WPSD/Pi-Star</title>
</head>
<body style="font-family: sans-serif; line-height: 1.6; color: #333;">

<h1>TGIFChanger (for OpenCCVoice &amp; WPSD/Pi-Star)</h1>

<p><strong>Version v1.2.2 (Dynamic Network Tracking Edition)</strong></p>

<p>
TGIFChanger は、MMDVM（Pi-Star / WPSD）環境において
TGIF ネットワークの運用を自動化・高度化するためのツールセットです。<br>
Arduino ベースの音声ガイダンスシステム OpenCCVoice との
物理連携を前提に設計されています。
</p>

<hr>

<h2>💡 ユースケース: デジピーター運用におけるダイナミックTGの戻し忘れ防止</h2>

<p>
本システムは、デジピーターとして広域ネットワーク（TGIF等）に常時接続し、地域の待機チャンネル（ホームTG）を維持する装置に最適です。
</p>

<p>
<code>DMRGateway</code> にて <code>PassAll</code> (<code>PassAllPC1=2</code> / <code>PassAllTG1=2</code> など) を有効にすることで、ユーザーは無線機のダイヤル操作のみで世界中の任意のTGへ一時的（ダイナミック）に接続して交信を楽しむことができます。<br>
しかし、交信終了後にTGを戻し忘れると、本来の待ち受けTG（ホームTG）のトラフィックがローカルに降りてこなくなるという「戻し忘れ」問題が発生します。
</p>

<p>
本ツールは、通信終了を自動検知し、指定時間（デフォルト120秒）後に自動でホームTG（<code>TGRewrite</code> で固定したTG）へ強制復帰させます。これにより、管理者の手を煩わせることなく、デジピーターを常に正しい待機状態に保つことができます。
</p>

<hr>

<h2>🌟 主な機能</h2>

<h3>TGIF Changer (tg_change)</h3>
<p>
DMRGateway の設定から DMR ID を自動取得し、
コマンドライン操作で TGIF のトークグループを即時に切り替えます。
</p>

<h3>Auto TG Restore (auto_tg_restore)</h3>
<p>
通信終了から指定秒数（デフォルト 120 秒）後、
自動的にホーム TG へ復帰します。<br>
v1.2.1 以降では、ホーム TG 番号を
<code>/etc/mmdvmhost</code> の TGRewrite 設定から自動取得・追従します。
</p>

<h3>GPIO Bridge (log_monitor)</h3>
<p>
指定 TG の受信状態をリアルタイムで監視します。
受信中は Raspberry Pi の GPIO17 を HIGH 出力し、
外部機器へ状態を通知します。<br>
v1.2.1 以降では、監視対象 TG 番号も
<code>/etc/mmdvmhost</code> から自動取得・追従します。
</p>

<hr>

<h2>🆕 v1.2.2 の主な変更点</h2>

<ul>
    <li>
        <strong>Dynamic Network Tracking (動的追従)</strong>
        <ul>
            <li><code>/etc/mmdvmhost</code> から TGIF ネットワーク設定を自動検出</li>
            <li><code>TGRewrite</code> 設定から監視 TG および復帰 TG を動的に取得</li>
            <li>DMR Network 番号（Network 4など）の変更の影響を受けない設計</li>
        </ul>
    </li>
    <li>
        <strong>GPIO 制御の堅牢化</strong>
        <ul>
            <li><code>libgpiod v2</code>（Bookworm / WPSD）に完全対応</li>
            <li>旧環境向けに <code>libgpiod v1</code> / <code>sysfs</code> へ自動でフォールバック</li>
        </ul>
    </li>
    <li>
        <strong>スマート復帰制御</strong>
        <ul>
            <li>ホーム TG または監視 TG で通信終了した場合、不要なタイマー起動（復帰処理）を自動抑止</li>
        </ul>
    </li>
    <li>
        <strong>長期運用向け改善</strong>
        <ul>
            <li><code>flock</code> による多重起動の完全防止</li>
            <li>ログファイルの日付ローテーション（日跨ぎ）への自動追従</li>
        </ul>
    </li>
</ul>

<hr>

<h2>🛠 システム概要</h2>

<p>
MMDVMHost が出力するログを <code>tail -F</code> によりリアルタイム監視し、
特定のログ行をトリガとして各処理を実行する軽量なイベント駆動型アーキテクチャです。<br>
GPIO 出力は OpenCCVoice 側の TM BUSY 入力
（Arduino Nano の D11）へ接続する想定です。
</p>

<hr>

<h2>📋 接続仕様</h2>

<table border="1" style="border-collapse: collapse; text-align: left; margin-bottom: 15px;">
    <thead>
        <tr style="background-color: #f2f2f2;">
            <th style="padding: 8px;">Raspberry Pi</th>
            <th style="padding: 8px;">Arduino Nano</th>
            <th style="padding: 8px;">役割</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td style="padding: 8px;"><strong>GPIO17 (Pin 11)</strong></td>
            <td style="padding: 8px;"><strong>D11</strong></td>
            <td style="padding: 8px;">TG 受信状態 (High: 受信中 / Low: 待機)</td>
        </tr>
        <tr>
            <td style="padding: 8px;"><strong>GND (Pin 9)</strong></td>
            <td style="padding: 8px;"><strong>GND</strong></td>
            <td style="padding: 8px;">共通接地 (Common Ground)</td>
        </tr>
    </tbody>
</table>

<p><strong>⚠️ 注意点:</strong></p>
<ul>
    <li>Raspberry Pi の GPIO は <strong>3.3V 出力</strong> です</li>
    <li>Arduino 側は必ず <strong>INPUT モード</strong> で使用してください</li>
</ul>

<hr>

<h2>🚀 導入手順</h2>

<p>Raspberry Pi に SSH ログインし、以下のコマンドを実行してください。</p>

<pre style="background-color: #f4f4f4; padding: 12px; border-radius: 5px; overflow-x: auto;"><code>rpi-rw
curl -L https://raw.githubusercontent.com/ji2tab/TGIFChanger/main/install.sh | bash</code></pre>

<p><em>(※ <code>rpi-rw</code> は Pi-Star 環境でのみ必要です。WPSD では不要です。)</em></p>

<hr>

<h2>⚙️ 設定ファイル</h2>

<p>設定は <code>/etc/tgifchanger.conf</code> に集約されています。</p>

<pre style="background-color: #f4f4f4; padding: 12px; border-radius: 5px; overflow-x: auto;"><code>LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
GPIO_PIN="17"
GPIO_BACKEND="auto"
GPIO_CHIP="0"
RESTORE_DELAY="120"
RESTORE_SLOT="2"</code></pre>

<p>設定変更後は、以下のコマンドでサービスを再起動して反映させてください。</p>

<pre style="background-color: #f4f4f4; padding: 12px; border-radius: 5px; overflow-x: auto;"><code>sudo systemctl restart log_monitor auto_tg_restore</code></pre>

<hr>

<h2>📄 ライセンス</h2>

<p>
<strong>GPL v3</strong><br>
OpenCCVoice プロジェクトの理念に基づき、オープンソースとして公開しています。
</p>

<hr>

<h2>👤 作者</h2>

<p>
<strong>篠田 一彦 / Kazuhiko Shinoda (JI2TAB)</strong><br>
愛知県尾張旭市 (Owariasahi City, Aichi, Japan)<br>
Aichi Digital Communication Ham Club (JJ2YYK) 管理人
</p>

<hr>

<h2>🤝 Special Thanks</h2>

<ul>
    <li>OpenCCVoice Project Contributors</li>
    <li>WPSD and Pi-Star Developers</li>
    <li>MMDVM Community</li>
</ul>

</body>
</html>
