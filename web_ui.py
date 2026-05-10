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
        watch_disp = f"TG {conf['WATCH_TG']}" if conf['WATCH_TG'] else "未設定"
        restore_disp = f"TG {conf['RESTORE_TG']}" if conf['RESTORE_TG'] else "未設定"
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TGIFChanger Web UI</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; padding: 15px; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }}
                h2 {{ text-align: center; color: #444; }}
                button {{ background: #007bff; color: white; border: none; padding: 12px; border-radius: 6px; cursor: pointer; margin: 8px 0; width: 100%; font-size: 16px; font-weight: bold; transition: opacity 0.2s; }}
                button:active {{ opacity: 0.8; }}
                button.danger {{ background: #dc3545; }}
                button.success {{ background: #28a745; }}
                input {{ width: 100%; padding: 10px; margin: 5px 0 15px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; font-size: 16px; }}
                label {{ font-weight: bold; font-size: 14px; color: #666; }}
                .status-val {{ float: right; font-weight: bold; color: #007bff; }}
                p {{ margin: 10px 0; padding-bottom: 10px; border-bottom: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🚀 TGIFChanger Dashboard</h2>
                <div class="card">
                    <h3>📊 現在のステータス</h3>
                    <p>監視TG (WATCH) <span class="status-val">{watch_disp}</span></p>
                    <p>復帰TG (RESTORE) <span class="status-val">{restore_disp}</span></p>
                    <p style="border:none;">復帰までの時間 <span class="status-val">{conf['RESTORE_DELAY']} 秒</span></p>
                </div>
                <div class="card">
                    <h3>⚡ クイック操作</h3>
                    <form method="POST" action="/stop"><button type="submit" class="danger">🛑 タイマー強制停止 (STOP)</button></form>
                    <form method="POST" action="/restore"><button type="submit" class="success">🏠 復帰TGへ今すぐ戻る</button></form>
                </div>
                <div class="card">
                    <h3>⚙️ 設定変更</h3>
                    <form method="POST" action="/config">
                        <label>監視TG (WATCH_TG)</label>
                        <input type="number" name="watch_tg" placeholder="例: 6" value="{conf['WATCH_TG']}">
                        <label>復帰TG (RESTORE_TG)</label>
                        <input type="number" name="restore_tg" placeholder="例: 44833" value="{conf['RESTORE_TG']}">
                        <label>復帰時間 (秒)</label>
                        <input type="number" name="delay" value="{conf['RESTORE_DELAY']}">
                        <button type="submit">💾 設定を保存して反映</button>
                    </form>
                </div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        if self.path == "/stop":
            subprocess.run([TG_CHANGE_BIN, "-s"])
        elif self.path == "/restore":
            conf = get_config()
            if conf['RESTORE_TG']: subprocess.run([TG_CHANGE_BIN, f"-{conf['RESTORE_TG']}"])
        elif self.path == "/config":
            if 'watch_tg' in fields and fields['watch_tg'][0]:
                subprocess.run([TG_CHANGE_BIN, "-w", fields['watch_tg'][0]])
            if 'restore_tg' in fields and fields['restore_tg'][0]:
                subprocess.run([TG_CHANGE_BIN, "-r", fields['restore_tg'][0]])
            if 'delay' in fields and fields['delay'][0]:
                subprocess.run([TG_CHANGE_BIN, "-t", fields['delay'][0]])
        
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
