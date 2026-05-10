#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool (v2.2.3)
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
                else: lines.append(line)
    if not found: lines.append(new_line)
    with open(CONF_FILE, 'w') as f: f.writelines(lines)

def notify_daemon():
    if os.path.exists(CMD_FIFO):
        try:
            fd = os.open(CMD_FIFO, os.O_WRONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as f:
                f.write("reload\n")
            return True
        except: return False
    return False

def main():
    args = sys.argv[1:]
    if not args: return
    
    cmd = args[0]
    if cmd == "-w" and len(args) > 1:
        save_config("WATCH_TG", args[1])
        notify_daemon()
        print(f"✅ WATCH_TG={args[1]} を保存し、デーモンに通知しました")
    elif cmd == "-r" and len(args) > 1:
        save_config("RESTORE_TG", args[1])
        notify_daemon()
        print(f"✅ RESTORE_TG={args[1]} を保存し、デーモンに通知しました")
    elif cmd == "-t" and len(args) > 1:
        save_config("RESTORE_DELAY", args[1])
        notify_daemon()
        print(f"✅ DELAY={args[1]} を保存しました")
    # API送信ロジックなどはここに続く...

if __name__ == "__main__":
    main()
