#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Web UI (v2.5.2)
# =============================================================================

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
        watch_disp = f"TG {conf['WATCH_TG']}" if conf['WATCH_TG'] else "未設定"
        restore_disp = f"TG {conf['RESTORE_TG']}" if conf['RESTORE_TG'] else "未設定"
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        html = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TGIFChanger Dashboard</title>
            <style>
                body {{ font-family: sans-serif; background: #f0f2f5; padding: 20px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto 20px; }}
                h2, h3 {{ margin-top: 0; color: #333; }}
                .status-val {{ float: right; font-weight: bold; color: #007bff; }}
                input {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
                button {{ width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }}
                button:hover {{ opacity: 0.9; }}
                .btn-red {{ background: #dc3545; margin-bottom: 10px; }}
                .btn-green {{ background: #28a745; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🚀 TGIFChanger</h2>
                <p>監視TG: <span class="status-val">{watch_disp}</span></p>
                <p>復帰TG: <span class="status-val">{restore_disp}</span></p>
                <p>復帰時間: <span class="status-val">{conf['RESTORE_DELAY']} 秒</span></p>
            </div>
            <div class="card">
                <h3>⚡ クイック操作</h3>
                <form method="POST" action="/stop"><button type="submit" class="btn-red">🛑 タイマー停止</button></form>
                <form method="POST" action="/restore"><button type="submit" class="btn-green">🏠 復帰TGへ戻る</button></form>
            </div>
            <div class="card">
                <h3>⚙️ 設定変更</h3>
                <form method="POST" action="/config">
                    <label>監視TG</label><input type="number" name="watch_tg" value="{conf['WATCH_TG']}">
                    <label>復帰TG</label><input type="number" name="restore_tg" value="{conf['RESTORE_TG']}">
                    <label>復帰時間(秒)</label><input type="number" name="delay" value="{conf['RESTORE_DELAY']}">
                    <button type="submit">💾 設定を保存して反映</button>
                </form>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        if self.path == "/config":
            if 'watch_tg' in fields: subprocess.run([TG_CHANGE_BIN, "-w", fields['watch_tg'][0]])
            if 'restore_tg' in fields: subprocess.run([TG_CHANGE_BIN, "-r", fields['restore_tg'][0]])
            if 'delay' in fields: subprocess.run([TG_CHANGE_BIN, "-t", fields['delay'][0]])
        
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
