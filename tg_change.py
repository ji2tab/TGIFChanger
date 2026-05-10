#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Professional CLI Tool (v2.3.2)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: This utility handles configuration persistence, communicates 
#              with the TGIF Network API, and sends real-time commands to 
#              the background daemon via FIFO.
# =============================================================================

import sys
import os
import re
import urllib.request
import urllib.parse
import time

# --- システム定数 ---
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
# デフォルトのAPIエンドポイント (設定ファイルに記述があればそちらを優先)
DEFAULT_API_URL = "http://tgif.network:5040/api/sessions/update"

def save_config(key, value):
    """設定ファイルを走査し、指定されたキーの値を安全に上書き保存する"""
    if not value:
        return
    
    lines = []
    found = False
    new_line = f'{key}="{value}"\n'
    
    # 設定ファイルが存在する場合、中身を1行ずつ確認
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, 'r') as f:
                for line in f:
                    # コメントアウト(#)されていても、キー名が一致すればその行を置換対象とする
                    if re.match(rf'^\s*#?\s*{key}=', line):
                        lines.append(new_line)
                        found = True
                    else:
                        lines.append(line)
        except Exception as e:
            print(f"❌ 設定ファイルの読み込みに失敗しました: {e}")
            return

    # キーが見つからなかった場合は末尾に追加
    if not found:
        lines.append(new_line)
    
    # ファイルに書き戻し
    try:
        with open(CONF_FILE, 'w') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"❌ 設定ファイルの保存に失敗しました: {e}")

def notify_daemon(cmd="reload"):
    """実行中のデーモンプロセスに対してFIFOパイプ経由で命令を送信する"""
    if not os.path.exists(CMD_FIFO):
        # デーモンが起動していない場合はパイプが存在しないため、静かに終了
        return False
    
    try:
        # 書き込み専用・ノンブロッキングモードでパイプを開く
        fd = os.open(CMD_FIFO, os.O_WRONLY | os.O_NONBLOCK)
        with os.fdopen(fd, 'w') as f:
            f.write(f"{cmd}\n")
        return True
    except Exception:
        # デーモン側がパイプを読んでいない等の場合はここに来る
        return False

def call_tgif_api(tg, slot="2"):
    """TGIF NetworkのAPIを叩いて、Talkgroupの切り替えをリクエストする"""
    api_url = DEFAULT_API_URL
    
    # 設定ファイルからカスタムAPI URLの取得を試みる
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, 'r') as f:
                for line in f:
                    if "TGIF_API=" in line and not line.startswith("#"):
                        api_url = line.split("=", 1)[1].strip().strip('"').strip("'")
        except:
            pass

    # API送信データの準備
    params = {'tg': tg, 'slot': slot}
    data = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, method='POST')
    
    print(f"📡 TGIF API送信中: TG {tg} (Slot {slot})...")
    
    try:
        # タイムアウト10秒でAPI送信
        with urllib.request.urlopen(req, timeout=10) as res:
            code = res.getcode()
            if code == 200:
                print(f"✅ 成功: TGIF Network が更新されました (HTTP {code})")
            else:
                print(f"⚠️ 応答あり: HTTP {code}")
    except Exception as e:
        print(f"❌ API送信エラー: {e}")

def main():
    """メイン引数解析ロジック"""
    args = sys.argv[1:]
    if not args:
        print("Usage: tg_change [Options] [TG_Command]")
        print("Options:")
        print("  -w <TG>      監視TGを設定")
        print("  -r <TG>      復帰TGを設定")
        print("  -t <SEC>     復帰タイマー秒数を設定")
        print("  -s           タイマーを強制停止")
        print("  -<TG>        Talkgroupを即座に変更 (例: -3100)")
        print("Internal Flags:")
        print("  --save-only    設定保存のみ行い、デーモン通知をスキップ")
        print("  --notify-only  デーモンへのリロード通知のみ実行")
        return

    # フラグの確認
    save_only = "--save-only" in args
    notify_only = "--notify-only" in args

    # 通知のみの場合
    if notify_only:
        notify_daemon("reload")
        sys.exit(0)

    # 実際の処理用引数（フラグを除去）
    clean_args = [a for a in args if not a.startswith("--")]
    if not clean_args:
        sys.exit(0)
    
    cmd = clean_args[0]

    # --- 1. 監視TGの設定変更 ---
    if cmd == "-w" and len(clean_args) > 1:
        val = clean_args[1]
        save_config("WATCH_TG", val)
        if not save_only:
            notify_daemon("reload")
        print(f"✅ 監視TGを {val} に設定しました。")

    # --- 2. 復帰TGの設定変更 ---
    elif cmd == "-r" and len(clean_args) > 1:
        val = clean_args[1]
        save_config("RESTORE_TG", val)
        if not save_only:
            notify_daemon("reload")
        print(f"✅ 復帰TGを {val} に設定しました。")

    # --- 3. 復帰時間の初期値変更 ---
    elif cmd == "-t" and len(clean_args) > 1:
        val = clean_args[1]
        save_config("RESTORE_DELAY", val)
        if not save_only:
            notify_daemon("reload")
        print(f"✅ 復帰時間を {val} 秒に設定しました。")

    # --- 4. タイマー強制停止命令 ---
    elif cmd == "-s":
        if notify_daemon("stop"):
            print("✅ デーモンにタイマー停止信号を送信しました。")
        else:
            print("⚠️ デーモンが応答しません。")

    # --- 5. TG切替APIの実行 (例: -3100 または -3100:1) ---
    elif cmd.startswith("-"):
        target = cmd.lstrip("-")
        # スロット指定があるか確認
        if ":" in target:
            tg_num = target.split(":")[0]
            slot_num = target.split(":")[1]
        else:
            tg_num = target
            slot_num = "2" # デフォルトはスロット2
            
        if tg_num.isdigit():
            call_tgif_api(tg_num, slot_num)
        else:
            print(f"❌ 不正なTalkgroup番号です: {tg_num}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"🔥 重大なエラーが発生しました: {e}")
        sys.exit(1)
