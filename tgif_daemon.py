#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time, threading, re, subprocess, sys

VERSION = "v2.9.0"
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
            try:
                with open(CONF_FILE, 'r', encoding='utf-8') as f:
                    c = f.read()
                    w = re.search(r'WATCH_TG="(\d+)"', c)
                    r = re.search(r'RESTORE_TG="(\d+)"', c)
                    d = re.search(r'RESTORE_DELAY="(\d+)"', c)
                    if w: self.watch_tg = w.group(1)
                    if r: self.restore_tg = r.group(1)
                    if d: self.delay = int(d.group(1))
            except: pass
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
    res = subprocess.run(["/usr/local/bin/tg_change", f"-{cfg.restore_tg}"], capture_output=True, text=True)
    if res.stdout:
        for l in res.stdout.splitlines(): log(l)

def get_latest_log():
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        return os.path.join(LOG_DIR, max(files)) if files else None
    except: return None

def main_loop():
    log(f"🚀 TGIFChanger Daemon {VERSION} 監視開始")
    current_log = get_latest_log()
    if not current_log: return
    
    with open(current_log, "r", errors="ignore") as f:
        f.seek(0, 2)
        active_tg = None
        while True:
            line = f.readline()
            if not line:
                if get_latest_log() != current_log: break
                time.sleep(0.05); continue
            
            # --- 受信検知ロジック (Busyランプ連動) ---
            if "voice header" in line.lower() and "to tg" in line.lower():
                m = re.search(r'to TG\s+(\d+)', line, re.I)
                if m:
                    active_tg = m.group(1)
                    log(f"⚡ 信号検知: TG {active_tg}")
                    set_gpio(True) # どんなTGでも信号があれば点灯
                    
                    global restore_timer
                    if restore_timer: restore_timer.cancel()

            # --- 信号終了ロジック ---
            if "end of voice" in line.lower() or "end of transmission" in line.lower():
                log(f"🌑 信号終了 (TG {active_tg if active_tg else '??'})")
                set_gpio(False) # 信号が切れたら消灯
                
                # 監視TG以外なら復帰タイマーを始動
                if active_tg and active_tg != cfg.watch_tg:
                    log(f"⏳ 復帰タイマー始動: {cfg.delay}s後に TG {cfg.restore_tg} へ戻ります")
                    if restore_timer: restore_timer.cancel()
                    restore_timer = threading.Timer(cfg.delay, do_restore)
                    restore_timer.start()

if __name__ == "__main__":
    while True:
        try: main_loop()
        except KeyboardInterrupt: sys.exit(0)
        except: time.sleep(2)
