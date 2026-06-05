# tgif_daemon.py ソフトウェア仕様書

**ファイル:** `tgif_daemon.py`
**バージョン:** v2.3.3
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py のメインデーモンです。MMDVM ログを常時監視し、DMR トークグループの変化を検出して TGIF API への自動復帰リクエストと GPIO 出力制御を行います。systemd によって管理され、`tg_change` CLI ツールからは Unix ドメインソケット経由で制御されます。

### v2.3.3 での変更点

logrotate 等によるログ消失・切替瞬間のレースコンディションを修正:

- `get_latest()` が空を返した場合、現ファイルを維持したまま次ループへ継続
- `os.stat()` での `FileNotFoundError` / `PermissionError` を捕捉・無視し、現ファイルを掴んだまま次ループで再検知を待つ

---

## 2. 定数

| 定数 | 値 | 説明 |
|------|----|------|
| `VERSION` | `v2.3.3` | デーモンバージョン（`status` コマンドで返される） |
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

| 処理 | 条件 |
|------|------|
| 復帰タイマーをキャンセル | 無条件 |
| 自局送信の除外 | `from <コールサイン>` が `my_call` と一致する場合はスキップ |
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

タイムアウトは `TGIF_API_TIMEOUT` 秒。`_timer_lock`（`threading.Lock`）で排他制御します。

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
