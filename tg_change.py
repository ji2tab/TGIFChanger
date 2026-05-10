#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - TGIF Talk Group Changer API Bridge
# 
# File:        tg_change.py
# Version:     v2.1.4 (Auto-Sudo Edition)
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: CLI tool to interact with TGIF API and the TGIFChanger daemon.
#              Features Auto-Sudo privilege escalation for seamless user UX.
# License:     GPL v3
# =============================================================================

import sys, os, urllib.request

# =====================================================================
# 🌟 Auto-Sudo (自動昇格) ロジック
# 一般ユーザーとして実行された場合、自動的に sudo 付きで自分自身を再起動します。
# これにより、ユーザーは手動で sudo を入力する必要がなくなります。
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
    except PermissionError:
        print("❌ エラー: デーモンに命令を送る権限がありません。")
        sys.exit(1)

def show_help():
    print(f"TGIFChanger CLI v2.1.4")
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

# --- API通信ロジック (デーモンから情報を取得) ---
try:
    sys.path.append("/opt/tgifchanger-py")
    import tgif_daemon
    tgif_daemon.load_config()
    dmr_id = tgif_daemon.config.get("DMR_ID") or tgif_daemon.App.get_dmr_id(tgif_daemon.App)
    api_url = tgif_daemon.config["TGIF_API"]
except Exception as e:
    print(f"❌ エラー: モジュールのロードに失敗 ({e})")
    sys.exit(1)

target = args[0].lstrip("-")
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
