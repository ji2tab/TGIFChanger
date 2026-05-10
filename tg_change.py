#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool (v2.3.0)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Configuration management and TG change API requester.
# =============================================================================

import sys, os, re, urllib.request

CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"

def save_config(key, value):
    if not value: return
    lines = []
    found = False
    new_line = f'{key}="{value}"\n'
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
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
    if os.path.exists(CMD_FIFO):
        try:
            fd = os.open(CMD_FIFO, os.O_WRONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as f:
                f.write(f"{cmd}\n")
            return True
        except: return False
    return False

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: tg_change [-w TG] [-r TG] [-t SEC] [-s] [-TG_NUMBER]")
        return
    
    cmd = args[0]
    if cmd == "-w" and len(args) > 1:
        save_config("WATCH_TG", args[1])
        notify_daemon()
        print(f"✅ 監視TGを {args[1]} に設定しました。")
    elif cmd == "-r" and len(args) > 1:
        save_config("RESTORE_TG", args[1])
        notify_daemon()
        print(f"✅ 復帰TGを {args[1]} に設定しました。")
    elif cmd == "-t" and len(args) > 1:
        save_config("RESTORE_DELAY", args[1])
        notify_daemon()
        print(f"✅ 復帰時間を {args[1]} 秒に設定しました。")
    elif cmd == "-s":
        notify_daemon("stop")
        print("✅ タイマーを停止しました。")
    elif cmd.startswith("-"):
        tg_num = cmd.lstrip("-")
        print(f"📡 TG {tg_num} への切替APIを送信中...")
        # ここにTGIF APIの送信ロジックが入ります

if __name__ == "__main__":
    main()
