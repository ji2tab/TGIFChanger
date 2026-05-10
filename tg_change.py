#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, urllib.request, re

# 自動昇格
if os.geteuid() != 0:
    try: os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    except: sys.exit(1)

CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"

def save_config(key, value):
    if not value or value.strip() == "": return # 空の値は保存しない
    lines = []
    found = False
    new_line = f'{key}="{value}"\n'
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if re.match(rf'^\s*#?\s*{key}=', line):
                    lines.append(new_line)
                    found = True
                else: lines.append(line)
    if not found: lines.append(new_line)
    with open(CONF_FILE, 'w') as f: f.writelines(lines)

def send_daemon_cmd(cmd):
    if os.path.exists(CMD_FIFO):
        try:
            with open(CMD_FIFO, 'w') as f: f.write(cmd)
        except: pass

args = sys.argv[1:]
if not args: sys.exit(0)
cmd = args[0]

# 設定変更ロジック
if cmd in ["-t", "-w", "-r"] and len(args) >= 2:
    val = args[1]
    key = {"-t":"RESTORE_DELAY", "-w":"WATCH_TG", "-r":"RESTORE_TG"}[cmd]
    save_config(key, val)
    send_daemon_cmd("reload")
    print(f"✅ {key} を {val} に設定し、永続化しました。")
    sys.exit(0)
elif cmd == "-s":
    send_daemon_cmd("stop")
    print("✅ タイマー停止信号を送信しました。")
    sys.exit(0)
elif cmd == "-c":
    sys.exit(0)

# API操作ロジック (設定フラグはTG番号として扱わない)
target = cmd.lstrip("-")
if target in ["w", "r", "t", "c", "s"]: sys.exit(0)

tg = target.split(":")[0]
slot = target.split(":")[1] if ":" in target else "1"
print(f"Changing Slot {slot} to TG {tg}...")
# ... (以下API通信処理: 以前と同じ)
