#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
# File:        tgif_daemon.py
# Version:     v2.0.0
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Ultra-lightweight Python daemon replacing shell scripts.
# =============================================================================

import os, sys, time, re, threading, subprocess, glob, urllib.request, select

VERSION = "v2.0.0"
CONF_FILE = "/etc/tgifchanger.conf"
MMDVM_CONF = "/etc/mmdvmhost"
DMRGW_CONF = "/etc/dmrgateway"

# デフォルト設定
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
        with open(CONF_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")

def get_dynamic_tgs():
    w_tg, r_tg = config.get("WATCH_TG"), config.get("RESTORE_TG")
    if w_tg and r_tg: return w_tg, r_tg

    if os.path.exists(MMDVM_CONF):
        in_dmr, is_tgif = False, False
        with open(MMDVM_CONF, "r", errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith("[DMR Network"): in_dmr, is_tgif = True, False
                elif line.startswith("["): in_dmr = False
                if in_dmr and "Address=tgif.network" in line: is_tgif = True
                if in_dmr and is_tgif and line.startswith("TGRewrite="):
                    parts = line.split("=")[1].split(",")
                    if not w_tg and len(parts) >= 2: w_tg = re.sub(r'\D', '', parts[1])
                    if not r_tg and len(parts) >= 4: r_tg = re.sub(r'\D', '', parts[3])
                    break
    return w_tg or "6", r_tg or "44833"

def get_dmr_id():
    dmr_id = ""
    for conf in [DMRGW_CONF, MMDVM_CONF]:
        if os.path.exists(conf):
            in_dmr, is_tgif = False, False
            with open(conf, "r", errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("[DMR Network"): in_dmr, is_tgif = True, False
                    elif line.startswith("["): in_dmr = False
                    if in_dmr and "Address=tgif.network" in line: is_tgif = True
                    if in_dmr and is_tgif and line.startswith("Id="):
                        return line.split("=")[1].split("#")[0].strip()
                    elif conf == MMDVM_CONF and line.startswith("Id="):
                        dmr_id = line.split("=")[1].split("#")[0].strip()
    return dmr_id

def get_my_callsign():
    if os.path.exists(MMDVM_CONF):
        with open(MMDVM_CONF, "r", errors='ignore') as f:
            for line in f:
                if line.startswith("Callsign="):
                    return line.split("=")[1].strip().upper()
    return ""

class GPIOEngine:
    def __init__(self, pin, chip):
        self.pin, self.chip = str(pin), str(chip)
        self.state, self.pid = -1, None
        self.engine = self.detect()

    def detect(self):
        if subprocess.run("command -v pinctrl", shell=True, stdout=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["pinctrl", "set", self.pin, "op", "pn", "dl"])
            return "pinctrl"
        if subprocess.run("command -v raspi-gpio", shell=True, stdout=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["raspi-gpio", "set", self.pin, "op", "pn", "dl"])
            return "raspi-gpio"
        if subprocess.run("gpioset --version 2>&1 | grep -q 'libgpiod) 2'", shell=True).returncode == 0:
            return "gpiod_v2"
        if os.path.exists("/sys/class/gpio"):
            if not os.path.exists(f"/sys/class/gpio/gpio{self.pin}"):
                try:
                    with open("/sys/class/gpio/export", "w") as f: f.write(self.pin)
                    time.sleep(0.1)
                    with open(f"/sys/class/gpio/gpio{self.pin}/direction", "w") as f: f.write("out")
                except: pass
            return "sysfs"
        return "unknown"

    def set(self, val):
        if self.state == val: return
        try:
            if self.engine == "pinctrl": subprocess.run(["pinctrl", "set", self.pin, "dh" if val else "dl"])
            elif self.engine == "raspi-gpio": subprocess.run(["raspi-gpio", "set", self.pin, "dh" if val else "dl"])
            elif self.engine == "gpiod_v2":
                if self.pid: subprocess.run(["kill", str(self.pid)], stderr=subprocess.DEVNULL); self.pid = None
                if val: self.pid = subprocess.Popen(["gpioset", self.chip, f"{self.pin}=1", "--mode=wait"]).pid
                else: subprocess.run(["gpioset", self.chip, f"{self.pin}=0"])
            elif self.engine == "sysfs":
                with open(f"/sys/class/gpio/gpio{self.pin}/value", "w") as f: f.write(str(val))
        except Exception as e: log(f"⚠️ GPIO Error: {e}")
        self.state = val
        log(f"⚡ GPIO{self.pin} -> HIGH" if val else f"🌑 GPIO{self.pin} -> LOW")

    def cleanup(self):
        self.set(0)
        if self.engine == "sysfs":
            try:
                with open("/sys/class/gpio/unexport", "w") as f: f.write(self.pin)
            except: pass

class App:
    def __init__(self):
        load_config()
        self.watch_tg, self.restore_tg = get_dynamic_tgs()
        self.dmr_id = get_dmr_id()
        self.my_call = get_my_callsign()
        self.gpio = GPIOEngine(config["GPIO_PIN"], config["GPIO_CHIP"])
        self.timer = None
        log(f"🚀 TGIFChanger-Py {VERSION} Active (Engine: {self.gpio.engine})")
        log(f"   HOME=TG{self.restore_tg}/Slot{config['RESTORE_SLOT']}  DELAY={config['RESTORE_DELAY']}s")
        log(f"   WATCH=TG{self.watch_tg}  IGNORE: TG{self.watch_tg}, TG{self.restore_tg}")

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
        def get_latest():
            logs = glob.glob(os.path.join(config["LOG_DIR"], "MMDVM-*.log"))
            return max(logs, key=os.path.getmtime) if logs else None

        current_file = None
        process = None
        try:
            while True:
                latest = get_latest()
                if latest != current_file or process is None or process.poll() is not None:
                    if process: process.terminate()
                    current_file = latest
                    if current_file:
                        log(f"📁 ログファイル監視開始: {os.path.basename(current_file)}")
                        process = subprocess.Popen(['tail', '-n', '0', '-F', current_file], stdout=subprocess.PIPE, text=True, bufsize=1)
                    else:
                        time.sleep(5); continue

                ready, _, _ = select.select([process.stdout], [], [], 2.0)
                if ready:
                    line = process.stdout.readline()
                    if line: self.process_line(line)
        except KeyboardInterrupt:
            if process: process.terminate()
            self.gpio.cleanup()

if __name__ == "__main__":
    App().run()
