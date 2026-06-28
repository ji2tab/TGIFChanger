#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
#
# File:        tgif_daemon.py
# Version:     v2.3.4
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Changes from v2.3.3:
#   - [NEW] コールサイン・ウォッチドッグ (真の利用者監視) を追加。
#           他TGへ "RF(自局側)キーアップ" した最後の局を「真の利用者」として記録し、
#           その局のRFが CALLSIGN_TIMEOUT 秒(既定300)確認できなければ、
#           ネット側の通話が続いていても RESTORE_TG へ強制復帰する。
#           network 受信(リモート通話)はカウント対象外。
#           別の局がRFキーアップすると追跡対象を切り替える。
# =============================================================================

import os, sys, re, time, glob, fcntl, errno, signal, socket, threading
import urllib.request, urllib.error, subprocess, shutil
from pathlib import Path

VERSION        = "v2.3.4"
CONF_FILE      = "/etc/tgifchanger.conf"
MMDVM_CONF     = "/etc/mmdvmhost"
DMRGW_CONF     = "/etc/dmrgateway"
LOCK_FILE      = "/run/tgifchanger-py.lock"
CMD_SOCKET     = "/run/tgifchanger-py.sock"  # daemon制御用 UDS
LOG_PATTERN    = "MMDVM-*.log"
GPIO_FAILSAFE_SEC = 120   # HIGH状態の上限秒数(フェイルセーフ)

