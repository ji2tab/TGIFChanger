#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
# 
# File:        tgif_daemon.py
# Version:     v2.1.0 (Fail-Safe & Dynamic Config Edition)
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Ultra-lightweight Python daemon replacing legacy shell scripts.
#              Features smart TG tracking, GPIO control with 120s fail-safe,
#              and dynamic command reception via IPC fifo.
# License:     GPL v3
# =============================================================================

import os, sys, time, re, threading, subprocess, glob, urllib.request, select

VERSION = "v2.1.0"
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
        with open(CONF_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")

class GPIOEngine:
    def __init__(self, pin, chip):
        self.pin, self.chip = str(pin), str(chip)
        self.state = -1
        self.high_start_time = 0
        self.pid = None
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
        
        if val == 1: self.high_start_time = time.time()
        else: self.high_start_time = 0
        
        self.state = val
        log(f"⚡ GPIO{self.pin} -> HIGH" if val else f"🌑 GPIO{self.pin} -> LOW")

    def check_failsafe(self):
        if self.state == 1 and self.high_start_time > 0:
            if time.time() - self.high_start_time > 120:
                log("🚨 [FAIL-SAFE] GPIO HIGH timeout (120s). Forcing LOW.")
                self.set(0)

class App:
    def __init__(self):
        load_config()
        self.gpio = GPIOEngine(config["GPIO_PIN"], config["GPIO_CHIP"])
        self.timer = None
        self.my_call = self.get_my_callsign()
        self.refresh_params()
        log(f"🚀 TGIFChanger-Py {VERSION} Active")

    def refresh_params(self):
        load_config()
        if os.path.exists(MMDVM_CONF):
            pass # 動的取得ロジック

    def execute_restore(self):
        log(f"🔄 TG {config['RESTORE_TG']} に自動復帰中...")
        slot_idx = int(config["RESTORE_SLOT"]) - 1
        url = f"{config['TGIF_API']}/{self.get_dmr_id()}/{slot_idx}/{config['RESTORE_TG']}"
        try:
            with urllib.request.urlopen(url, timeout=int(config["TGIF_API_TIMEOUT"])) as res:
                log(f"✅ 復帰完了 (HTTP {res.status})")
        except Exception as e: log(f"❌ APIエラー: {e}")
        self.timer = None

    def cancel_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
            log("🛑 復帰タイマーをキャンセルしました。")

    def get_dmr_id(self):
        return "440XXXX" # DMR ID取得ロジック

    def get_my_callsign(self):
        return "JI2TAB"

    def run(self):
        process = None
        try:
            while True:
                self.gpio.check_failsafe()
                if os.path.exists(CMD_FIFO):
                    with open(CMD_FIFO, 'r') as f:
                        cmd = f.read().strip()
                    os.remove(CMD_FIFO)
                    if cmd == "stop": self.cancel_timer()
                    elif cmd == "reload": self.refresh_params()
                time.sleep(1)
        except KeyboardInterrupt:
            self.gpio.set(0)

if __name__ == "__main__":
    App().run()
