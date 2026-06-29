# tgif_daemon.py ソフトウェア仕様書

**ファイル:** `tgif_daemon.py`
**バージョン:** v2.3.4
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py のメインデーモンです。MMDVM ログを常時監視し、DMR トークグループの変化を検出して TGIF API への自動復帰リクエストと GPIO 出力制御を行います。systemd によって管理され、`tg_change` CLI ツールからは Unix ドメインソケット経由で制御されます。

### v2.3.4 での変更点

コールサイン・ウォッチドッグ（真の利用者監視）を追加:

- 他TGへ **RF（自局側）でキーアップした最後の局** を「真の利用者」として記録・追跡（`tracked_call` / `away_tg` / `rf_deadline`）
- 追跡対象局の RF が `CALLSIGN_TIMEOUT` 秒（既定 300）確認できなければ、ネット側の通話が続いていても `RESTORE_TG` へ強制復帰
- network 受信（リモート通話）はカウント対象外（`received RF voice header` のみを RF アクセスとして扱う）
- 別の局が RF キーアップすると追跡対象を切り替え
- `CALLSIGN_TIMEOUT="0"` で本機能を無効化（従来の `RESTORE_DELAY` のみで動作）
- `status` の JSON に `callsign_timeout` / `tracked_call` / `away_tg` フィールドを追加

### v2.3.3 での変更点

logrotate 等によるログ消失・切替瞬間のレースコンディションを修正:

- `get_latest()` が空を返した場合、現ファイルを維持したまま次ループへ継続
- `os.stat()` での `FileNotFoundError` / `PermissionError` を捕捉・無視し、現ファイルを掴んだまま次ループで再検知を待つ

---

## 2. 定数

| 定数 | 値 | 説明 |
|------|----|------|
| `VERSION` | `v2.3.4` | デーモンバージョン（`status` コマンドで返される） |
| `CONF_FILE` | `/etc/tgifchanger.conf` | 設定ファイルパス |
| `MMDVM_CONF` | `/etc/mmdvmhost` | MMDVMHost 設定ファイルパス |
| `DMRGW_CONF` | `/etc/dmrgateway` | DMRGateway 設定ファイルパス |
| `LOCK_FILE` | `/run/tgifchanger-py.lock` | 多重起動防止ロックファイル |
| `CMD_SOCKET` | `/run/tgifchanger-py.sock` | CLI 制御用 Unix ドメインソケット |
| `LOG_PATTERN` | `MMDVM-*.log` | 監視対象ログファイルのグロブパターン |
| `GPIO_FAILSAFE_SEC` | `120` | GPIO HIGH 状態の上限秒数（フェイルセーフ） |

---

## 3. デフォルト設定値

`config` 辞書の初期値。`/etc/tgifchanger.conf` が読み込まれると上書きされます。

| キー | デフォルト値 | 説明 |
|------|------------|------|
| `LOG_DIR` | `/var/log/pi-star` | MMDVM ログファイルのディレクトリ |
| `WATCH_SLOT` | `2` | 監視対象の DMR タイムスロット番号 |
| `RESTORE_SLOT` | `2` | 復帰操作に使用するタイムスロット番号 |
| `WATCH_TG` | `""`（空） | 監視対象 TG（空時は設定ファイルから動的取得） |
| `RESTORE_TG` | `""`（空） | 復帰先 TG（空時は設定ファイルから動的取得） |
| `GPIO_PIN` | `17` | GPIO 出力ピン番号（BCM 番号体系） |
| `GPIO_CHIP` | `auto` | libgpiod 使用時の gpiochip 番号 |
| `GPIO_BACKEND` | `auto` | GPIO 制御バックエンド |
| `RESTORE_DELAY` | `120` | 通話終了後、復帰するまでの待機時間（秒） |
| `CALLSIGN_TIMEOUT` | `300` | 真の利用者（RFアクセス局）を確認できなくなってから強制復帰するまでの秒数。`0` で無効 |
| `TGIF_API` | `http://tgif.network:5040/api/sessions/update` | TGIF セッション更新 API エンドポイント |
| `TGIF_API_TIMEOUT` | `10` | TGIF API 呼び出しのタイムアウト（秒） |

---

## 4. 起動シーケンス（`App.run()`）

