#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, urllib.request

def show_help():
    print("使用方法:\n  tg_change -<TG番号>           スロット1 の TG を変更")
    print("  tg_change -<TG番号>:<スロット> 指定スロットの TG を変更")
    sys.exit(0)

if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]: show_help()

# Import parser logic from daemon
try:
    sys.path.append("/opt/tgifchanger-py")
    import tgif_daemon
    tgif_daemon.load_config()
    dmr_id = tgif_daemon.get_dmr_id()
    api_url = tgif_daemon.config["TGIF_API"]
except Exception as e:
    print(f"❌ エラー: モジュールのロードに失敗 ({e})")
    sys.exit(1)

if not dmr_id:
    print("❌ エラー: DMR ID を取得できませんでした。"); sys.exit(1)

target = sys.argv[1].lstrip("-")
tg = target.split(":")[0]
slot = target.split(":")[1] if ":" in target else "1"

print(f"Changing Slot {slot} to TG {tg} (DMR ID: {dmr_id})...")
try:
    url = f"{api_url}/{dmr_id}/{int(slot)-1}/{tg}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as res:
        if res.status == 200: print("✅ TG変更リクエスト送信完了 (HTTP 200)")
        else: print(f"⚠️ HTTP {res.status}")
except Exception as e:
    print(f"❌ API通信エラー: {e}")
    sys.exit(1)
