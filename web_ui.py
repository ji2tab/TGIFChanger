#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Professional Web Dashboard (v2.5.8)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: This script provides a lightweight, mobile-responsive web 
#              interface to manage TGIF Talkgroups on WPSD/Pi-Star systems.
#              Synchronizes with tgif_daemon via FIFO commands.
# =============================================================================

import http.server
import socketserver
import urllib.parse
import subprocess
import os
import sys

# --- 構成設定 ---
PORT = 8080
CONF_FILE = "/etc/tgifchanger.conf"
TG_CHANGE_BIN = "/usr/local/bin/tg_change"

def get_config():
    """設定ファイルから現在の値を読み取って辞書で返す"""
    conf = {"WATCH_TG": "", "RESTORE_TG": "", "RESTORE_DELAY": "120"}
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, 'r') as f:
                for line in f:
                    # コメント行を除外し、キー=値のペアを抽出
                    if "=" in line and not line.strip().startswith("#"):
                        try:
                            k, v = line.split("=", 1)
                            conf[k.strip()] = v.strip().strip('"').strip("'")
                        except:
                            pass
        except Exception:
            pass
    return conf

class Handler(http.server.BaseHTTPRequestHandler):
    """HTTPリクエストハンドラ"""

    def do_GET(self):
        """ダッシュボード画面のレンダリング"""
        conf = get_config()
        
        # 表示用文字列の整理
        watch_disp = f"TG {conf['WATCH_TG']}" if conf['WATCH_TG'] else "未設定"
        restore_disp = f"TG {conf['RESTORE_TG']}" if conf['RESTORE_TG'] else "未設定"
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        # HTML/CSS 完全版（省略なし）
        html = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TGIFChanger Dashboard</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f7f9; color: #333; margin: 0; padding: 20px; line-height: 1.6; }}
                .container {{ max-width: 480px; margin: 0 auto; }}
                .card {{ background: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 20px; }}
                h2 {{ margin: 0 0 20px 0; font-size: 1.4em; color: #1a202c; text-align: center; border-bottom: 2px solid #edf2f7; padding-bottom: 10px; }}
                h3 {{ margin: 0 0 15px 0; font-size: 1.1em; color: #2d3748; }}
                .status-row {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
                .status-row:last-child {{ border-bottom: none; }}
                .status-label {{ color: #718096; font-size: 0.95em; font-weight: 500; }}
                .status-value {{ color: #3182ce; font-weight: 700; font-family: 'Courier New', monospace; }}
                
                button {{ width: 100%; padding: 14px; margin: 8px 0; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 600; transition: all 0.2s ease; }}
                .btn-primary {{ background-color: #3182ce; color: white; }}
                .btn-danger {{ background-color: #e53e3e; color: white; }}
                .btn-success {{ background-color: #38a169; color: white; }}
                button:hover {{ filter: brightness(1.1); transform: translateY(-1px); }}
                button:active {{ transform: translateY(0); }}
                
                label {{ display: block; margin-top: 15px; margin-bottom: 5px; font-size: 0.9em; font-weight: 600; color: #4a5568; }}
                input[type="number"] {{ width: 100%; padding: 12px; border: 2px solid #e2e8f0; border-radius: 8px; box-sizing: border-box; font-size: 16px; transition: border-color 0.2s; }}
                input[type="number"]:focus {{ border-color: #3182ce; outline: none; }}
                .footer {{ text-align: center; font-size: 0.8em; color: #a0aec0; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card">
                    <h2>🚀 TGIFChanger</h2>
                    <div class="status-row">
                        <span class="status-label">監視中のTalkgroup</span>
                        <span class="status-value">{watch_disp}</span>
                    </div>
                    <div class="status-row">
                        <span class="status-label">復帰先Talkgroup</span>
                        <span class="status-value">{restore_disp}</span>
                    </div>
                    <div class="status-row">
                        <span class="status-label">自動復帰タイマー</span>
                        <span class="status-value">{conf['RESTORE_DELAY']} 秒</span>
                    </div>
                </div>

                <div class="card">
                    <h3>⚡ クイックアクション</h3>
                    <form method="POST" action="/stop">
                        <button type="submit" class="btn-danger">🛑 タイマーを強制停止</button>
                    </form>
                    <form method="POST" action="/restore">
                        <button type="submit" class="btn-success">🏠 復帰先へ即座に接続</button>
                    </form>
                </div>

                <div class="card">
                    <h3>⚙️ システム設定</h3>
                    <form method="POST" action="/config">
                        <label>監視対象TG (WATCH_TG)</label>
                        <input type="number" name="watch_tg" value="{conf['WATCH_TG']}" placeholder="例: 6">
                        
                        <label>復帰先TG (RESTORE_TG)</label>
                        <input type="number" name="restore_tg" value="{conf['RESTORE_TG']}" placeholder="例: 44833">
                        
                        <label>待ち時間 (秒)</label>
                        <input type="number" name="delay" value="{conf['RESTORE_DELAY']}">
                        
                        <button type="submit" class="btn-primary">💾 設定を保存して反映</button>
                    </form>
                </div>
                <div class="footer">
                    TGIFChanger-Py {VERSION} | Designed by JI2TAB
                </div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        """フォームからの命令実行"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        fields = urllib.parse.parse_qs(post_data)
        
        if self.path == "/config":
            # ログの複数出力を防ぐため、保存は --save-only で行い、最後に一度だけ通知する
            if 'watch_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-w", fields['watch_tg'][0]])
            if 'restore_tg' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-r", fields['restore_tg'][0]])
            if 'delay' in fields:
                subprocess.run([TG_CHANGE_BIN, "--save-only", "-t", fields['delay'][0]])
            
            # デーモンに一括リロードを通知
            subprocess.run([TG_CHANGE_BIN, "--notify-only"])
            
        elif self.path == "/stop":
            # タイマー停止命令
            subprocess.run([TG_CHANGE_BIN, "-s"])
            
        elif self.path == "/restore":
            # 現在の設定を読み直して復帰TGを取得し、APIを叩く
            curr = get_config()
            if curr['RESTORE_TG']:
                # tg_change のハイフン付き引数でAPI送信を実行
                subprocess.run([TG_CHANGE_BIN, f"-{curr['RESTORE_TG']}"])
        
        # 処理後はトップへリダイレクト
        self.send_response(3
