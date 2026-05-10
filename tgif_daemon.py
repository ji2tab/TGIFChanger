#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Professional Unified Daemon (v2.7.1)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: Ultra-high sensitivity log monitor for WPSD/Pi-Star.
#              Optimized for instant Talkgroup detection and auto-restore.
# =============================================================================

import os
import time
import threading
import re
import subprocess
import sys

# --- システム定数 ---
VERSION = "v2.7.1"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
LOG_DIR = "/var/log/pi-star"

def log(msg):
    """journalctlに即座に出力 (バッファなし)"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    def __init__(self):
        self.watch_tg = "6"; self.restore_tg = "44833"; self.delay = 120; self.gpio_pin = "17"
        self.load()
    def load(self):
        if os.path.exists(CONF_FILE):
            try:
                with open(CONF_FILE, 'r') as f:
                    c = f.read()
                    w = re.search(r'WATCH_TG="(\d+)"', c)
                    r = re.search(r'RESTORE_TG="(\d+)"', c)
                    d = re.search(r'RESTORE_DELAY="(\d+)"', c)
                    if w: self.watch_tg = w.group(1)
                    if r: self.restore_tg = r.group(1)
                    if d: self.delay = int(d.group(1))
            except Exception as e: log(f"⚠️ 読込エラー: {e}")
        log(f"⚙️ 設定反映: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

cfg = Config()
restore_timer = None

def set_gpio(state):
    try:
        mode = "dh" if state else "dl"
        subprocess.run(["pinctrl", "set", cfg.gpio_pin, "op", mode], check=False, capture_output=True)
    except: pass

def do_restore():
    log(f"🏠 復帰実行: TG {cfg.restore_tg} へ戻ります")
    subprocess.run(["/usr/local/bin/tg_change", f"-{cfg.restore_tg}"], check=False)

def command_listener():
    """Web UIからの割り込み（設定変更やタイマー停止）を監視"""
    if os.path.exists(CMD_FIFO): os.remove(CMD_FIFO)
    try:
        os.mkfifo(CMD_FIFO); os.chmod(CMD_FIFO, 0o666)
    except: return
    while True:
        try:
            with open(CMD_FIFO, 'r') as fifo:
                for line in fifo:
                    if "reload" in line: cfg.load()
                    if "stop" in line:
                        global restore_timer
                        if restore_timer: restore_timer.cancel(); log("🛑 タイマー強制停止")
        except: time.sleep(0.5)

def get_latest_log():
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        return os.path.join(LOG_DIR, max(files)) if files else None
    except: return None

def main_loop():
    log(f"🚀 TGIFChanger-Py {VERSION} 監視開始 (高精度モード)")
    threading.Thread(target=command_listener, daemon=True).start()
    
    current_log_path = get_latest_log()
    if not current_log_path:
        log("❌ ログファイルが見つかりません"); return

    log(f"📂 監視対象: {os.path.basename(current_log_path)}")

    with open(current_log_path, "r", errors="ignore") as f:
        # 起動時は末尾へ。ただし、テストのために直近の10行だけ読み直す設定に
        f.seek(0, 2)
        
        active_tg = None
        while True:
            line = f.readline()
            if not line:
                # ログファイルのローテーションチェック
                new_path = get_latest_log()
                if new_path and new_path != current_log_path:
                    log("🔄 ログファイルが更新されました。開き直します。")
                    break # while True を抜けて開き直し
                time.sleep(0.1); continue
            
            # --- 解析セクション ---
            # WPSD/Pi-StarのログからTG番号を抽出 (大文字小文字を問わず、Net/RF両方に対応)
            # 例: "received network voice header from ... to TG 6"
            # 例: "locally originating RF voice header from ... to TG 44833"
            if "voice header" in line.lower() and "to tg" in line.lower():
                m = re.search(r'to TG\s+(\d+)', line, re.I)
                if m:
                    active_tg = m.group(1)
                    log(f"⚡ 信号検知: TG {active_tg}")
                    set_gpio(True)
                    global restore_timer
                    if restore_timer: restore_timer.cancel()

            # 交信終了の検知
            if "end of voice" in line.lower() or "end of transmission" in line.lower():
                log("🌑 信号終了")
                set_gpio(False)
                if active_tg and active_tg != cfg.watch_tg:
                    log(f"⏳ 復帰タイマー始動: {cfg.delay}s後に TG {cfg.restore_tg} へ戻ります")
                    if restore_timer: restore_timer.cancel()
                    restore_timer = threading.Timer(cfg.delay, do_restore)
                    restore_timer.start()

if __name__ == "__main__":
    while True:
        try:
            main_loop()
        except KeyboardInterrupt:
            log("👋 終了します"); sys.exit(0)
        except Exception as e:
            log(f"⚠️ エラー再起動: {e}"); time.sleep(2)
