#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool (v2.3.2)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Configuration management and TGIF Network API client.
# =============================================================================

import sys
import os
import re
import urllib.request
import urllib.parse

# --- 設定項目 ---
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
# デフォルトAPI（設定ファイルから上書き可能）
DEFAULT_API = "http://tgif.network:5040/api/sessions/update"

def save_config(key, value):
    """設定ファイル内のキーを検索し、値を安全に上書き保存する"""
    if not value: return
    lines = []
    found = False
    new_line = f'{key}="{value}"\n'
    
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                # コメントアウトされていても、キーが一致すればそこを置換
                if re.match(rf'^\s*#?\s*{key}=', line):
                    lines.append(new_line)
                    found = True
                else:
                    lines.append(line)
    
    if not found:
        lines.append(new_line)
    
    with open(CONF_FILE, 'w') as f:
        f.writelines(lines)

def notify_daemon(cmd="reload"):
    """実行中のデーモンにFIFOを通じて命令を送る"""
    if os.path.exists(CMD_FIFO):
        try:
            # ノンブロッキングで書き込み
            fd = os.open(CMD_FIFO, os.O_WRONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as f:
                f.write(f"{cmd}\n")
            return True
        except:
            return False
    return False

def call_tgif_api(tg, slot="2"):
    """TGIF APIにTalkgroup変更リクエストを送信する"""
    # 設定ファイルからAPI URLを取得
    api_url = DEFAULT_API
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if "TGIF_API=" in line:
                    api_url = line.split("=", 1)[1].strip().strip('"').strip("'")

    data = urllib.parse.urlencode({'tg': tg, 'slot': slot}).encode('utf-8')
    req = urllib.request.Request(api_url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            print(f"✅ TG {tg} (Slot {slot}) 変更リクエスト送信完了 (HTTP {res.getcode()})")
    except Exception as e:
        print(f"❌ APIエラー: {e}")

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: tg_change [-w TG] [-r TG] [-t SEC] [-s] [-TG_NUMBER]")
        return

    # フラグの分離
    save_only = "--save-only" in args
    notify_only = "--notify-only" in args
    
    if notify_only:
        notify_daemon("reload")
        sys.exit(0)

    # 有効な引数のみ抽出
    clean_args = [a for a in args if not a.startswith("--")]
    if not clean_args: return
    
    cmd = clean_args[0]
    
    # 個別設定の保存
    if cmd == "-w" and len(clean_args) > 1:
        save_config("WATCH_TG", clean_args[1])
        if not save_only: notify_daemon("reload")
        print(f"✅ 監視TG: {clean_args[1]} を保存しました。")
        
    elif cmd == "-r" and len(clean_args) > 1:
        save_config("RESTORE_TG", clean_args[1])
        if not save_only: notify_daemon("reload")
        print(f"✅ 復帰TG: {clean_args[1]} を保存しました。")
        
    elif cmd == "-t" and len(clean_args) > 1:
        save_config("RESTORE_DELAY", clean_args[1])
        if not save_only: notify_daemon("reload")
        print(f"✅ 復帰時間: {clean_args[1]}秒 を保存しました。")
        
    elif cmd == "-s":
        notify_daemon("stop")
        print("✅ タイマー強制停止を通知しました。")
        
    elif cmd.startswith("-"):
        # API経由でのTG切替実行
        target = cmd.lstrip("-")
        tg = target.split(":")[0]
        slot = target.split(":")[1] if ":" in target else "2"
        call_tgif_api(tg, slot)

if __name__ == "__main__":
    main()
