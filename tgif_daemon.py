#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Focused Daemon (v2.8.0)
# =============================================================================
import os, time, threading, re, subprocess, sys

VERSION = "v2.8.0"
CONF_FILE = "/etc/tgifchanger.conf"
LOG_DIR = "/var/log/pi-star"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    def __init__(self):
        self.watch_tg = "6"; self.restore_tg = "44833"; self.delay = 120; self.gpio_pin = "17"
        self.load()
    def load(self):
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, 'r', encoding='utf-8') as f:
                c = f.read()
                w = re.search(r'WATCH_TG="(\d+)"', c)
                r = re.search(r'RESTORE_TG="(\d+)"', c)
                d = re.search(r'RESTORE_DELAY="(\d+)"', c)
                if w: self.watch_tg = w.group(1)
                if r: self.restore_tg = r.group(1)
                if d: self.delay = int(d.group(1))
        log(f"⚙️ 設定読込: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

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

def get_latest_log():
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        return os.path.join(LOG_DIR, max(files)) if files else None
    except: return None

def main_loop():
    log(f"🚀 TGIFChanger Daemon {VERSION} 監視開始 (Focused)")
    current_log = get_latest_log()
    if not current_log: return
    with open(current_log, "r", errors="ignore") as f:
        f.seek(0, 2)
        active_tg = None
        while True:
            line = f.readline()
            if not line:
                if get_latest_log() != current_log: break
                time.sleep(0.1); continue
            
            if "voice header" in line.lower() and "to tg" in line.lower():
                m = re.search(r'to TG\s+(\d+)', line, re.I)
                if m:
                    active_tg = m.group(1)
                    if active_tg != cfg.watch_tg:
                        log(f"⚡ 信号検知: TG {active_tg} (LED点灯)")
                        set_gpio(True)
                    else:
                        log(f"💤 監視TG受信: TG {active_tg}")
                    global restore_timer
                    if restore_timer: restore_timer.cancel()

            if "end of voice" in line.lower() or "end of transmission" in line.lower():
                set_gpio(False)
                if active_tg and active_tg != cfg.watch_tg:
                    log(f"⏳ 復帰タイマー始動: {cfg.delay}s")
                    if restore_timer: restore_timer.cancel()
                    restore_timer = threading.Timer(cfg.delay, do_restore)
                    restore_timer.start()

if __name__ == "__main__":
    while True:
        try: main_loop()
        except KeyboardInterrupt: sys.exit(0)
        except: time.sleep(2)
