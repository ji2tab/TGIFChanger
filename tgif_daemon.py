#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - TGIF Talk Group Changer API Bridge
# 
# File:        tg_change.py
# Version:     v2.2.0 (Full CLI Config Edition)
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: CLI tool with Auto-Sudo and full configuration management.
# License:     GPL v3
# =============================================================================

import sys, os, urllib.request

# =====================================================================
# 🌟 Auto-Sudo (自動昇格) ロジック
# =====================================================================
if os.geteuid() != 0:
    try:
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    except Exception as e:
        print("❌ エラー: 管理者権限への自動昇格に失敗しました。")
        sys.exit(1)

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
    
    try:
        with open(CONF_FILE, 'w') as f:
            f.writelines(lines)
    except PermissionError:
        print("❌ エラー: 設定ファイルに書き込む権限がありません。")
        sys.exit(1)

def send_daemon_cmd(cmd):
    try:
        with open(CMD_FIFO, 'w') as f:
            f.write(cmd)
    except Exception:
        pass # デーモンが停止している場合は無視

def show_config():
    print("⚙️  現在の TGIFChanger 設定:")
    print("-" * 40)
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    print(f"  {line.strip()}")
    else:
        print("  (設定ファイルがまだ作成されていません)")
    print("-" * 40)

def show_help():
    print(f"TGIFChanger CLI v2.2.0")
    print("\n使用方法:")
    print("  【API操作 (即時変更)】")
    print("  tg_change -<TG>[:<Slot>]  現在の接続先TGを即座に変更")
    print("  tg_change -s              動作中の復帰タイマーを強制停止 (STOP)")
    print("\n  【設定の変更・確認】")
    print("  tg_change -w <TG>         監視TG (WATCH_TG) を設定")
    print("  tg_change -r <TG>         復帰TG (RESTORE_TG) を設定")
    print("  tg_change -t <秒数>       復帰時間 (RESTORE_DELAY) を設定")
    print("  tg_change -c              現在の設定一覧を確認 (CHECK)")
    sys.exit(0)

# --- 引数処理 ---
args = sys.argv[1:]
if not args or "-h" in args or "--help" in args: show_help()

cmd = args[0]

if cmd == "-s":
    send_daemon_cmd("stop")
    print("✅ タイマー停止信号を送信しました。")
    sys.exit(0)
elif cmd == "-c":
    show_config()
    sys.exit(0)
elif cmd in ["-t", "-w", "-r"]:
    if len(args) < 2:
        print("❌ エラー: 設定値が入力されていません。")
        show_help()
    val = args[1]
    if cmd == "-t":
        save_config("RESTORE_DELAY", val)
        msg = f"復帰時間 (RESTORE_DELAY) を {val} 秒"
    elif cmd == "-w":
        save_config("WATCH_TG", val)
        msg = f"監視TG (WATCH_TG) を {val}"
    elif cmd == "-r":
        save_config("RESTORE_TG", val)
        msg = f"復帰TG (RESTORE_TG) を {val}"
    
    send_daemon_cmd("reload")
    print(f"✅ {msg} に設定し、デーモンに反映しました。")
    sys.exit(0)

# --- API通信ロジック (通常のTG変更) ---
try:
    sys.path.append("/opt/tgifchanger-py")
    import tgif_daemon
    tgif_daemon.load_config()
    dmr_id = tgif_daemon.config.get("DMR_ID") or tgif_daemon.App.get_dmr_id(tgif_daemon.App)
    api_url = tgif_daemon.config.get("TGIF_API", "http://tgif.network:5040/api/sessions/update")
except Exception as e:
    print(f"❌ エラー: モジュールのロードに失敗 ({e})")
    sys.exit(1)

target = cmd.lstrip("-")
tg = target.split(":")[0]
slot = target.split(":")[1] if ":" in target else "1"

print(f"Changing Slot {slot} to TG {tg}...")
try:
    url = f"{api_url}/{dmr_id}/{int(slot)-1}/{tg}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as res:
        if res.status == 200: print("✅ TG変更リクエスト送信完了 (HTTP 200)")
        else: print(f"⚠️ HTTP {res.status}")
except Exception as e:
    print(f"❌ API通信エラー: {e}")
    sys.exit(1)
