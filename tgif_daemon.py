#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Professional Unified Daemon (v2.6.4)
# 
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
# Description: This daemon monitors MMDVMHost logs in real-time to detect 
#              DMR traffic. It controls GPIO LEDs for status indication and 
#              manages an auto-restore timer to return the hotspot to a 
#              home Talkgroup. Supports real-time config reloads via FIFO.
# =============================================================================

import os
import time
import threading
import re
import subprocess
import sys

# --- システム定数 ---
VERSION = "v2.6.4"
CONF_FILE = "/etc/tgifchanger.conf"
CMD_FIFO = "/run/tgifchanger.cmd"
LOG_DIR = "/var/log/pi-star"

def log(msg):
    """標準出力(journalctl)へ即座に内容を書き出すためのラッパー"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

class Config:
    """設定ファイルの読み込みと動的更新を管理するクラス"""
    def __init__(self):
        self.watch_tg = "6"
        self.restore_tg = "44833"
        self.delay = 120
        self.gpio_pin = "17"
        self.load()

    def load(self):
        """/etc/tgifchanger.conf から最新の設定をパースする"""
        if os.path.exists(CONF_FILE):
            try:
                with open(CONF_FILE, 'r') as f:
                    content = f.read()
                    # 正規表現で各設定値を抽出（コメントアウトされている行は無視）
                    w = re.search(r'^\s*WATCH_TG\s*=\s*["\']?(\d+)["\']?', content, re.M)
                    r = re.search(r'^\s*RESTORE_TG\s*=\s*["\']?(\d+)["\']?', content, re.M)
                    d = re.search(r'^\s*RESTORE_DELAY\s*=\s*["\']?(\d+)["\']?', content, re.M)
                    g = re.search(r'^\s*GPIO_PIN\s*=\s*["\']?(\d+)["\']?', content, re.M)
                    
                    if w: self.watch_tg = w.group(1)
                    if r: self.restore_tg = r.group(1)
                    if d: self.delay = int(d.group(1))
                    if g: self.gpio_pin = g.group(1)
            except Exception as e:
                log(f"⚠️ 設定読み込みエラー: {e}")
        
        log(f"⚙️  設定を反映: WATCH={self.watch_tg}, HOME={self.restore_tg}, DELAY={self.delay}s")

# グローバル設定インスタンスとタイマー
cfg = Config()
restore_timer = None

def set_gpio(state):
    """GPIOの出力を制御してLEDを点灯/消灯させる"""
    try:
        # dh (Digital High), dl (Digital Low)
        mode = "dh" if state else "dl"
        subprocess.run(["pinctrl", "set", cfg.gpio_pin, "op", mode], check=False, capture_output=True)
    except Exception:
        pass

def do_restore():
    """復帰用Talkgroupへの切替APIを実行する"""
    log(f"🏠 自動復帰時間経過: TG {cfg.restore_tg} へ戻ります。")
    try:
        # tg_change ツールを介してAPIリクエストを送信
        subprocess.run(["/usr/local/bin/tg_change", f"-{cfg.restore_tg}"], check=False)
    except Exception as e:
        log(f"❌ 復帰コマンド実行失敗: {e}")

def command_listener():
    """Web UIやCLIツールからの命令を非同期に待ち受けるパイプ(FIFO)リスナー"""
    if os.path.exists(CMD_FIFO):
        os.remove(CMD_FIFO)
    
    try:
        os.mkfifo(CMD_FIFO)
        os.chmod(CMD_FIFO, 0o666)
    except Exception as e:
        log(f"❌ FIFO作成に失敗しました。Web連動ができません: {e}")
        return

    while True:
        try:
            # パイプが開かれるのを待機
            with open(CMD_FIFO, 'r') as fifo:
                for line in fifo:
                    cmd = line.strip()
                    if "reload" in cmd:
                        cfg.load()
                    elif "stop" in cmd:
                        global restore_timer
                        if restore_timer and restore_timer.is_alive():
                            restore_timer.cancel()
                            log("🛑 ユーザー操作により復帰タイマーを停止しました。")
        except Exception:
            time.sleep(1)

def get_latest_log():
    """最新のMMDVMHostログファイル名を取得する"""
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("MMDVM-")]
        if not files: return None
        return os.path.join(LOG_DIR, max(files))
    except Exception:
        return None

def main_loop():
    """ログファイルを監視し、DMRの挙動に応じて処理を行うメインループ"""
    log(f"🚀 TGIFChanger-Py {VERSION} 監視開始")
    
    # 別スレッドでコマンドリスナーを起動
    threading.Thread(target=command_listener, daemon=True).start()
    
    current_log = get_latest_log()
    if not current_log:
        log("❌ 監視対象のログファイルが見つかりません。")
        return

    log(f"📁 監視中のログ: {os.path.basename(current_log)}")

    with open(current_log, "r") as f:
        # 起動時の古いログは読み飛ばし、現在の末尾から監視
        f.seek(0, 2)
        
        active_tg = None
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            # --- 受信開始検知 (Voice Header) ---
            if "received network voice header" in line:
                m = re.search(r'to TG (\d+)', line)
                if m:
                    active_tg = m.group(1)
                    log(f"⚡ 受信開始: TG {active_tg}")
                    set_gpio(True)
                    
                    # 受信が始まったら既存の復帰タイマーは破棄
                    global restore_timer
                    if restore_timer and restore_timer.is_alive():
                        restore_timer.cancel()
            
            # --- 受信終了検知 (End of Voice) ---
            if "received network end of voice" in line:
                log("🌑 受信終了 / 待機状態")
                set_gpio(False)
                
                # 受信していたTGが、監視対象(WATCH_TG)以外の「ゲストTG」だった場合のみ復帰タイマーを始動
                if active_tg and active_tg != cfg.watch_tg:
                    log(f"⏳ 復帰タイマー開始: {cfg.delay}秒後に TG {cfg.restore_tg} へ自動復帰します。")
                    if restore_timer and restore_timer.is_alive():
                        restore_timer.cancel()
                    restore_timer = threading.Timer(cfg.delay, do_restore)
                    restore_timer.start()

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log("👋 プログラムを終了します。")
        sys.exit(0)
    except Exception as e:
        log(f"🔥 システムエラーが発生しました: {e}")
        sys.exit(1)
