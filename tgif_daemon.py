#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified Daemon (v2.6.4)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: Real-time MMDVMHost log monitor with GPIO control and 
#              unbuffered FIFO command synchronization for Web UI.
# =============================================================================

import os
import time
import threading
import re
import subprocess
import sys

# --- 定数定義 ---
VERSION = "v2.6.4"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
LOG_DIR = "/var/log/pi-star"

def log(msg):
    """標準出力にバッファなしで即座にログを書き出す"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    """設定ファイルの読み込みと保持を担当するクラス"""
    def __init__(self):
        self.watch_tg = "6"
        self.restore_tg = "44833"
        self.delay = 120
        self.gpio_pin = "17"
        self.load()

    def load(self):
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
        
        log(f"⚙️  設定を反映しました: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

# グローバルインスタンス
cfg = Config()
restore_timer = None

def set_gpio(state):
    """GPIOの出力を制御 (pinctrlコマンドを使用)"""
    try:
        mode = "dh" if state else "dl"
        # check=Falseでコマンド自体の失敗でデーモンを落とさないようにする
        subprocess.run(["pinctrl", "set", cfg.gpio_pin, "op", mode], check=False, capture_output=True)
    except Exception as e:
        pass

def do_restore():
    """指定されたTGへ戻るコマンドを実行"""
    log(f"🏠 自動復帰実行: TG {cfg.restore_tg} へ接続します。")
    try:
        subprocess.run(["/usr/local/bin/tg_change", f"-{cfg.restore_tg}"], check=False)
    except Exception as e:
        log(f"❌ 復帰コマンド失敗: {e}")

def command_listener():
    """Web UIやCLIからの非同期命令(FIFO)を待ち受けるスレッド"""
    if os.path.exists(CMD_FIFO):
        os.remove(CMD_FIFO)
    
    try:
        os.mkfifo(CMD_FIFO)
        os.chmod(CMD_FIFO, 0o666)
    except Exception as e:
        log(f"❌ FIFO作成失敗: {e}")
        return

    while True:
        try:
            with open(CMD_FIFO, 'r') as fifo:
                for line in fifo:
                    cmd = line.strip()
                    if "reload" in cmd:
                        cfg.load()
                    elif "stop" in cmd:
                        global restore_timer
                        if restore_timer and restore_timer.is_alive():
                            restore_timer.cancel()
                            log("🛑 タイマーを強制停止しました。")
        except Exception as e:
            time.sleep(1)

def get_latest_log():
    """MMDVMHostの最新ログファイルパスを取得"""
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        if not files: return None
        return os.path.join(LOG_DIR, max(files))
    except:
        return None

def main_loop():
    """メインのログ監視ループ"""
    log(f"🚀 TGIFChanger-Py {VERSION} 起動完了")
    
    # 命令受信用スレッドをデーモンとして開始
    threading.Thread(target=command_listener, daemon=True).start()
    
    current_log = get_latest_log()
    if not current_log:
        log("❌ 監視対象のログファイルが見つかりません。")
        return

    log(f"📁 監視ログ: {os.path.basename(current_log)}")

    with open(current_log, "r") as f:
        # 起動時点までの過去ログは無視して末尾から開始
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            # 受信開始(Header)の検知
            if "received network voice header" in line:
                m = re.search(r'to TG (\d+)', line)
                if m:
                    active_tg = m.group(1)
                    log(f"⚡ 受信開始: TG {active_tg}")
                    set_gpio(True)
                    
                    # 受信中は復帰タイマーを止める
                    global restore_timer
                    if restore_timer and restore_timer.is_alive():
                        restore_timer.cancel()
            
            # 受信終了(End of Voice)の検知
            if "received network end of voice" in line:
                log("🌑 受信終了 / 待機状態")
                set_gpio(False)
                
                # 監視TG以外（ゲストTG）での交信が終わった場合のみタイマー開始
                if 'active_tg' in locals() and active_tg != cfg.watch_tg:
                    log(f"⏳ 復帰タイマー開始: {cfg.delay}秒後に TG {cfg.restore_tg} へ戻ります")
                    if restore_timer and restore_timer.is_alive():
                        restore_timer.cancel()
                    restore_timer = threading.Timer(cfg.delay, do_restore)
                    restore_timer.start()

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log("👋 ユーザー操作により終了します。")
        sys.exit(0)
    except Exception as e:
        log(f"🔥 重大なエラーが発生しました: {e}")
        sys.exit(1)