```
1. load_config()         設定ファイル読み込み
2. GPIOEngine 初期化     バックエンド自動選択・ピン出力設定
3. 多重起動チェック      LOCK_FILE に LOCK_EX|LOCK_NB でロック取得
                         → 失敗時（EWOULDBLOCK 等）は終了コード 1 で終了
4. シグナルハンドラ登録  SIGINT/SIGTERM → 停止、SIGHUP → 設定リロード
5. CmdServer 起動        Unix ドメインソケットを別スレッドで待受開始
6. ログファイル待機      MMDVM-*.log を 0.5 秒間隔で最大 240 回（120 秒）探索
                         → 見つからない場合は終了コード 1 で終了
7. ファイル末尾へシーク  既存ログを読み飛ばして新規行のみを処理対象とする
8. メインループ開始      readline() による行読み取りと process_line() の実行
```

---

## 5. メインループ

0.2 秒間隔でログ行を読み取り、以下を繰り返します。

```
readline() で新規行を取得
  ├─ 行あり → process_line() へ渡す → 先頭に戻る
  └─ 行なし（EOF）
        ├─ fh.seek(fh.tell())  EOFバッファクリア（フリーズ防止）
        ├─ time.sleep(0.2)
        ├─ GPIO フェイルセーフチェック
        ├─ コールサイン・ウォッチドッグ判定（後述 §6.3）
        └─ ログファイル切替チェック（後述）
```

### GPIO フェイルセーフ

GPIO が HIGH 状態のまま `GPIO_FAILSAFE_SEC`（120 秒）を超えた場合、強制的に LOW へリセットします。`high_start` タイムスタンプと現在時刻の差分で判定します。

### ログファイル切替チェック（v2.3.3 強化）

| 状況 | 動作 |
|------|------|
| `glob` 結果が空（logrotate 切替の瞬間） | 現ファイルを維持したまま `continue`（v2.3.3 修正） |
| `os.stat()` で `FileNotFoundError` / `PermissionError` | 無視して `continue`（v2.3.3 修正） |
| ファイル名またはiノード番号が変化 | 0.1 秒待機後に新ファイルをオープンし末尾へシーク |
| 変化なし | 何もせず次ループへ |

---

## 6. ログ解析（`process_line()`）

`WATCH_SLOT` に対応する `Slot N,` マーカーを含まない行は即時スキップします。

### 6.1 `voice header` 検出時

`voice header` 行から `from <コールサイン>`、`to TG <番号>`、および RF/network 種別（`received RF voice header` を含むかで判定）を抽出します。

| 処理 | 条件 |
|------|------|
| 復帰タイマーをキャンセル | 無条件 |
| コールサイン・ウォッチドッグの更新 | §6.3 を参照（自局送信を含む RF キーアップで記録。`my_call` でも記録される） |
| 自局送信の GPIO 除外 | `from <コールサイン>` が `my_call` と一致する場合、以降の GPIO 点灯処理をスキップ（ウォッチドッグ記録は上で完了済み） |
| GPIO を HIGH にセット | `to TG <番号>` が `watch_tg` と一致する場合 |

### 6.2 通話終了系キーワード検出時

対象パターン（正規表現）:

```
end of voice transmission | transmission lost | watchdog has expired
```

| 条件 | 処理 |
|------|------|
| TG が `watch_tg` と一致 | GPIO を LOW にセット |
| TG が取得できず GPIO が HIGH | GPIO を強制 LOW（Signal Lost） |
| TG が `watch_tg` / `restore_tg` いずれでもない | 復帰タイマーをセット（`schedule_restore()`） |
| TG が `watch_tg` または `restore_tg` | タイマーセットをスキップ（ログ出力のみ） |

### 6.3 コールサイン・ウォッチドッグ（v2.3.4）

「真の利用者」＝ `watch_tg` / `restore_tg` 以外のTGへ **RF（自局側）でキーアップした最後の局** を追跡し、その局の RF が一定時間途絶えた場合に強制復帰させる仕組みです。ネット側だけで遠方局の通話が延々と続いてホームTGが奪われ続ける状態を防ぎます。

App が保持する状態:

| 属性 | 初期値 | 内容 |
|------|--------|------|
| `away_tg` | `None` | 現在「離脱（他TG）」中ならその TG 番号。`watch_tg` / `restore_tg` に戻ると `None` |
| `tracked_call` | `""` | 他TGへ最後に RF アクセスした「真の利用者」コールサイン |
| `rf_deadline` | `0.0` | この時刻を過ぎても `tracked_call` の RF が無ければ強制復帰 |

`process_line()` 内の更新ロジック（`voice header` 検出時）:

| 条件 | 動作 |
|------|------|
| TG が `watch_tg` または `restore_tg` | `_clear_away()`（在宅とみなしウォッチドッグ解除） |
| `received RF voice header` かつ TG あり、かつ `CALLSIGN_TIMEOUT > 0` | `tracked_call` を当該局に設定、`rf_deadline = now + CALLSIGN_TIMEOUT`、`away_tg = TG`。既存追跡局と異なる場合は「対象切替」としてログ |
| network 受信（リモート通話） | 記録しない（カウント対象外） |

