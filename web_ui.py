#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Web Dashboard (v2.5.9)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: Professional Web Interface for TGIF Talkgroup management.
#              This script is self-contained and serves a mobile-responsive UI.
# =============================================================================

import http.server
import socketserver
import urllib.parse
import subprocess
import os
import sys

# --- システム設定 ---
PORT = 8080
CONF_FILE = "/etc/tgifchanger.conf"
TG_CHANGE_BIN = "/usr/local/bin/tg_change"

def get_config():
    """設定ファイルから現在の値をパースして取得する"""
    conf = {"WATCH_TG": "", "RESTORE_TG": "", "RESTORE_DELAY": "120"}
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    # 有効な設定行（キー=値）のみを抽出
                    if "=" in line and not line.strip().startswith("#"):
                        try:
                            k, v = line.split("=", 1)
                            conf[k.strip()] = v.strip().strip('"').strip("'")
                        except:
                            pass
        except Exception as e:
            # ログ出力用
            print(f"Config Load Error: {e}", file=sys.stderr)
    return conf

class Handler(http.server.BaseHTTPRequestHandler):
    """HTTPサーバーのリクエスト処理クラス"""

    def log_message(self, format, *args):
        """標準のログ出力を抑制（ジャーナルを汚さないため）"""
        return

    def do_GET(self):
        """管理画面のHTMLを生成して送信する"""
        conf = get_config()
        
        # 画面表示用の文字列生成
        watch_disp = f"TG {conf['WATCH_TG']}" if conf['WATCH_TG'] else "未設定"
        restore_disp = f"TG {conf['RESTORE_TG']}" if conf['RESTORE_TG'] else "未設定"
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        # UIデザイン（CSS込みのフルHTML）
        html = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TGIFChanger Dashboard</title>
            <style>
                body {{ font-family: -apple-system, sans-serif; background-color: #f0f4f8; color: #2d3748; margin: 0; padding: 20px; }}
                .wrapper {{ max-width: 480px; margin: 0 auto; }}
                .card {{ background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); padding: 25px; margin-bottom: 20px; }}
                h2 {{ margin: 0 0 20px 0; font-size: 1.5rem; text-align: center; color: #1a202c; border-bottom: 2px solid #e2e8f0; padding-bottom: 15px; }}
                h3 {{ margin: 0 0 15px 0; font-size: 1.1rem; color: #4a5568; }}
                
                .info-row {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #edf2f7; }}
                .info-row:last-child {{ border-bottom: none; }}
                .label {{ color: #718096; font-weight: 500; }}
                .value {{ color: #3182ce; font-weight: 800; font-family: monospace; font-size: 1.1rem; }}
                
                button {{ width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 10px; cursor: pointer; font-size: 16px; font-weight: bold; transition: 0.3s; color: white; }}
                .btn-save {{ background-color: #3182ce; }}
                .btn-stop {{ background-color: #e53e3e; }}
                .btn-home {{ background-color: #38a169; }}
                button:hover {{ opacity: 0.85; transform: scale(0.98); }}
                
                label {{ display: block; margin-top: 15px; font-weight: bold; color: #4a5568; font-size: 0.9rem; }}
                input {{ width: 100%; padding: 12px; margin: 8px 0 15px 0; border: 2px solid #e2e8f0; border-radius: 8px; box-sizing: border-box; font-size: 16px; }}
                input:focus {{ border-color: #3182ce; outline: none; }}
                
                .footer {{ text-align: center; margin-top: 30px; color: #a0aec0; font-size: 0.85rem; }}
            </style>
        </head>
        <body>
            <div class="wrapper">
                <div class="card">
                    <h2>🚀 TGIFChanger</h2>
                    <div class="info-row"><span class="label">監視中 (WATCH)</span><span class="value">{watch_disp}</span></div>
                    <div class="info-row"><span class="label">復帰先 (RESTORE)</span><span class="value">{restore_disp}</span></div>
                    <div class="info-row"><span class="label">待機時間</span><span class="value">{conf['RESTORE_DELAY']}s</span></div>
                </div>

                <div class="card">
                    <h3>⚡ クイック操作</h3>
                    <form method="POST" action="/stop"><button type="submit" class="btn-stop">🛑 復帰タイマーを停止</button></form>
                    <form method="POST" action="/restore"><button type="submit" class="btn-home">🏠 復帰TGへ今すぐ戻る</button></form>
                </div>

                <div class="card">
                    <h3>⚙️ 設定変更</h3>
                    <form method="POST" action="/config">
                        <label>監視対象TG</label>
                        <input type="number" name="watch_tg" value="{conf['WATCH_TG']}" placeholder="例: 6">
                        <label>自動復帰先TG</label>
                        <input type="number" name="restore_tg" value="{conf['RESTORE_TG']}" placeholder="例: 44833">
                        <label>待ち時間 (秒)</label>
                        <input type="number" name="delay" value="{conf['RESTORE_DELAY']}">
                        <button type="submit" class="btn-save">💾 設定を保存して反映</button>
                    </form>
                </div>
                <div class="footer">
                    Designed for JI2TAB Amateur Radio Station
                </div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        """フォームからのデータを処理する"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        # 1. 設定変更の処理
        if self.path == "/config":
            # ログの重複を避けるため、保存は --save-only で行い、最後に一度だけリロード通知
            if 'watch_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-w", fields['watch_tg'][0]], check=False)
            if 'restore_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-r", fields['restore_tg'][0]], check=False)
            if 'delay' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-t", fields['delay'][0]], check=False)
            
            # デーモンへ設定の再読み込みを通知
            subprocess.run([TG_CHANGE_BIN, "--notify-only"], check=False)
            
        # 2. タイマー停止の処理
        elif self.path == "/stop":
            subprocess.run([TG_CHANGE_BIN, "-s"], check=False)
            
        # 3. 復帰APIの実行
        elif self.path == "/restore":
            c = get_config()
            if c['RESTORE_TG']:
                subprocess.run([TG_CHANGE_BIN, f"-{c['RESTORE_TG']}"], check=False)
        
        # 処理完了後、トップページ（GET）へリダイレクト
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

# --- サーバー起動 ---
if __name__ == "__main__":
    # ポートが既に使用されている場合のエラーを回避
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            # 起動メッセージを標準出力へ（journalctlで確認可能）
            print(f"[{Handler.log_date_time_string(Handler)}] 🌐 Web UI started on port {PORT}", flush=True)
            httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"❌ Web Server Fatal Error: {e}", file=sys.stderr)
        sys.exit(1)
