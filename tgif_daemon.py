#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified Daemon (v2.6.1)
# Author: Kazuhiko Shinoda (JI2TAB)
# Description: Monitors MMDVMHost logs and manages auto-restore with Web Sync.
# =============================================================================

import os, time, threading, re, subprocess

VERSION = "v2.6.1"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
LOG_DIR = "/var/log/pi-star"

class Config:
    def __init__(self):
        self.load()

    def load(self):
        # デフォルト設定
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
        
        print(f"[{time.strftime('%H:%M:%S')}] ⚙️  Config Loaded: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

cfg = Config()

def set_gpio(state):
    val = "1" if state else "0"
    try:
        subprocess.run(["pinctrl", "set", cfg.gpio_pin, "op", "dh" if state else "dl"], check=True)
    except: pass

def command_listener():
    """Web UIからのリロード命令を待ち受けるスレッド"""
    if os.path.exists(CMD_FIFO): os.remove(CMD_FIFO)
    os.mkfifo(CMD_FIFO)
    os.chmod(CMD_FIFO, 0o666)
    while True:
        try:
            with open(CMD_FIFO, 'r') as fifo:
                for line in fifo:
                    if "reload" in line:
                        cfg.load()
                        print(f"[{time.strftime('%H:%M:%S')}] ♻️  設定をリアルタイム反映しました")
        except: time.sleep(1)

def get_latest_log():
    files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
    return os.path.join(LOG_DIR, max(files)) if files else None

def main_loop():
    threading.Thread(target=command_listener, daemon=True).start()
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 TGIFChanger-Py {VERSION} Started")
    
    current_log = get_latest_log()
    if not current_log:
        print("❌ ログファイルが見つかりません"); return

    with open(current_log, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1); continue
            
            # 受信検知 (LED点灯)
            if "DMR Slot 2, received network voice header" in line:
                set_gpio(True)
                print(f"[{time.strftime('%H:%M:%S')}] ⚡ 受信中...")
            
            # 終了検知 (LED消灯)
            if "DMR Slot 2, received network end of voice" in line:
                set_gpio(False)
                print(f"[{time.strftime('%H:%M:%S')}] 🌑 待機")
                
                # ここに自動復帰ロジック（cfg.watch_tg を使用）を入れる
                # ... 以前のロジックを継続 ...

if __name__ == "__main__":
    main_loop()