メインループ（EOF 時）の判定:

```
if away_tg かつ rf_deadline かつ now > rf_deadline:
    cancel_timer()
    _do_restore()   # 内部で _clear_away() される
```

`CALLSIGN_TIMEOUT="0"` の場合、上記の記録・判定は行われず本機能は無効になります。`_clear_away()` は `away_tg` / `tracked_call` / `rf_deadline` を初期化するヘルパで、`_do_restore()` 成功後にも呼ばれます。

---

## 7. 自動復帰タイマー

### スケジューリング（`schedule_restore()`）

1. 既存タイマーがあればキャンセル（`cancel_timer()`）
2. `RESTORE_DELAY` 秒後に `_do_restore()` を実行する `threading.Timer` を作成
3. タイマーはデーモンスレッドとして起動（プロセス終了時に自動破棄）

### 実行（`_do_restore()`）

```
GET {TGIF_API}/{DMR_ID}/{RESTORE_SLOT - 1}/{RESTORE_TG}
```

| 応答 | ログ出力 |
|------|---------|
| HTTP 200〜299 | `✅ TG変更リクエスト送信完了 (HTTP N)` |
| HTTP エラー | `⚠️ HTTP N` |
| 通信エラー | `❌ TGIF API 通信エラー: ...` |

タイムアウトは `TGIF_API_TIMEOUT` 秒。`_timer_lock`（`threading.Lock`）で排他制御します。復帰実行後は `_clear_away()` を呼び、コールサイン・ウォッチドッグの追跡状態（`away_tg` / `tracked_call` / `rf_deadline`）を解除します。

---

## 8. GPIOEngine クラス

### 8.1 初期化

| 処理 | 内容 |
|------|------|
| `_detect_gpiochip()` | `GPIO_CHIP` 設定を解釈し使用する gpiochip 名を決定 |
| `_gpioset_version()` | `gpioset --version` の出力から libgpiod のバージョンを判定（0=不在、1、2） |
| `_select()` | `GPIO_BACKEND` 設定に従いエンジンを選択 |

初期状態: `state = -1`（未設定）、`high_start = 0.0`

### 8.2 バックエンド選択ロジック（`_select()`）

| `GPIO_BACKEND` 設定値 | 動作 |
|----------------------|------|
| `libgpiod` | `gpioset` が存在すれば `libgpiod_v1` または `libgpiod_v2`、なければ `_fallback_simple()` |
| `pinctrl` / `raspi-gpio` / `sysfs` / `null` | `_init_simple()` で直接初期化 |
| `auto`（またはその他） | `_fallback_simple()`（pinctrl → raspi-gpio → sysfs の順で試行） |

### 8.3 バックエンド別の出力コマンド（`set(val)`）

| エンジン | HIGH（val=1） | LOW（val=0） |
|---------|--------------|-------------|
| `libgpiod_v2` | `gpioset -c <chip> --mode=wait <pin>=1`（バックグラウンドプロセス） | `gpioset -c <chip> <pin>=0` |
| `libgpiod_v1` | `gpioset --mode=wait <chip> <pin>=1`（バックグラウンドプロセス） | `gpioset <chip> <pin>=0` |
| `pinctrl` | `pinctrl set <pin> dh` | `pinctrl set <pin> dl` |
| `raspi-gpio` | `raspi-gpio set <pin> dh` | `raspi-gpio set <pin> dl` |
| `sysfs` | `/sys/class/gpio/gpio<pin>/value` に `1` を書き込み | 同上に `0` を書き込み |
| `null` | 何もしない | 何もしない |

`state` が変化する場合のみ実行します（同じ値への再セットは無視）。

### 8.4 libgpiod バックグラウンドプロセス管理（`_kill_bg()`）

libgpiod v1/v2 で HIGH を維持するためにバックグラウンドプロセスを起動します。次の `set()` 呼び出し時に `terminate()` → `wait(1.0)` → 必要なら `kill()` の順で終了させます。

### 8.5 クリーンアップ（`cleanup()`）

1. `set(0)` でピンを LOW へリセット
2. `_kill_bg()` でバックグラウンドプロセスを終了
3. `sysfs` エンジンの場合は `/sys/class/gpio/unexport` へピン番号を書き込み

### 8.6 gpiochip 自動検出（`_detect_gpiochip()`）

