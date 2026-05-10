#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified Daemon
# Version: v2.2.0
# =============================================================================

import os, re, sys, glob, time, threading, subprocess, urllib.request

VERSION = "v2.2.0"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
MMDVM_CONF = "/etc/mmdvmhost"
DMRGW_CONF = "/etc/dmrgateway"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    def __init__(self):
        self.watch_slot = "2"
        self.watch_tg = "6"
        self.restore_delay = 120
        self.restore_tg = "44833"
        self.restore_slot = "2"
        self.gpio_pin = "17"
        self.gpio_chip = "0"
        self.log_dir = "/var/log/pi-star"
        self.tgif_api = "http://tgif.network:5040/api/sessions/update"
        self.my_call = ""
        self.dmr_id = ""
        self.load()
        self._extract_system_data()

    def load(self):
        if not os.path.isfile(CONF_FILE): return
        with open(CONF_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                v = v.strip(' "\'')
                if k == "WATCH_SLOT": self.watch_slot = v
                elif k == "WATCH_TG": self.watch_tg = v
                elif k == "RESTORE_DELAY": self.restore_delay = int(v)
                elif k == "RESTORE_TG": self.restore_tg = v
                elif k == "RESTORE_SLOT": self.restore_slot = v

    def _extract_system_data(self):
        # MMDVMHost & DMRGateway Config parsing
        if os.path.isfile(MMDVM_CONF):
            with open(MMDVM_CONF, 'r') as f:
                for line in f:
                    if line.startswith("Callsign="):
                        self.my_call = line.split('=')[1].strip().upper()
        if os.path.isfile(DMRGW_CONF):
            with open(DMRGW_CONF, 'r') as f:
                for line in f:
                    if line.startswith("Id="):
                        self.dmr_id = line.split('=')[1].split('#')[0].strip()

class GPIOEngine:
    def __init__(self, pin, chip):
        self.pin = pin
        self.chip = chip
        self.state = -1
        self._detect_engine()

    def _detect_engine(self):
        import shutil
        if shutil.which("pinctrl"): self.engine = "pinctrl"
        elif shutil.which("raspi-gpio"): self.engine = "raspi-gpio"
        elif os.path.isdir("/sys/class/gpio"): self.engine = "sysfs"
        else: self.engine = "none"
        
        if self.engine == "sysfs":
            try:
                with open("/sys/class/gpio/export", "w") as f: f.write(self.pin)
                time.sleep(0.1)
                with open(f"/sys/class/gpio/gpio{self.pin}/direction", "w") as f: f.write("out")
            except OSError: pass
        log(f"🚀 GPIO Engine Init: {self.engine} (Pin: {self.pin})")

    def set_value(self, val):
        if self.state == val or self.engine == "none": return
        try:
            if self.engine in ["pinctrl", "raspi-gpio"]:
                mode = "dh" if val == 1 else "dl"
                subprocess.run([self.engine, "set", self.pin, mode])
            elif self.engine == "sysfs":
                with open(f"/sys/class/gpio/gpio{self.pin}/value", "w") as f: f.write(str(val))
        except Exception as e: log(f"⚠️ GPIO Error: {e}")
        self.state = val
        log(f"{'⚡' if val==1 else '🌑'} GPIO{self.pin} -> {'HIGH' if val==1 else 'LOW'}")

class TGIFChanger:
    def __init__(self):
        self.cfg = Config()
        self.gpio = GPIOEngine(self.cfg.gpio_pin, self.cfg.gpio_chip)
        self.restore_timer = None
        
        # コマンドFIFOリスナースレッド起動
        threading.Thread(target=self.fifo_listener, daemon=True).start()

    def fifo_listener(self):
        if os.path.exists(CMD_FIFO): os.remove(CMD_FIFO)
        os.mkfifo(CMD_FIFO)
        os.chmod(CMD_FIFO, 0o666)
        while True:
            with open(CMD_FIFO, 'r') as f:
                cmd = f.read().strip()
                if cmd == 'stop':
                    self.cancel_restore()
                    log("🚫 CLIからの指示でタイマーを停止しました。")
                elif cmd == 'reload':
                    self.cfg.load()
                    log(f"🔄 設定を再読み込みしました: 待機時間={self.cfg.restore_delay}秒")

    def change_tg(self, tg, slot):
        slot_idx = int(slot) - 1
        url = f"{self.cfg.tgif_api}/{self.cfg.dmr_id}/{slot_idx}/{tg}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
                log(f"✅ TG{tg} へ復帰完了 (HTTP {r.getcode()})")
        except Exception as e: log(f"❌ TGIF API通信エラー: {e}")

    def schedule_restore(self, prev_tg):
        self.cancel_restore()
        log(f"🕒 [END] TG {prev_tg} | {self.cfg.restore_delay}秒後に復帰します...")
        self.restore_timer = threading.Timer(self.cfg.restore_delay, self.change_tg, args=(self.cfg.restore_tg, self.cfg.restore_slot))
        self.restore_timer.start()

    def cancel_restore(self):
        if self.restore_timer and self.restore_timer.is_alive():
            self.restore_timer.cancel()

    def get_latest_log(self):
        files = glob.glob(os.path.join(self.cfg.log_dir, "MMDVM-*.log"))
        return max(files, key=os.path.getmtime) if files else None

    def run(self):
        log(f"🚀 TGIFChanger-Py {VERSION} 起動 (監視:TG{self.cfg.watch_tg} / 復帰:TG{self.cfg.restore_tg})")
        current_file = self.get_latest_log()
        while not current_file:
            time.sleep(5)
            current_file = self.get_latest_log()

        with open(current_file, 'r', errors='replace') as f:
            f.seek(0, 2)  # ファイル末尾へ移動
            while True:
                line = f.readline()
                if not line:
                    # EOFバッファの罠を回避
                    f.seek(f.tell())
                    time.sleep(0.1)
                    
                    # ログローテーション検知
                    new_file = self.get_latest_log()
                    if new_file and new_file != current_file:
                        log("🔄 ログファイル切替検知: 新しいログを監視します")
                        current_file = new_file
                        f.close()
                        f = open(current_file, 'r', errors='replace')
                        f.seek(0, 2)
                    continue

                line = line.strip()
                if f"Slot {self.cfg.watch_slot}," not in line: continue

                if "voice header" in line:
                    self.cancel_restore()
                    from_match = re.search(r'from (\S+)', line)
                    if from_match and from_match.group(1).upper() == self.cfg.my_call: continue
                    tg_match = re.search(r'to TG ([0-9]+)', line)
                    if tg_match and tg_match.group(1) == self.cfg.watch_tg:
                        self.gpio.set_value(1)
                        log(f"[ RECEIVING ] TG{tg_match.group(1)} | From: {from_match.group(1) if from_match else 'UNKNOWN'}")

                elif "end of voice transmission" in line:
                    tg_match = re.search(r'to TG ([0-9]+)', line)
                    if tg_match:
                        tg = tg_match.group(1)
                        if tg == self.cfg.watch_tg: self.gpio.set_value(0)
                        if tg not in [self.cfg.restore_tg, self.cfg.watch_tg]:
                            self.schedule_restore(tg)

if __name__ == "__main__":
    app = TGIFChanger()
    try: app.run()
    except KeyboardInterrupt: pass
