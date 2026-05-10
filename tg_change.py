#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - CLI Tool (v2.3.5)
# Description: Auto-extracts API Key from DMRGateway.ini for secure switching.
# =============================================================================

import sys, os, re, urllib.request, urllib.parse

CONF_FILE = "/etc/tgifchanger.conf"
DMRGW_FILE = "/etc/dmrgateway"
API_URL = "http://tgif.network:5040/api/sessions/update"

def get_tgif_key_from_gw():
    """DMRGateway.iniを解析してTGIFのAPIキーを動的に取得する"""
    if not os.path.exists(DMRGW_FILE):
        return None
    
    try:
        with open(DMRGW_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_section = ""
        sections = {}
        
        # 1. セクションごとに設定を分割して保持
        for line in lines:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_section = line
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line)
        
        # 2. tgif.networkが含まれるセクションを探す
        for name, params in sections.items():
            if any("Address=tgif.network" in p for p in params):
                # そのセクション内の Password= を探す
                for p in params:
                    if p.startswith("Password="):
                        # Password="key" または Password=key の形式に対応
                        key = p.split("=", 1)[1].strip().strip('"').strip("'")
                        return key
    except Exception:
        pass
    return None

def call_api(tg, slot="2"):
    # まずDMRGatewayから取得を試みる
    api_key = get_tgif_key_from_gw()
    
    # もし見つからなければ、予備として設定ファイルも見る
    if not api_key and os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r', encoding='utf-8') as f:
            k = re.search(r'TGIF_KEY="(.+?)"', f.read())
            if k: api_key = k.group(1)

    if not api_key:
        print("❌ APIキーが見つかりません (DMRGateway.iniにも設定なし)"); return

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