| 入力値 | 動作 |
|--------|------|
| `gpiochip` で始まる文字列 | そのまま返す |
| 数字のみ | `gpiochip<N>` として返す |
| `auto` 以外の文字列 | そのまま返す |
| `auto` | `gpiodetect` を実行し `pinctrl-bcm` または `pinctrl-rp1` を含む行の chip 名を返す。`gpiodetect` 不在またはエラー時は `gpiochip0` |

---

## 9. CmdServer クラス

Unix ドメインソケットサーバ。`cmd-server` という名前のデーモンスレッドで動作します。

### 9.1 ソケット仕様

| 項目 | 値 |
|------|-----|
| パス | `/run/tgifchanger-py.sock` |
| 種別 | `AF_UNIX` / `SOCK_STREAM` |
| パーミッション | `0o666`（一般ユーザーからも接続可） |
| バックログ | `8` |
| accept タイムアウト | 0.5 秒 |
| 接続タイムアウト | 2.0 秒 |
| 受信上限 | 512 バイト |
| 終端 | `\n` で終端と判定 |

### 9.2 受付コマンドと応答

| コマンド | 処理 | 応答 |
|---------|------|------|
| `stop` | `App.cancel_timer()` を呼び出す | `OK stop` |
| `reload` | `load_config()` と `get_dynamic_tgs()` を再実行 | `OK reload` |
| `status` | 現在状態を JSON 文字列で返す | JSON（下表） |
| その他 | エラー | `ERR unknown command: '...'` |

`status` の JSON フィールド:

| フィールド | 内容 |
|-----------|------|
| `version` | デーモンバージョン文字列 |
| `watch_tg` | 現在の監視 TG |
| `restore_tg` | 現在の復帰先 TG |
| `delay` | `RESTORE_DELAY` の現在値 |
| `callsign_timeout` | `CALLSIGN_TIMEOUT` の現在値 |
| `tracked_call` | 追跡中の「真の利用者」コールサイン（未追跡時は `null`） |
| `away_tg` | 離脱中（他TG）の TG 番号（在宅時は `null`） |
| `gpio_state` | GPIO ピンの状態（`-1`=未設定、`0`=LOW、`1`=HIGH） |
| `gpio_engine` | 使用中の GPIO バックエンド名 |
| `gpio_chip` | 使用中の gpiochip 名 |
| `timer_pending` | 復帰タイマー動作中かどうか（`true` / `false`） |

### 9.3 停止処理（`stop()`）

1. `_stop` イベントをセット
2. ダミー接続でブロック中の `accept()` を解除
3. スレッドの `join(timeout=2.0)`
4. ソケットのクローズと `/run/tgifchanger-py.sock` の削除

---

## 10. 設定値・ID 取得関数

### 10.1 `load_config()`

`/etc/tgifchanger.conf` を行単位で読み込み、`config` 辞書を上書きします。コメント行・空行・`=` を含まない行はスキップ。`OSError` 発生時はログ出力して継続。

### 10.2 `get_dmr_id() -> str`

| 探索順 | 方法 |
|--------|------|
| 1 | `/etc/dmrgateway` の `[DMR Network...]` セクションで `Address=tgif.network` を含むセクションの `Id=` 値 |
| 2 | `/etc/mmdvmhost` の全セクションから最初の `Id=` 値 |
| 3 | 見つからない場合は空文字列 |

### 10.3 `get_my_callsign() -> str`

`/etc/mmdvmhost` の全セクションから最初の `Callsign=` 値を大文字化して返します。見つからない場合は空文字列。自局送信の除外判定に使用します。

### 10.4 `get_dynamic_tgs() -> tuple[str, str]`

`WATCH_TG` と `RESTORE_TG` を解決します。

| 条件 | 動作 |
|------|------|
| `config` の両方が非空 | そのまま返す |
| どちらか一方または両方が空 | `/etc/dmrgateway`、`/etc/mmdvmhost` の順で TGRewrite を探索し解決 |
| TGRewrite も見つからない | `WATCH_TG=1`、`RESTORE_TG=4000` をフォールバック値として使用 |

TGRewrite 解析: `TGRewrite0=2,<WATCH>,2,<RESTORE>,1` のカンマ区切り第2・第4フィールドを抽出。

### 10.5 `_iter_sections(path: str)`

INI 形式ファイルをセクション単位でイテレートするジェネレータ。`[セクション名]` で区切り `(セクション名, 行リスト)` を yield します。ファイル不在・`OSError` 時は何も yield しません。

### 10.6 `_kv(line: str)`

