#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, urllib.request

CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"

def save_config(key, value):
    lines = []
    found = False
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    
    with open(CONF_FILE, 'w') as f:
        f.writelines(lines)

def send_daemon_cmd(cmd):
    with open(CMD_FIFO, 'w') as f:
        f.write(cmd)

def show_help():
    print(f"TGIFChanger CLI v2.1.0")
    print("使用方法:")
    print("  tg_change -<TG>[:<Slot>]  TGを変更")
    print("  tg_change -s              復帰タイマーを停止 (STOP)")
    print("  tg_change -t <秒数>       復帰時間を設定して保存")
    sys.exit(0)

# --- 引数処理 ---
args = sys.argv[1:]
if not args or "-h" in args: show_help()

if args[0] == "-s":
    send_daemon_cmd("stop")
    print("✅ タイマー停止信号を送信しました。")
    sys.exit(0)

if args[0] == "-t":
    if len(args) < 2: show_help()
    sec = args[1]
    save_config("RESTORE_DELAY", sec)
    send_daemon_cmd("reload")
    print(f"✅ 復帰時間を {sec} 秒に設定し、永続化しました。")
    sys.exit(0)

# (通常のTG変更ロジック...)
