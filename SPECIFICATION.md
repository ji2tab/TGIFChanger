<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>TGIFChanger 技術仕様書 proto-1.0.0</title>
</head>
<body>

<h1>TGIFChanger 技術仕様書</h1>

<p>
<strong>Version:</strong> proto-1.0.0<br>
<strong>Author:</strong> Kazuhiko Shinoda (JI2TAB)<br>
<strong>License:</strong> GPL v3
</p>

<hr>

<h2>改訂履歴</h2>

<table border="1">
    <thead>
        <tr>
            <th>版</th>
            <th>内容</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1.0 (初版)</td>
            <td>オリジナル版仕様書（sysfs / TG1固定 / Restart=always / /home/pi-star/scripts）</td>
        </tr>
        <tr>
            <td>proto-1.0.0</td>
            <td>
                プロト版として全面改訂。
                共通設定ファイル導入、libgpiod対応、ログファイル日付追従、
                PID追跡改善、WATCH_TG設定可変化、
                配置先 /opt/tgifchanger/ 等。
            </td>
        </tr>
    </tbody>
</table>

<hr>

<h2>0. はじめに</h2>

<p>
本書は、MMDVM（Pi-Star / WPSD）環境向け
トークグループ自動化ツール「TGIFChanger」の
プロト版（proto-1.0.0）における技術仕様を定める。
</p>

<p>
本ツールセットは、Arduino ベースの音声ガイダンスシステム
「OpenCCVoice」との物理的な連携を前提として設計されている。
</p>

<p>
Raspberry Pi の GPIO 出力を OpenCCVoice 側の TM BUSY 入力に直結することにより、
DMR 受信状態に応じた音声ガイダンス制御を、
ソフトウェアプロトコルを介さず物理層で確実に実現することを目的とする。
</p>

<p>
本仕様書はオリジナル版仕様書を全面改訂したものであり、
proto-1.0.0 で導入された各種改良事項を
絶対仕様として記述する。
</p>

<hr>

<h2>1. システムアーキテクチャ</h2>

<p>
本システムは、MMDVMHost が生成するログファイルをイベントソースとし、
Bash スクリプト群が systemd 配下のデーモンとして動作する
軽量なイベント駆動型アーキテクチャを採用する。
</p>

<p>
OS の標準機能（systemd, sysfs, libgpiod）を最大限活用し、
独自のメッセージブローカーや常駐データベースを必要としない。
</p>

<h3>1.1 システム構成図</h3>

<pre><code>
（原文の ASCII アート構成図をそのまま保持）
</code></pre>

<h3>1.2 構成要素</h3>

<table border="1">
    <thead>
        <tr>
            <th>要素</th>
            <th>役割</th>
            <th>実行形態</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>log_monitor</td>
            <td>MMDVMHost ログを監視し、特定TG受信時に GPIO を制御</td>
            <td>systemd 常駐</td>
        </tr>
        <tr>
            <td>auto_tg_restore</td>
            <td>通信終了後に自動的にホームTGへ復帰</td>
            <td>systemd 常駐</td>
        </tr>
        <tr>
            <td>tg_change</td>
            <td>TGIF API を呼び出して TG を即時変更</td>
            <td>オンデマンド</td>
        </tr>
        <tr>
            <td>/etc/tgifchanger.conf</td>
            <td>共通設定ファイル</td>
            <td>テキスト</td>
        </tr>
    </tbody>
</table>

<h3>1.3 ファイル配置</h3>

<p>
proto-1.0.0 では FHS に基づき、
実行ファイルを /opt/tgifchanger/ に集約する。
</p>

<p>
オリジナル版で使用していた /home/pi-star/scripts/ は使用せず、
1 製品 1 ディレクトリとする。
</p>

<hr>

<h2>2. ソフトウェア詳細仕様</h2>

<h3>2.1 log_monitor</h3>

<p>
MMDVMHost ログをリアルタイムで監視し、
指定 TG の受信状態を Raspberry Pi GPIO へ反映する。
</p>

<p>
GPIO 制御は libgpiod を優先し、
未対応環境では sysfs に自動フォールバックする。
</p>

<h3>2.2 auto_tg_restore</h3>

<p>
通信終了イベントを契機として復帰タイマーを起動し、
満了時に tg_change を呼び出す。
</p>

<p>
proto-1.0.0 ではプロセス置換を用い、
PID 追跡不能問題を根本的に解消した。
</p>

<pre><code>
exec 3< <(tail -n 0 -F "$current_file")
while read -r -t 5 line <&3; do
    # 親シェルで処理
done
</code></pre>

<h3>2.3 tg_change</h3>

<p>
TGIF Network の HTTP API を呼び出して
トークグループ切替を行う CLI ツールである。
</p>

<hr>

<h2>6. メンテナンスとデバッグ</h2>

<pre><code>
journalctl -u log_monitor -f
journalctl -u auto_tg_restore -f
</code></pre>

<hr>

<h2>7. 動作環境</h2>

<table border="1">
    <thead>
        <tr>
            <th>項目</th>
            <th>対応内容</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>ハードウェア</td>
            <td>Raspberry Pi Zero 2 W / 3 / 4 / 5</td>
        </tr>
        <tr>
            <td>OS</td>
            <td>Pi-Star / WPSD</td>
        </tr>
        <tr>
            <td>Bash</td>
            <td>5.0 以上</td>
        </tr>
    </tbody>
</table>

<hr>

<h2>著作・ライセンス</h2>

<p>
ライセンス: GPL v3
</p>

<p>
著作: 篠田 一彦 / Kazuhiko Shinoda (JI2TAB)<br>
Owariasahi City, Aichi, Japan<br>
Aichi Digital Communication Ham Club (JJ2YYK)
</p>

</body>
</html>