1行を解析して `(key, value)` タプルを返します。コメント（`#` / `;`）・空行・`=` を含まない行は `None` を返します。値の `#` 以降のインラインコメントも除去します。

---

## 11. シグナル処理

| シグナル | 動作 |
|---------|------|
| `SIGINT` | `_stop` イベントをセットしてメインループを終了 |
| `SIGTERM` | `_stop` イベントをセットしてメインループを終了 |
| `SIGHUP` | `load_config()` と `get_dynamic_tgs()` を再実行（設定ホットリロード） |

登録失敗時（`ValueError` / `OSError` / `AttributeError`）は無視して継続します。

---

## 12. 終了処理（`_shutdown()`）

1. `cancel_timer()` — 復帰タイマーをキャンセル
2. `gpio.cleanup()` — GPIO ピンを LOW にリセット・バックグラウンドプロセス終了・sysfs アンエクスポート
3. `_cmd_server.stop()` — ソケットサーバを停止・ソケットファイル削除
4. `os.unlink(LOCK_FILE)` — ロックファイルを削除

---

## 13. 終了コード

| コード | 意味 |
|--------|------|
| `0` | 正常終了（`SIGINT` / `SIGTERM` による停止） |
| `1` | エラー終了（多重起動検出・ログファイル未発見） |

---

## 14. 依存関係

標準ライブラリのみ使用。外部パッケージは不要。

| モジュール | 用途 |
|-----------|------|
| `os`, `sys` | ファイル操作・プロセス制御・終了コード |
| `re` | ログ行の正規表現解析 |
| `time`, `glob` | タイマー・ログファイル検索 |
| `fcntl`, `errno` | 多重起動防止ロック |
| `signal` | シグナルハンドラ登録 |
| `socket` | Unix ドメインソケットサーバ |
| `threading` | 復帰タイマー・ソケットサーバのスレッド管理 |
| `urllib.request`, `urllib.error` | TGIF API HTTP 通信 |
| `subprocess`, `shutil` | GPIO コマンド実行・ツール存在確認 |
| `json` | `status` コマンドの JSON 生成 |
| `pathlib.Path` | ファイル読み込み |


---

## 付録A. Raspberry Pi GPIO ピンアサイン（40 ピン）

対象: Pi Zero / Zero W / Zero 2 W / 2 / 3 / 4（40 ピンヘッダ）
`GPIO_PIN` は **BCM 番号** で指定します（下図の "GPIOxx" の数字）。

```
                  3V3  [ 1] [ 2]  5V
          GPIO2 (SDA)  [ 3] [ 4]  5V
          GPIO3 (SCL)  [ 5] [ 6]  GND
       GPIO4 (GPCLK0)  [ 7] [ 8]  GPIO14 (TXD)
                  GND  [ 9] [10]  GPIO15 (RXD)
               GPIO17  [11] [12]  GPIO18 (PCM_CLK)
               GPIO27  [13] [14]  GND
               GPIO22  [15] [16]  GPIO23
                  3V3  [17] [18]  GPIO24
        GPIO10 (MOSI)  [19] [20]  GND
         GPIO9 (MISO)  [21] [22]  GPIO25
        GPIO11 (SCLK)  [23] [24]  GPIO8 (CE0)
                  GND  [25] [26]  GPIO7 (CE1)
        GPIO0 (ID_SD)  [27] [28]  GPIO1 (ID_SC)
                GPIO5  [29] [30]  GND
                GPIO6  [31] [32]  GPIO12 (PWM0)
        GPIO13 (PWM1)  [33] [34]  GND
      GPIO19 (PCM_FS)  [35] [36]  GPIO16
               GPIO26  [37] [38]  GPIO20 (PCM_DIN)
                  GND  [39] [40]  GPIO21 (PCM_DOUT)
```

### A.1 `GPIO_PIN` に使えるピン

| 区分 | BCM 番号 | 備考 |
|------|---------|------|
| **推奨（汎用 / 衝突しにくい）** | 17（既定）, 22, 23, 24, 25, 27, 5, 6, 12, 13, 16, 26, 19, 20, 21, 4 | 特殊機能割り当てがなく出力に適する |
| **避ける（周辺機器が使用）** | 2, 3（I2C → OLED） / 14, 15（UART → MMDVM モデム・Nextion） / 7〜11（SPI） / 0, 1（HAT ID EEPROM・予約） / 18（MMDVM の PCM/PWM で使われがち） | ホットスポット構成と競合する恐れ |

> **注:** 実際に使われているピンは HAT・ディスプレイの構成で変わります。割り当て前に、お使いの MMDVM HAT / OLED / Nextion の配線と重複しないか確認してください。
