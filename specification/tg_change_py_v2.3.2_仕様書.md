# tg_change.py ソフトウェア仕様書

**ファイル:** `tg_change.py`
**バージョン:** v2.3.2
**作成者:** Kazuhiko Shinoda (JI2TAB)
**ライセンス:** GPL v3
**リポジトリ:** https://github.com/ji2tab/TGIFChanger

---

## 1. 概要

TGIFChanger-Py デーモン（`tgif_daemon.py`）に対応する **CLI 制御ツール**です。以下の3つの役割を担います。

- TGIF API への直接 TG 変更リクエスト送信
- Unix ドメインソケット経由のデーモン制御（タイマー停止・設定リロード・状態確認）
- 設定ファイル（`/etc/tgifchanger.conf`）の読み書き

シンボリックリンク `/usr/local/bin/tg_change` 経由で呼び出します。

### v2.3.2 での変更点

設定ファイル書き込み時の競合（レースコンディション）を防止:

- `fcntl.flock` による排他ロック制御を導入
- `os.replace` によるアトミック書き込みを導入（`.tmp` ファイル経由）

---

## 2. 定数

| 定数 | 値 | 説明 |
|------|----|------|
| `CONF_FILE` | `/etc/tgifchanger.conf` | 設定ファイルパス |
| `CMD_SOCKET` | `/run/tgifchanger-py.sock` | デーモン制御用 Unix ドメインソケット |
| `DMRGW_CONF` | `/etc/dmrgateway` | DMRGateway 設定ファイルパス |
| `MMDVM_CONF` | `/etc/mmdvmhost` | MMDVMHost 設定ファイルパス |

---

## 3. コマンドリファレンス

### 3.1 構文

```
tg_change -<TG>[:<Slot>]   # TGIF API で即時 TG 変更
tg_change -s / --cancel    # 復帰タイマー停止
tg_change --status         # デーモン状態を JSON 表示
tg_change -w <TG>          # WATCH_TG を設定（root 必要）
tg_change -r <TG>          # RESTORE_TG を設定（root 必要）
tg_change -t <秒数>        # RESTORE_DELAY を設定（root 必要）
tg_change -c               # 設定ファイル内容を表示
tg_change -h / --help      # ヘルプ表示（引数なし時も同様）
```

### 3.2 コマンド詳細

| コマンド | root 要否 | 処理関数 | 説明 |
|---------|-----------|---------|------|
| `-<TG>[:<Slot>]` | 不要 | `cmd_change_tg()` | TGIF API を呼び出し指定 TG へ即時切替。スロット省略時はスロット 1 |
| `-s` / `--cancel` | 不要 | `cmd_cancel_timer()` | デーモンの復帰タイマーを即時停止（`stop` コマンド送信） |
| `--status` | 不要 | `cmd_status()` | デーモンの現在状態を JSON 形式で標準出力へ表示 |
| `-w <TG>` | **root** | `cmd_set_conf()` | `WATCH_TG` を変更・保存しデーモンへ即時反映 |
| `-r <TG>` | **root** | `cmd_set_conf()` | `RESTORE_TG` を変更・保存しデーモンへ即時反映 |
| `-t <秒>` | **root** | `cmd_set_conf()` | `RESTORE_DELAY` を変更・保存しデーモンへ即時反映 |
| `-c` | 不要 | `cmd_show_config()` | `/etc/tgifchanger.conf` の有効行（コメント除く）を表示 |
| `-h` / `--help` | 不要 | `show_help()` | ヘルプを表示して終了 |

### 3.3 使用例

```bash
# スロット1 を TG4000（Disconnect）へ即時変更
tg_change -4000

# スロット2 を TG168 へ即時変更
tg_change -168:2

# デーモン状態確認
tg_change --status

# 監視 TG を 1234 に変更（デーモンへ即時反映）
sudo tg_change -w 1234

# 復帰待機時間を 60 秒に変更
sudo tg_change -t 60

# 復帰タイマーを手動キャンセル
tg_change --cancel
```

---

## 4. 内部関数仕様

### 4.1 `_send_cmd(cmd: str) -> str`

デーモンとの Unix ドメインソケット通信を担います。

| 項目 | 内容 |
|------|------|
| ソケットパス | `/run/tgifchanger-py.sock` |
| ソケット種別 | `AF_UNIX` / `SOCK_STREAM` |
| タイムアウト | 3.0 秒 |
| 送信フォーマット | `コマンド文字列\n`（UTF-8） |
| 受信終端判定 | バッファが `\n` で終端するまで受信継続 |
| エラー時戻り値 | `"ERR socket: <詳細>"`（例外を外へ出さない） |

送信コマンドと対応するデーモン動作:

| 文字列 | デーモン動作 |
|--------|------------|
| `status` | 状態を JSON で返す |
| `stop` | 復帰タイマーをキャンセル |
| `reload` | 設定ファイルを再読み込みし TG を更新 |

### 4.2 `_load_conf() -> dict`

`/etc/tgifchanger.conf` を行単位で読み込み、KEY=VALUE 形式を辞書で返します。

- コメント行（`#` 始まり）・空行・`=` を含まない行はスキップ
- 値のシングルクォート・ダブルクォートは除去

### 4.3 `_save_conf(key: str, value: str) -> None`

設定ファイルへのアトミック書き込み（v2.3.2 刷新）。

**処理フロー:**

