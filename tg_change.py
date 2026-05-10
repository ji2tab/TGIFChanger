#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool (v2.3.4)
# =============================================================================
import sys, os, re, urllib.request, urllib.parse

CONF_FILE = "/etc/tgifchanger.conf"
API_URL = "http://tgif.network:5040/api/sessions/update"

def call_api(tg, slot="2"):
    api_key = ""
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            k = re.search(r'TGIF_KEY="(.+?)"', content)
            if k: api_key = k.group(1)

    if not api_key:
        print("❌ TGIF_KEY 未設定。/etc/tgifchanger.conf を確認してください。"); return

    params = {'tg': tg, 'slot': slot, 'key': api_key}
    data = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            print(f"✅ TG {tg} 切替成功 (HTTP {res.getcode()})")
    except Exception as e:
        print(f"❌ API送信エラー: {e}")

def main():
    args = sys.argv[1:]
    if not args: return
    cmd = args[0]
    if cmd.startswith("-") and cmd[1:].isdigit():
        call_api(cmd.lstrip("-"))

if __name__ == "__main__":
    main()
