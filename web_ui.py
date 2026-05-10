#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Web Dashboard (v2.5.7)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Lightweight Web UI for TGIFChanger control.
# =============================================================================

import http.server
import socketserver
import urllib.parse
import subprocess
import os

PORT = 8080
CONF_FILE = "/etc/tgifchanger.conf"
TG_CHANGE_BIN = "/usr/local/bin/tg_change"

def get_config():
    """現在の設定をファイルから読み取って辞書形式で返す"""
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
        """ブラウザに管理画面のHTMLを返す"""
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
                body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; padding: 15px; color: #333; }}
                .container {{ max-width: 500px; margin: 0 auto; }}
                .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }}
                h2, h3 {{ margin-top: 0; color: #1a1a1a; }}
                .status-item {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }}
                .status-val {{ font-weight: bold; color: #007bff; }}
                button {{ width: 100%; padding: 14px; margin: 8px 0; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; color: white; transition: 0.2s; }}
                .btn-blue {{ background: #007bff; }}
                .btn-red {{ background: #dc3545; }}
                .btn-green {{ background: #28a745; }}
                button:hover {{ opacity: 0.9; }}
                input {{ width: 100%; padding: 12px; margin: 10px 0 20px 0; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 16px; }}
                label {{ font-size: 14px; font-weight: bold; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card">
                    <h2>🚀 TGIFChanger</h2>
                    <div class="status-item"><span>監視対象 (WATCH)</span><span class="status-val">{watch_disp}</span></div>
                    <div class="status-item"><span>復帰先 (RESTORE)</span><span class="status-val">{restore_disp}</span></div>
                    <div class="status-item" style="border:none;"><span>自動復帰時間</span><span class="status-val">{conf['RESTORE_DELAY']} 秒</span></div>
                </div>

                <div class="card">
                    <h3>⚡ クイック操作</h3>
                    <form method="POST" action="/stop"><button type="submit" class="btn-red">🛑 復帰タイマーを今すぐ止める</button></form>
                    <form method="POST" action="/restore"><button type="submit" class="btn-green">🏠 復帰TG ({conf['RESTORE_TG']}) へ接続</button></form>
                </div>

                <div class="card">
                    <h3>⚙️ 基本設定の変更</h3>
                    <form method="POST" action="/config">
                        <label>監視するTG番号</label>
                        <input type="number" name="watch_tg" value="{conf['WATCH_TG']}" placeholder="例: 6">
                        <label>自動復帰するTG番号</label>
                        <input type="number" name="restore_tg" value="{conf['RESTORE_TG']}" placeholder="例: 44833">
                        <label>復帰までの待ち時間 (秒)</label>
                        <input type="number" name="delay" value="{conf['RESTORE_DELAY']}">
                        <button type="submit" class="btn-blue">💾 設定を保存して反映</button>
                    </form>
                </div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        """フォームからの送信を処理し、コマンドを実行する"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        if self.path == "/config":
            # 各項目を個別に保存（デーモンへの通知は最後に行う）
            if 'watch_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-w", fields['watch_tg'][0]])
            if 'restore_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-r", fields['restore_tg'][0]])
            if 'delay' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-t", fields['delay'][0]])
            # 最後に一度だけデーモンをリロード
            subprocess.run([TG_CHANGE_BIN, "--notify-only"])
            
        elif self.path == "/stop":
            subprocess.run([TG_CHANGE_BIN, "-s"])
            
        elif self.path == "/restore":
            c = get_config()
            if c['RESTORE_TG']:
                subprocess.run([TG_CHANGE_BIN, f"-{c['RESTORE_TG']}"])
        
        # 処理完了後、トップ画面にリダイレクト
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

if __name__ == "__main__":
    # ポートの再利用を許可してサーバー起動
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