| ステップ | 処理 |
|---------|------|
| 1 | root 権限チェック。非 root の場合はエラーメッセージを表示して `sys.exit(1)` |
| 2 | `/etc/tgifchanger.conf.lock` を作成し `fcntl.LOCK_EX` で排他ロック取得 |
| 3 | 設定ファイルを行単位で読み込み、対象キーの行を新値で置換（未存在時は末尾追記） |
| 4 | `/etc/tgifchanger.conf.tmp` へ書き出し |
| 5 | `os.replace()` で `.tmp` を本番ファイルへアトミックに置換 |
| 6 | `with` ブロック終了でロックを自動解放 |

**エラー時:** `.tmp` ファイルが残存する場合は削除してから `sys.exit(1)`。

書き込みフォーマット: `KEY="value"\n`（ダブルクォートで囲む）

### 4.4 `_iter_sections(path: str)`

INI 形式ファイルをセクション単位でイテレートするジェネレータ。

- `[セクション名]` 行でセクションを区切り、`(セクション名, 行リスト)` を yield
- ファイル不在の場合は何も yield しない
- `errors="replace"` で読み込むため、不正エンコードでも停止しない

### 4.5 `_get_dmr_id() -> str`

設定ファイルから DMR ID を取得します。

**探索順:**

1. `/etc/dmrgateway` の `[DMR Network...]` セクションを走査し、`Address=tgif.network` を含むセクションの `Id=` 値を返す
2. 見つからない場合は `/etc/mmdvmhost` の全セクションから最初の `Id=` 値を返す
3. どちらも見つからない場合は空文字列を返す

コメント（`#` 以降）は値から除去。`;` 始まりの行もスキップ。

---

## 5. コマンド関数仕様

### 5.1 `cmd_show_config() -> None`

`/etc/tgifchanger.conf` を読み込み、コメント行と空行を除いた有効な設定行を標準出力へ表示します。ファイルが存在しない場合はその旨を表示します。終了コードなし（`None` 返却）。

### 5.2 `cmd_status() -> int`

デーモンへ `status` コマンドを送信し、JSON レスポンスをインデント付きで標準出力へ表示します。

| 状態 | 動作 | 終了コード |
|------|------|-----------|
| デーモン応答あり（JSON） | `json.dump` でインデント表示 | `0` |
| デーモン応答あり（非 JSON） | テキストをそのまま表示 | `0` |
| `ERR` で始まる応答 | エラーメッセージと確認コマンドを表示 | `1` |

### 5.3 `cmd_cancel_timer() -> int`

デーモンへ `stop` コマンドを送信します。

| 応答 | 動作 | 終了コード |
|------|------|-----------|
| `OK` で始まる | 停止成功メッセージを表示 | `0` |
| その他 | デーモン応答をそのまま表示 | `1` |

### 5.4 `cmd_set_conf(key, value, label) -> int`

`_save_conf()` で設定を保存後、デーモンへ `reload` コマンドを送信します。

| デーモン応答 | 表示メッセージ |
|------------|--------------|
| `OK` で始まる | 設定済み＋デーモン反映済みを通知 |
| その他 | 設定済みを通知（リロード失敗の詳細を併記） |

常に終了コード `0` を返します。

### 5.5 `cmd_change_tg(arg: str) -> int`

引数を解析して TGIF API へ GET リクエストを送信します。

**引数フォーマット:**

| 入力 | TG | スロット |
|------|----|---------|
| `-4000` | `4000` | `1`（デフォルト） |
| `-168:2` | `168` | `2` |

**バリデーション:**

| チェック項目 | エラー条件 |
|------------|-----------|
| TG 番号 | `^\d+$` にマッチしない場合 |
| スロット | `"1"` または `"2"` 以外の場合 |
| DMR ID | `_get_dmr_id()` が空文字列を返した場合 |

**API エンドポイント:**

```
GET {TGIF_API}/{DMR_ID}/{SLOT_INDEX}/{TG番号}
```

`SLOT_INDEX` はスロット番号 - 1（スロット1→0、スロット2→1）。

**レスポンス処理:**

| HTTP ステータス | 動作 | 終了コード |
|----------------|------|-----------|
| 200〜299 | 成功メッセージを表示 | `0` |
| その他の HTTP ステータス | ステータスコードを警告表示 | `1` |
| 通信エラー（`URLError` / `OSError`） | エラー詳細を表示 | `1` |

---

## 6. 引数解析フロー（`main()`）

```
引数なし / -h / --help  →  show_help() → 終了コード 0
-s / --cancel           →  cmd_cancel_timer()
-c                      →  cmd_show_config()
--status                →  cmd_status()
-t / -w / -r <値>       →  cmd_set_conf()  ※値なし時はエラー
-<数字>[:<数字>]        →  cmd_change_tg()
その他                  →  エラーメッセージ + show_help() → 終了コード 1
```

---

## 7. 終了コード

| コード | 意味 |
|--------|------|
| `0` | 正常終了 |
| `1` | エラー（引数不正・API エラー・デーモン未応答・権限不足・書き込み失敗など） |

---

## 8. 依存関係

標準ライブラリのみ使用。外部パッケージは不要。

| モジュール | 用途 |
|-----------|------|
| `sys`, `os` | 引数処理・ファイル操作・プロセス制御 |
| `re` | 引数パターンマッチ・設定ファイル行解析 |
| `socket` | Unix ドメインソケット通信 |
| `json` | デーモン応答の解析・整形表示 |
| `urllib.request`, `urllib.error` | TGIF API HTTP 通信 |
| `fcntl` | 設定ファイルの排他ロック（Linux 専用） |
| `pathlib.Path` | ファイル読み書き |

