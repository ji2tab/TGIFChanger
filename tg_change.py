#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool
# Version: v2.2.0 (Auto-Sudo Edition)
# =============================================================================

import sys, os, urllib.request

# 🌟 Auto-Sudo ロジック: pi-starユーザーでもエラーなく管理者権限で実行
if os.geteuid() != 0:
    try: os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    except Exception:
        print("❌ エラー: 管理者権限への自動昇格に失敗しました。")
        sys.exit(1)

CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
DMRGW_CONF = "/etc/dmrgateway"

def save_config(key, value):
    lines, found = [], False
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else: lines.append(line)
    if not found: lines.append(f'{key}="{value}"\n')
    
    with open(CONF_FILE, 'w') as f: f.writelines(lines)

def send_daemon_cmd(cmd):
    if not os.path.exists(CMD_FIFO):
        print("⚠️ デーモンが起動していません。設定は保存されました。")
        return
    with open(CMD_FIFO, 'w') as f: f.write(cmd)

def show_help():
    print("TGIFChanger CLI v2.2.0")
    print("  tg_change -<TG>[:<Slot>]  即時TG変更 (例: tg_change -168)")
    print("  tg_change -s              復帰タイマーを停止 (STOP)")
    print("  tg_change -t <秒数>       復帰時間を設定して保存")
    print("  tg_change -w <TG>         監視TGを設定して保存")
    sys.exit(0)

args = sys.argv[1:]
if not args or "-h" in args: show_help()

if args[0] == "-s":
    send_daemon_cmd("stop")
    print("✅ タイマー停止信号をデーモンに送信しました。")
    sys.exit(0)

if args[0] in ["-t", "-w"]:
    if len(args) < 2: show_help()
    val = args[1]
    key = "RESTORE_DELAY" if args[0] == "-t" else "WATCH_TG"
    save_config(key, val)
    send_daemon_cmd("reload")
    print(f"✅ {key} を {val} に設定し、デーモンに反映させました。")
    sys.exit(0)

# 即時API通信ロジック
dmr_id = ""
if os.path.exists(DMRGW_CONF):
    with open(DMRGW_CONF, 'r') as f:
        for line in f:
            if line.startswith("Id="):
                dmr_id = line.split('=')[1].split('#')[0].strip()

if not dmr_id:
    print("❌ エラー: DMR IDが見つかりません。")
    sys.exit(1)

target = args[0].lstrip("-")
tg = target.split(":")[0]
slot = target.split(":")[1] if ":" in target else "1"

print(f"Changing Slot {slot} to TG {tg}...")
try:
    url = f"http://tgif.network:5040/api/sessions/update/{dmr_id}/{int(slot)-1}/{tg}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as res:
        if res.status == 200: print("✅ TG変更リクエスト送信完了 (HTTP 200)")
        else: print(f"⚠️ HTTP {res.status}")
except Exception as e:
    print(f"❌ API通信エラー: {e}")
    sys.exit(1)
