#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
# 
# File:        tgif_daemon.py
# Version:     v2.1.1 (Debug & FIFO Fix)
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# =============================================================================

import os, sys, time, re, threading, subprocess, glob, urllib.request, select

VERSION = "v2.1.1"
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
        log("DEBUG: Initializing App...")
        load_config()
        self.gpio = GPIOEngine(config["GPIO_PIN"], config["GPIO_CHIP"])
        self.timer = None
        self.dmr_id = self.get_dmr_id()
        self.my_call = self.get_my_callsign()
        self.watch_tg, self.restore_tg = self.get_dynamic_tgs()
        
        log(f"🚀 TGIFChanger-Py {VERSION} Active")
        log(f"   HOME=TG{self.restore_tg}/Slot{config['RESTORE_SLOT']}  DELAY={config['RESTORE_DELAY']}s")
        log(f"   WATCH=TG{self.watch_tg} (DMR ID: {self.dmr_id})")

    def get_dmr_id(self):
        # DMR ID取得 (WPSD/Pi-Star両対応)
        for path in [DMRGW_CONF, MMDVM_CONF]:
            if os.path.exists(path):
                with open(path, 'r', errors='ignore') as f:
                    for line in f:
                        if line.startswith("Id="): return line.split("=")[1].strip()
        return "Unknown"

    def get_my_callsign(self):
        if os.path.exists(MMDVM_CONF):
            with open(MMDVM_CONF, 'r', errors='ignore') as f:
                for line in f:
                    if line.startswith("Callsign="): return line.split("=")[1].strip().upper()
        return "Unknown"

    def get_dynamic_tgs(self):
        # 設定ファイル優先
        w_tg = config.get("WATCH_TG")
        r_tg = config.get("RESTORE_TG")
        if w_tg and r_tg: return w_tg, r_tg
        # MMDVMHostから抽出 (フォールバック)
        return w_tg or "6", r_tg or "44833"

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

    def run(self):
        log("DEBUG: Starting Main Loop...")
        def get_latest_log():
            logs = glob.glob(os.path.join(config["LOG_DIR"], "MMDVM-*.log"))
            return max(logs, key=os.path.getmtime) if logs else None

        current_file = get_latest_log()
        if not current_file:
            log("❌ ログファイルが見つかりません。")
            return

        log(f"📁 監視開始: {os.path.basename(current_file)}")
        # ログを最後から読み込み
        with subprocess.Popen(['tail', '-n', '0', '-F', current_file], stdout=subprocess.PIPE, text=True, bufsize=1) as proc:
            while True:
                # FIFOコマンドのチェック
                self.process_command()
                
                # GPIOフェールセーフ
                if self.gpio.state == 1 and self.gpio.high_start_time > 0:
                    if time.time() - self.gpio.high_start_time > 120:
                        log("🚨 [FAIL-SAFE] Timeout 120s. Forcing LOW.")
                        self.gpio.set(0)

                # ログの1行読み込み (ノンブロッキング)
                r, _, _ = select.select([proc.stdout], [], [], 0.5)
                if r:
                    line = proc.stdout.readline()
                    if line:
                        # ここに解析ロジックを実装 (スロット2の判定など)
                        if f"Slot {config['WATCH_SLOT']}," in line:
                            # (以前の解析ロジックを継続)
                            pass

if __name__ == "__main__":
    App().run()
