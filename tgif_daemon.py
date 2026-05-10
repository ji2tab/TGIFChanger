#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
# 
# File:        tgif_daemon.py
# Version:     v2.1.5 (EOF Buffer Fix Edition)
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# =============================================================================

import os, sys, time, re, threading, subprocess, glob, urllib.request

VERSION = "v2.1.5"
CONF_FILE = "/etc/tgifchanger.conf"
MMDVM_CONF = "/etc/mmdvmhost"
DMRGW_CONF = "/etc/dmrgateway"
CMD_FIFO = "/run/tgifchanger.cmd"

config = {
    "LOG_DIR": "/var/log/pi-star",
    "WATCH_SLOT": "2",
    "RESTORE_SLOT": "2",
    "WATCH_TG": "",
    "RESTORE_TG": "",
    "GPIO_PIN": "17",
    "GPIO_CHIP": "0",
    "RESTORE_DELAY": "120",
    "TGIF_API": "http://tgif.network:5040/api/sessions/update",
    "TGIF_API_TIMEOUT": "10"
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def load_config():
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            log(f"⚠️ Config Load Error: {e}")

class GPIOEngine:
    def __init__(self, pin, chip):
        self.pin, self.chip = str(pin), str(chip)
        self.state = -1
        self.high_start_time = 0
        self.engine = self.detect()

    def detect(self):
        if subprocess.run("command -v pinctrl", shell=True, stdout=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["pinctrl", "set", self.pin, "op", "pn", "dl"])
            return "pinctrl"
        if subprocess.run("command -v raspi-gpio", shell=True, stdout=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["raspi-gpio", "set", self.pin, "op", "pn", "dl"])
            return "raspi-gpio"
        return "sysfs"

    def set(self, val):
        if self.state == val: return
        try:
            if self.engine == "pinctrl": subprocess.run(["pinctrl", "set", self.pin, "dh" if val else "dl"])
            elif self.engine == "raspi-gpio": subprocess.run(["raspi-gpio", "set", self.pin, "dh" if val else "dl"])
            elif self.engine == "sysfs":
                with open(f"/sys/class/gpio/gpio{self.pin}/value", "w") as f: f.write(str(val))
        except Exception as e: log(f"⚠️ GPIO Error: {e}")
        
        self.high_start_time = time.time() if val == 1 else 0
        self.state = val
        log(f"⚡ GPIO{self.pin} -> HIGH" if val else f"🌑 GPIO{self.pin} -> LOW")

class App:
    def __init__(self):
        load_config()
        self.gpio = GPIOEngine(config["GPIO_PIN"], config["GPIO_CHIP"])
        self.timer = None
        self.dmr_id = self.get_dmr_id()
        self.my_call = self.get_my_callsign()
        self.watch_tg, self.restore_tg = self.get_dynamic_tgs()
        
        log(f"🚀 TGIFChanger-Py {VERSION} Active (Native Engine)")
        log(f"   HOME=TG{self.restore_tg}/Slot{config['RESTORE_SLOT']}  DELAY={config['RESTORE_DELAY']}s")
        log(f"   WATCH=TG{self.watch_tg} (DMR ID: {self.dmr_id})")

    def get_dmr_id(self):
        for path in [DMRGW_CONF, MMDVM_CONF]:
            if os.path.exists(path):
                with open(path, 'r', errors='ignore') as f:
                    for line in f:
                        if line.startswith("Id="): return line.split("=")[1].split("#")[0].strip()
        return "Unknown"

    def get_my_callsign(self):
        if os.path.exists(MMDVM_CONF):
            with open(MMDVM_CONF, 'r', errors='ignore') as f:
                for line in f:
                    if line.startswith("Callsign="): return line.split("=")[1].strip().upper()
        return "Unknown"

    def get_dynamic_tgs(self):
        w_tg = config.get("WATCH_TG")
        r_tg = config.get("RESTORE_TG")
        if w_tg and r_tg: return w_tg, r_tg
        return w_tg or "6", r_tg or "44833"

    def execute_restore(self):
        log(f"🔄 TG {self.restore_tg} に自動復帰中...")
        slot_idx = int(config["RESTORE_SLOT"]) - 1
        url = f"{config['TGIF_API']}/{self.dmr_id}/{slot_idx}/{self.restore_tg}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=int(config["TGIF_API_TIMEOUT"])) as res:
                log(f"✅ TG変更リクエスト送信完了 (HTTP {res.status})")
        except Exception as e:
            log(f"❌ TGIF API 通信エラー: {e}")
        self.timer = None

    def schedule_restore(self, prev_tg):
        if self.timer: self.timer.cancel()
        delay = float(config["RESTORE_DELAY"])
        log(f"[END] TG {prev_tg} | {int(delay)}秒後に復帰します...")
        self.timer = threading.Timer(delay, self.execute_restore)
        self.timer.start()

    def process_command(self):
        if os.path.exists(CMD_FIFO):
            try:
                with open(CMD_FIFO, 'r') as f:
                    cmd = f.read().strip()
                os.remove(CMD_FIFO)
                if cmd == "stop":
                    if self.timer:
                        self.timer.cancel(); self.timer = None
                        log("🛑 復帰タイマーをキャンセルしました。")
                elif cmd == "reload":
                    load_config()
                    log("🔄 設定を再読み込みしました。")
            except Exception as e:
                log(f"⚠️ CMD Error: {e}")

    def process_line(self, line):
        if f"Slot {config['WATCH_SLOT']}," not in line: return

        if "voice header" in line:
            if self.timer: self.timer.cancel(); self.timer = None
            m_call = re.search(r'from (\S+)', line)
            if m_call and m_call.group(1).upper() == self.my_call: return
            m_tg = re.search(r'to TG (\d+)', line)
            if m_tg and m_tg.group(1) == self.watch_tg:
                self.gpio.set(1)
                log(f"[ RECEIVING ] TG{self.watch_tg} | From: {m_call.group(1) if m_call else 'Unknown'}")

        elif re.search(r'end of voice transmission|transmission lost|watchdog has expired', line):
            m_tg = re.search(r'to TG (\d+)', line)
            tg = m_tg.group(1) if m_tg else None

            if tg == self.watch_tg:
                self.gpio.set(0)
                log(f"[   IDLE   ] TG{tg}")
            elif not tg and self.gpio.state == 1:
                self.gpio.set(0)
                log("[   IDLE   ] Force Reset (Signal Lost)")

            if tg and tg not in (self.watch_tg, self.restore_tg):
                self.schedule_restore(tg)
            elif tg:
                log(f"ℹ️ [SKIP] TG {tg} は自動復帰の対象外です。")

    def run(self):
        def get_latest_log():
            logs = glob.glob(os.path.join(config["LOG_DIR"], "MMDVM-*.log"))
            return max(logs, key=os.path.getmtime) if logs else None

        current_file = get_latest_log()
        if not current_file:
            log("❌ ログファイルが見つかりません。")
            return

        log(f"📁 監視開始: {os.path.basename(current_file)}")
        f = open(current_file, 'r', errors='ignore')
        f.seek(0, 2)
        current_ino = os.stat(current_file).st_ino

        try:
            while True:
                self.process_command()
                
                if self.gpio.state == 1 and self.gpio.high_start_time > 0:
                    if time.time() - self.gpio.high_start_time > 120:
                        log("🚨 [FAIL-SAFE] Timeout 120s. Forcing LOW.")
                        self.gpio.set(0)

                line = f.readline()
                if line:
                    self.process_line(line)
                else:
                    f.seek(f.tell())
                    time.sleep(0.2)
                    
                    latest = get_latest_log()
                    if latest:
                        try:
                            new_ino = os.stat(latest).st_ino
                            if latest != current_file or new_ino != current_ino:
                                f.close()
                                current_file = latest
                                f = open(current_file, 'r', errors='ignore')
                                current_ino = new_ino
                                log(f"🔄 ログファイル切替検知: {os.path.basename(current_file)}")
                                f.seek(0, 2)
                        except FileNotFoundError:
                            pass
        except KeyboardInterrupt:
            self.gpio.set(0)
            if f: f.close()

if __name__ == "__main__":
    App().run()
