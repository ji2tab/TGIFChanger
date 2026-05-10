#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified Daemon (v2.6.2)
# =============================================================================

import os, time, threading, re, subprocess, sys

VERSION = "v2.6.2"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
LOG_DIR = "/var/log/pi-star"

# ログ出力を即座に反映させるための関数
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    def __init__(self):
        self.load()

    def load(self):
        self.watch_tg = "6"
        self.restore_tg = "44833"
        self.delay = 120
        self.gpio_pin = "17"
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, 'r') as f:
                content = f.read()
                w = re.search(r'^\s*WATCH_TG\s*=\s*["\']?(\d+)["\']?', content, re.M)
                r = re.search(r'^\s*RESTORE_TG\s*=\s*["\']?(\d+)["\']?', content, re.M)
                d = re.search(r'^\s*RESTORE_DELAY\s*=\s*["\']?(\d+)["\']?', content, re.M)
                g = re.search(r'^\s*GPIO_PIN\s*=\s*["\']?(\d+)["\']?', content, re.M)
                if w: self.watch_tg = w.group(1)
                if r: self.restore_tg = r.group(1)
                if d: self.delay = int(d.group(1))
                if g: self.gpio_pin = g.group(1)
        log(f"⚙️  設定反映: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

cfg = Config()

def set_gpio(state):
    try:
        mode = "dh" if state else "dl"
        subprocess.run(["pinctrl", "set", cfg.gpio_pin, "op", mode], check=False)
    except: pass

def command_listener():
    """Web UIからのリロード命令を待機"""
    if os.path.exists(CMD_FIFO): os.remove(CMD_FIFO)
    os.mkfifo(CMD_FIFO)
    os.chmod(CMD_FIFO, 0o666)
    while True:
        try:
            with open(CMD_FIFO, 'r') as fifo:
                for line in fifo:
                    if "reload" in line: cfg.load()
        except: time.sleep(1)

def get_latest_log():
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        return os.path.join(LOG_DIR, max(files)) if files else None
    except: return None

def main_loop():
    log(f"🚀 TGIFChanger-Py {VERSION} 起動プロセス開始...")
    
    # コマンド待機スレッド開始
    threading.Thread(target=command_listener, daemon=True).start()
    
    current_log = get_latest_log()
    if not current_log:
        log("❌ ログファイルが見つかりません。終了します。")
        return

    log(f"📁 監視対象: {os.path.basename(current_log)}")

    with open(current_log, "r") as f:
        f.seek(0, 2) # ファイルの末尾へ移動
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            # 受信開始検知
            if "received network voice header" in line and f"to TG {cfg.watch_tg}" in line:
                log(f"⚡ 受信開始 (TG {cfg.watch_tg})")
                set_gpio(True)
            
            # 受信終了検知
            if "received network end of voice" in line:
                log("🌑 受信終了 / 待機")
                set_gpio(False)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log("👋 終了します。")
