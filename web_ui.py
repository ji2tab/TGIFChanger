#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import http.server, socketserver, urllib.parse, subprocess, os

PORT = 8080
CONF_FILE = "/etc/tgifchanger.conf"
TG_CHANGE_BIN = "/usr/local/bin/tg_change"

def get_config():
    conf = {"WATCH_TG": "", "RESTORE_TG": "", "RESTORE_DELAY": "120"}
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    try:
                        k, v = line.split("=", 1)
                        conf[k.strip()] = v.strip().strip('"').strip("'")
                    except: pass
    return conf

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        conf = get_config()
        # 値が空なら「未設定」と表示するロジック
        watch_disp = f"TG {conf['WATCH_TG']}" if conf['WATCH_TG'] else "未設定"
        restore_disp = f"TG {conf['RESTORE_TG']}" if conf['RESTORE_TG'] else "未設定"
        
        # (以前のHTMLコードの変数部分をこれに差し替え)
        # ... HTML生成 ...
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        # (以下、HTMLの wfile.write)

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        if self.path == "/config":
            # 値が入っている時だけコマンドを叩く
            if 'watch_tg' in fields and fields['watch_tg'][0]:
                subprocess.run([TG_CHANGE_BIN, "-w", fields['watch_tg'][0]])
            if 'restore_tg' in fields and fields['restore_tg'][0]:
                subprocess.run([TG_CHANGE_BIN, f"-r", fields['restore_tg'][0]])
            if 'delay' in fields and fields['delay'][0]:
                subprocess.run([TG_CHANGE_BIN, f"-t", fields['delay'][0]])
        
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