# デフォルト設定 (仕様書§3)
config = {
    "LOG_DIR":          "/var/log/pi-star",
    "WATCH_SLOT":       "2",
    "RESTORE_SLOT":     "2",
    "WATCH_TG":         "",  
    "RESTORE_TG":       "",  
    "GPIO_PIN":         "17",
    "GPIO_CHIP":        "auto",
    "GPIO_BACKEND":     "auto",
    "RESTORE_DELAY":    "120",
    "CALLSIGN_TIMEOUT": "300",  # 真の利用者(RFアクセス局)を確認できなくなってから復帰するまでの秒数。0で無効。
    "TGIF_API":         "http://tgif.network:5040/api/sessions/update",
    "TGIF_API_TIMEOUT": "10",
}

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------
def load_config() -> None:
    if not os.path.exists(CONF_FILE):
        return
    try:
        with open(CONF_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as e:
        log(f"⚠️ 設定読み込みエラー: {e}")

# ---------------------------------------------------------------------------
# DMR ID / コールサイン / 動的TG 抽出
# ---------------------------------------------------------------------------
def _iter_sections(path: str):
    if not os.path.isfile(path):
        return
    current, buf = "", []
    try:
        for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\[(.+?)\]\s*$", raw)
            if m:
                yield current, buf
                current, buf = m.group(1).strip(), []
            else:
                buf.append(raw)
        yield current, buf
    except OSError:
        return

def _kv(line: str):
    s = line.strip()
    if not s or s.startswith(("#", ";")):
        return None
    if "=" not in s:
        return None
    k, _, v = s.partition("=")
    return k.strip(), v.split("#", 1)[0].strip()

def get_dmr_id() -> str:
    for section, lines in _iter_sections(DMRGW_CONF):
        if not section.startswith("DMR Network"):
            continue
        is_tgif = False
        found_id = ""
        for line in lines:
            kv = _kv(line)
            if not kv:
                continue
            k, v = kv
            if k == "Address" and "tgif.network" in v:
                is_tgif = True
            elif k == "Id" and v:
                found_id = v
        if is_tgif and found_id:
            return found_id
    for _sec, lines in _iter_sections(MMDVM_CONF):
        for line in lines:
            kv = _kv(line)
            if kv and kv[0] == "Id" and kv[1]:
                return kv[1]
    return ""

def get_my_callsign() -> str:
    for _sec, lines in _iter_sections(MMDVM_CONF):
        for line in lines:
            kv = _kv(line)
            if kv and kv[0] == "Callsign" and kv[1]:
                return kv[1].upper()
    return ""

def get_dynamic_tgs():
    w = config.get("WATCH_TG", "").strip()
    r = config.get("RESTORE_TG", "").strip()
    if w and r:
        return w, r
    for conf_path in [DMRGW_CONF, MMDVM_CONF]:
        for section, lines in _iter_sections(conf_path):
            if not section.startswith("DMR Network"):
                continue
            is_tgif = False
            rewrite = None
            for line in lines:
                kv = _kv(line)
                if not kv:
                    continue
                k, v = kv
                if k == "Address" and "tgif.network" in v:
                    is_tgif = True
                elif k.startswith("TGRewrite") and rewrite is None:
                    rewrite = v
            if is_tgif and rewrite:
                parts = rewrite.split(",")
                parsed_w = re.sub(r"\D", "", parts[1]) if len(parts) > 1 else ""
                parsed_r = re.sub(r"\D", "", parts[3]) if len(parts) > 3 else ""
                return (w or parsed_w or "1"), (r or parsed_r or "4000")
    return (w or "1"), (r or "4000")

# ---------------------------------------------------------------------------
# GPIO エンジン
# ---------------------------------------------------------------------------
def _detect_gpiochip(requested: str) -> str:
    if requested.startswith("gpiochip"): return requested
    if requested.isdigit(): return f"gpiochip{requested}"
    if requested != "auto": return requested
    if not shutil.which("gpiodetect"): return "gpiochip0"
    try:
        cp = subprocess.run(["gpiodetect"], capture_output=True, text=True, check=False, timeout=2.0)
        for line in cp.stdout.splitlines():
            m = re.match(r"^(gpiochip\d+)\s+\[(.+?)\]", line)
            if m and ("pinctrl-bcm" in m.group(2) or "pinctrl-rp1" in m.group(2)):
                return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return "gpiochip0"

def _gpioset_version() -> int:
    if not shutil.which("gpioset"): return 0
    try:
        cp = subprocess.run(["gpioset", "--version"], capture_output=True, text=True, check=False, timeout=2.0)
        blob = (cp.stdout or "") + (cp.stderr or "")
        if re.search(r"libgpiod\)?\s*2|libgpiod 2", blob): return 2
        return 1
    except (OSError, subprocess.SubprocessError):
        return 0

class GPIOEngine:
    def __init__(self, pin: str, chip_cfg: str, backend_cfg: str):
        self.pin = str(pin)
        self.chip = _detect_gpiochip(chip_cfg)
        self.state = -1
        self.high_start = 0.0
        self._gpioset_ver = _gpioset_version()
        self._bg_proc = None
        self.backend_cfg = backend_cfg.lower()
        self.engine = self._select()
        log(f"🎛  GPIO{self.pin} engine={self.engine}" + (f" chip={self.chip}" if "libgpiod" in self.engine else ""))

    def _select(self) -> str:
        b = self.backend_cfg
        if b == "libgpiod":
            if self._gpioset_ver > 0: return f"libgpiod_v{self._gpioset_ver}"
            log("⚠️  libgpiod指定だが gpioset が見つかりません。fallback")
            return self._fallback_simple()
        if b in ("pinctrl", "raspi-gpio", "sysfs", "null"): return self._init_simple(b)
        return self._fallback_simple()

    def _init_simple(self, engine: str) -> str:
        try:
            if engine == "pinctrl" and subprocess.run("command -v pinctrl", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0:
                subprocess.run(["pinctrl", "set", self.pin, "op", "pn", "dl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                return "pinctrl"
            if engine == "raspi-gpio" and subprocess.run("command -v raspi-gpio", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0:
                subprocess.run(["raspi-gpio", "set", self.pin, "op", "pn", "dl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                return "raspi-gpio"
            if engine == "sysfs" and os.path.isdir("/sys/class/gpio"):
                gdir = f"/sys/class/gpio/gpio{self.pin}"
                if not os.path.isdir(gdir):
                    with open("/sys/class/gpio/export", "w") as f: f.write(self.pin)
                    time.sleep(0.1)
                with open(f"{gdir}/direction", "w") as f: f.write("out")
                with open(f"{gdir}/value", "w") as f: f.write("0")
                return "sysfs"
            if engine == "null": return "null"
        except OSError: pass
        return "null"

    def _fallback_simple(self) -> str:
        for eng in ("pinctrl", "raspi-gpio", "sysfs"):
            result = self._init_simple(eng)
            if result != "null": return result
        return "null"

    def _kill_bg(self) -> None:
        if self._bg_proc is not None:
            try:
                self._bg_proc.terminate()
                self._bg_proc.wait(timeout=1.0)
            except (OSError, subprocess.SubprocessError):
                try: self._bg_proc.kill()
                except OSError: pass
            self._bg_proc = None

    def set(self, val: int) -> None:
        if self.state == val: return
        try:
            if "libgpiod" in self.engine:
                self._kill_bg()
                if val:
                    cmd = ["gpioset", "-c", self.chip, "--mode=wait", f"{self.pin}=1"] if self._gpioset_ver == 2 else ["gpioset", "--mode=wait", self.chip, f"{self.pin}=1"]
                    self._bg_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    cmd = ["gpioset", "-c", self.chip, f"{self.pin}=0"] if self._gpioset_ver == 2 else ["gpioset", self.chip, f"{self.pin}=0"]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            elif self.engine == "pinctrl":
                subprocess.run(["pinctrl", "set", self.pin, "dh" if val else "dl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            elif self.engine == "raspi-gpio":
                subprocess.run(["raspi-gpio", "set", self.pin, "dh" if val else "dl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            elif self.engine == "sysfs":
                with open(f"/sys/class/gpio/gpio{self.pin}/value", "w") as f: f.write(str(val))
        except OSError as e:
            log(f"⚠️ GPIO Error: {e}")
        self.high_start = time.time() if val else 0.0
        self.state = val
        log(f"⚡ GPIO{self.pin} -> HIGH" if val else f"🌑 GPIO{self.pin} -> LOW")

    def cleanup(self) -> None:
        self.set(0)
        self._kill_bg()
        if self.engine == "sysfs":
            try:
                with open("/sys/class/gpio/unexport", "w") as f: f.write(self.pin)
            except OSError: pass

# ---------------------------------------------------------------------------
# コマンドソケットサーバ
# ---------------------------------------------------------------------------
class CmdServer:
    def __init__(self, app: "App") -> None:
        self.app  = app
        self._sock: "socket.socket | None" = None
        self._thr: "threading.Thread | None" = None
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            if os.path.exists(CMD_SOCKET): os.unlink(CMD_SOCKET)
            os.makedirs(os.path.dirname(CMD_SOCKET) or "/", exist_ok=True)
        except OSError: pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.bind(CMD_SOCKET)
        except OSError as e:
            log(f"⚠️ CMD socket bind失敗: {e}")
            s.close()
            return
        os.chmod(CMD_SOCKET, 0o666)
        s.listen(8)
        s.settimeout(0.5)
        self._sock = s
        self._thr  = threading.Thread(target=self._serve, daemon=True, name="cmd-server")
        self._thr.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as w:
                w.settimeout(0.2)
                w.connect(CMD_SOCKET)
        except OSError: pass
        if self._thr: self._thr.join(timeout=2.0)
        if self._sock:
            try: self._sock.close()
            except OSError: pass
        try: os.unlink(CMD_SOCKET)
        except OSError: pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout: continue
            except OSError: break
            with conn:
                try:
                    conn.settimeout(2.0)
                    data = b""
                    while b"\n" not in data and len(data) < 512:
                        chunk = conn.recv(512)
                        if not chunk: break
                        data += chunk
                    cmd  = data.decode("utf-8", "replace").strip().lower()
                    resp = self._handle(cmd)
                    conn.sendall((resp + "\n").encode("utf-8"))
                except OSError: continue

    def _handle(self, cmd: str) -> str:
        app = self.app
        if cmd == "stop":
            app.cancel_timer()
            return "OK stop"
        if cmd == "reload":
            load_config()
            app.watch_tg, app.restore_tg = get_dynamic_tgs()
            log("🔄 設定リロード完了")
            log(f"   HOME=TG{app.restore_tg}  WATCH=TG{app.watch_tg}  DELAY={config['RESTORE_DELAY']}s  CS_TIMEOUT={config.get('CALLSIGN_TIMEOUT','300')}s")
            return "OK reload"
        if cmd == "status":
            import json
            d = {
                "version":    VERSION,
                "watch_tg":   app.watch_tg,
                "restore_tg": app.restore_tg,
                "delay":      config.get("RESTORE_DELAY", "120"),
                "callsign_timeout": config.get("CALLSIGN_TIMEOUT", "300"),
                "tracked_call":  app.tracked_call or None,
                "away_tg":       app.away_tg,
                "gpio_state": app.gpio.state,
                "gpio_engine":app.gpio.engine,
                "gpio_chip":  app.gpio.chip,
                "timer_pending": app.timer is not None,
            }
            return json.dumps(d, ensure_ascii=False)
        return f"ERR unknown command: {cmd!r}"

# ---------------------------------------------------------------------------
# メインアプリケーション
# ---------------------------------------------------------------------------
class App:
    def __init__(self) -> None:
        load_config()
        self.gpio       = GPIOEngine(config["GPIO_PIN"], config.get("GPIO_CHIP", "auto"), config.get("GPIO_BACKEND", "auto"))
        self.timer: "threading.Timer | None" = None
        self._timer_lock = threading.Lock()
        self.dmr_id     = get_dmr_id()
        self.my_call    = get_my_callsign()
        self.watch_tg, self.restore_tg = get_dynamic_tgs()
        self._stop      = threading.Event()
        self._cmd_server = CmdServer(self)

        # --- [v2.3.4] コールサイン・ウォッチドッグ状態 ---
        self.away_tg: "str | None" = None   # 現在「離脱(他TG)」中なら、そのTG番号。ホーム/監視TGに戻ると None。
        self.tracked_call = ""              # 他TGへ最後にRFアクセスした「真の利用者」コールサイン
        self.rf_deadline  = 0.0             # この時刻を過ぎても tracked_call のRFが無ければ強制復帰

        log(f"🚀 TGIFChanger-Py {VERSION} Active")
        log(f"   HOME=TG{self.restore_tg}/Slot{config['RESTORE_SLOT']}  DELAY={config.get('RESTORE_DELAY', '120')}s  CS_TIMEOUT={config.get('CALLSIGN_TIMEOUT','300')}s")
        log(f"   WATCH=TG{self.watch_tg}  DMR ID={self.dmr_id or '(unknown)'}")

    # --- [v2.3.4] 離脱状態・ウォッチドッグのクリア ---
    def _clear_away(self) -> None:
        if self.away_tg is not None or self.tracked_call:
            self.away_tg      = None
            self.tracked_call = ""
            self.rf_deadline  = 0.0

    def cancel_timer(self) -> None:
        with self._timer_lock:
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
                log("🛑 復帰タイマーをキャンセルしました。")

    def schedule_restore(self, prev_tg: str) -> None:
        self.cancel_timer()
        delay = float(config.get("RESTORE_DELAY", "120"))
        log(f"[END] TG {prev_tg} | {int(delay)}秒後に復帰します...")
        with self._timer_lock:
            t = threading.Timer(delay, self._do_restore)
            t.daemon = True
            self.timer = t
            t.start()

    def _do_restore(self) -> None:
        with self._timer_lock:
            self.timer = None
        log(f"🔄 TG {self.restore_tg} に自動復帰中...")
        slot_idx = int(config.get("RESTORE_SLOT", "2")) - 1
        url = (f"{config['TGIF_API'].rstrip('/')}/{self.dmr_id}/{slot_idx}/{self.restore_tg}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=int(config.get("TGIF_API_TIMEOUT", "10"))) as res:
                log(f"✅ TG変更リクエスト送信完了 (HTTP {res.status})")
        except urllib.error.HTTPError as e: log(f"⚠️ HTTP {e.code}")
        except (urllib.error.URLError, OSError) as e: log(f"❌ TGIF API 通信エラー: {e}")
        # 復帰したのでウォッチドッグ状態を解除
        self._clear_away()

    def process_line(self, line: str) -> None:
        slot_marker = f"Slot {config['WATCH_SLOT']},"
        if slot_marker not in line: return

        if "voice header" in line:
            self.cancel_timer()
            m_call = re.search(r"from (\S+)", line)
            from_call = m_call.group(1).upper() if m_call else ""
            m_tg = re.search(r"to TG (\d+)", line)
            tg = m_tg.group(1) if m_tg else None
            is_rf = "received RF voice header" in line   # 自局(RF)キーアップ。network受信と区別する。

            # --- [v2.3.4] コールサイン・ウォッチドッグ ---
            # ホーム/監視TGの通話を見たら「在宅」とみなしウォッチドッグ解除。
            # 他TGへの "RF(自局側)キーアップ" は「真の利用者のアクセス」として記録し、
            #   そのコールサインを追跡対象に設定/更新して 5分タイマーをリセットする。
            #   ※ network受信(リモート通話)はここを通らないのでカウントされない。
            if tg and tg in (self.watch_tg, self.restore_tg):
                self._clear_away()
            elif is_rf and tg:
                cs_to = float(config.get("CALLSIGN_TIMEOUT", "300") or 0)
                if cs_to > 0:
                    switched = bool(self.tracked_call) and self.tracked_call != from_call
                    self.tracked_call = from_call
                    self.rf_deadline  = time.time() + cs_to
                    self.away_tg      = tg
                    tag = "対象切替" if switched else "アクセス確認"
                    log(f"👤 {tag}: {from_call or '?'} → TG{tg} （{int(cs_to)}秒監視開始）")

            # 自局送信は GPIO 点灯の対象外（ウォッチドッグ記録は上で済ませてある）
            if from_call and self.my_call and from_call == self.my_call:
                return
            if tg and tg == self.watch_tg:
                self.gpio.set(1)
                log(f"[ RECEIVING ] TG{self.watch_tg} | From: {from_call or 'Unknown'}")

        elif re.search(r"end of voice transmission|transmission lost|watchdog has expired", line):
            m_tg  = re.search(r"to TG (\d+)", line)
            tg    = m_tg.group(1) if m_tg else None

            if tg == self.watch_tg:
                self.gpio.set(0)
                log(f"[    IDLE   ] TG{tg}")
            elif tg is None and self.gpio.state == 1:
                self.gpio.set(0)
                log("[    IDLE   ] Force Reset (Signal Lost)")

            if tg and tg not in (self.watch_tg, self.restore_tg):
                self.schedule_restore(tg)
            elif tg:
                log(f"ℹ️ [SKIP] TG {tg} は自動復帰の対象外です。")

    def run(self) -> int:
        try:
            lock_fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(lock_fd, f"{os.getpid()}\n".encode())
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                log("❌ 多重起動を検出。終了します。")
                return 1
            raise

        self._install_signals()
        self._cmd_server.start()
        log_dir = config.get("LOG_DIR", "/var/log/pi-star")

        def get_latest():
            files = glob.glob(os.path.join(log_dir, LOG_PATTERN))
            return max(files, key=os.path.getmtime) if files else None

        current_file = None
        for _ in range(240):
            current_file = get_latest()
            if current_file: break
            time.sleep(0.5)
        if not current_file:
            log("❌ ログファイルが見つかりません。終了します。")
            return 1

        log(f"📁 監視開始: {os.path.basename(current_file)}")
        fh = open(current_file, "r", encoding="utf-8", errors="ignore")
        fh.seek(0, 2)
        current_ino = os.stat(current_file).st_ino

        try:
            while not self._stop.is_set():
                if (self.gpio.state == 1 and self.gpio.high_start > 0 and time.time() - self.gpio.high_start > GPIO_FAILSAFE_SEC):
                    log(f"🚨 [FAIL-SAFE] {GPIO_FAILSAFE_SEC}s timeout. Forcing LOW.")
                    self.gpio.set(0)

                # --- [v2.3.4] コールサイン・ウォッチドッグ判定 ---
                # 他TGに留まっている間、真の利用者(RFアクセス局)が CALLSIGN_TIMEOUT 秒
                # 確認できなければ、ネット側の通話が続いていても強制復帰する。
                if (self.away_tg and self.rf_deadline and time.time() > self.rf_deadline):
                    cs_to = int(float(config.get("CALLSIGN_TIMEOUT", "300") or 0))
                    log(f"⏰ [CS-WATCHDOG] {self.tracked_call or '?'} を{cs_to}秒確認できず → TG{self.restore_tg} へ強制復帰")
                    self.cancel_timer()
                    self._do_restore()   # 内部で _clear_away() される

                line = fh.readline()
                if line:
                    self.process_line(line)
                    continue
                
                # --- EOFバッファクリアによるフリーズ防止 ---
                fh.seek(fh.tell())
                time.sleep(0.2)

                # --- ログ切替チェックの堅牢化 (v2.3.3) ---
                latest = get_latest()
                if not latest:
                    # logrotateの瞬間に一時的にglobが空になった場合は、現ファイル維持のまま次ループへ
                    continue

                try:
                    new_ino = os.stat(latest).st_ino
                    # ファイル名が変わった、またはinodeが変わった（同名で新ファイルが生成された）場合
                    if latest != current_file or new_ino != current_ino:
                        # 完全に書き換わる（または古いログのフラッシュ）を少しだけ待つ安全弁
                        time.sleep(0.1)
                        
                        fh.close()
                        current_file = latest
                        fh = open(current_file, "r", encoding="utf-8", errors="ignore")
                        current_ino = new_ino
                        log(f"🔄 ログ切替: {os.path.basename(current_file)}")
                        fh.seek(0, 2)
                except (FileNotFoundError, PermissionError):
                    # ログの圧縮・削除処理中の瞬間的なエラーは無視して、現ファイルを掴んだまま次ループで再検知を待つ
                    continue

        except KeyboardInterrupt:
            pass
        finally:
            try: fh.close()
            except OSError: pass
            self._shutdown()

        return 0

    def _shutdown(self) -> None:
        log("⚠️ 停止")
        self.cancel_timer()
        self.gpio.cleanup()
        self._cmd_server.stop()
        try: os.unlink(LOCK_FILE)
        except OSError: pass

    def _install_signals(self) -> None:
        def stop(sig, frame): self._stop.set()
        def reload_(sig, frame):
            load_config()
            self.watch_tg, self.restore_tg = get_dynamic_tgs()
            log("🔄 SIGHUP: 設定リロード完了")
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: signal.signal(sig, stop)
            except (ValueError, OSError): pass
        try: signal.signal(signal.SIGHUP, reload_)
        except (ValueError, OSError, AttributeError): pass

if __name__ == "__main__":
    sys.exit(App().run())
