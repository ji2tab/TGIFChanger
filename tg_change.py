#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, re, urllib.request, urllib.parse

CONF_FILE = "/etc/tgifchanger.conf"
DMRGW_FILE = "/etc/dmrgateway"
API_URL = "http://tgif.network:5040/api/sessions/update"

def get_tgif_key():
    """DMRGateway.iniからPassword(APIキー)を自動抽出"""
    if os.path.exists(DMRGW_FILE):
        try:
            with open(DMRGW_FILE, 'r') as f:
                content = f.read()
            # tgif.networkを含むセクションのPasswordを探す
            sections = re.split(r'(\[.*?\])', content)
            for i in range(1, len(sections), 2):
                if "tgif.network" in sections[i+1]:
                    pw = re.search(r'^Password=(.+)$', sections[i+1], re.M)
                    if pw: return pw.group(1).strip().strip('"').strip("'")
        except: pass
    return None

def call_api(tg, slot="2"):
    api_key = get_tgif_key()
    if not api_key:
        print("❌ APIキーをDMRGatewayから取得できませんでした。"); return

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
