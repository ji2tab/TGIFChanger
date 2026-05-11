#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - Unified MMDVM Daemon
#
# File:        tgif_daemon.py
# Version:     v2.3.0
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Changes from v2.2.0:
#   - DMR ID: tgif.network セクション正引き (§2.4仕様準拠)
#   - FIFO制御をUnix domain socketに変更(競合・上書き消滅を解消)
#   - GPIOエンジン: libgpiod v1/v2 + gpiodetect(Pi5対応) 追加
#   - fcntl.flockによる多重起動防止を追加
#   - ExecStartPre sleep廃止に伴い、ログファイル待機ループで吸収
#   - Restart=on-failure (仕様書§5準拠)
#   - signal handler: SIGTERM/SIGINT で GPIO LOW + クリーンシャットダウン
#   - SIGHUP で設定リロード
# =============================================================================

import os, sys, re, time, glob, fcntl, errno, signal, socket, threading
import urllib.request, urllib.error, subprocess, shutil
from pathlib import Path

VERSION        = "v2.3.0"
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
    "WATCH_TG":         "1",
    "RESTORE_TG":       "168",
    "GPIO_PIN":         "17",
    "GPIO_CHIP":        "auto",
    "GPIO_BACKEND":     "auto",
    "RESTORE_DELAY":    "120",
    "TGIF_API":         "http://tgif.network:5040/api/sessions/update",
    "TGIF_API_TIMEOUT": "10",
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------

def load_config() -> None:
    """bash KEY=VALUE形式の設定ファイルを読み込む。"""
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
# DMR ID / コールサイン (仕様書 §2.4 に準拠)
# ---------------------------------------------------------------------------

def _iter_sections(path: str):
    """(section_name, [lines]) を順に返す簡易 INI パーサ。"""
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
    """
    取得順序 (仕様書 §2.4):
      1. /etc/dmrgateway の [DMR Network *] で Address=tgif.network の Id=
      2. /etc/mmdvmhost の先頭 Id= (fallback)
    """
    # 1) dmrgateway
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

    # 2) mmdvmhost fallback
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
    """
    (WATCH_TG, RESTORE_TG) を解決する。
    conf に両方あればそれを最優先、なければ TGRewrite= から自動抽出。
    """
    w = config.get("WATCH_TG", "").strip()
    r = config.get("RESTORE_TG", "").strip()
    if w and r:
        return w, r

    # mmdvmhost の TGRewrite から自動抽出
    for section, lines in _iter_sections(MMDVM_CONF):
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
            return (w or parsed_w or "1"), (r or parsed_r or "168")

    return (w or "1"), (r or "168")


# ---------------------------------------------------------------------------
# GPIO エンジン (ハイブリッド版)
# デフォルト: pinctrl/raspi-gpio/sysfs (Buster実績)
# オプト: libgpiod v1/v2 (Bookworm/Pi5対応、仕様書§6推奨)
# ---------------------------------------------------------------------------

def _detect_gpiochip(requested: str) -> str:
    """gpiochip名を解決。'auto'なら gpiodetect でBCMチップを探す。"""
    if requested.startswith("gpiochip"):
        return requested
    if requested.isdigit():
        return f"gpiochip{requested}"
    if requested != "auto":
        return requested
    if not shutil.which("gpiodetect"):
        return "gpiochip0"
    try:
        cp = subprocess.run(["gpiodetect"], capture_output=True, text=True,
                            check=False, timeout=2.0)
        for line in cp.stdout.splitlines():
            m = re.match(r"^(gpiochip\d+)\s+\[(.+?)\]", line)
            if m and ("pinctrl-bcm" in m.group(2) or "pinctrl-rp1" in m.group(2)):
                return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return "gpiochip0"


def _gpioset_version() -> int:
    """gpiosetのメジャーバージョン。未インストール→0。"""
    if not shutil.which("gpioset"):
        return 0
    try:
        cp = subprocess.run(["gpioset", "--version"], capture_output=True,
                            text=True, check=False, timeout=2.0)
        blob = (cp.stdout or "") + (cp.stderr or "")
        if re.search(r"libgpiod\)?\s*2|libgpiod 2", blob):
            return 2
        return 1
    except (OSError, subprocess.SubprocessError):
        return 0


class GPIOEngine:
    """
    GPIO制御エンジン。backend設定で動作モード選択可能。

    Modes:
      'auto' (デフォルト)
          → pinctrl / raspi-gpio / sysfs を順に試す (v2.2.0互換)
      'libgpiod'
          → libgpiod v1/v2 を使用 (§6対応、Bookworm/Pi5推奨)
      'pinctrl', 'raspi-gpio', 'sysfs', 'null'
          → 強制指定
    """

    def __init__(self, pin: str, chip_cfg: str, backend_cfg: str):
        self.pin = str(pin)
        self.chip = _detect_gpiochip(chip_cfg)
        self.state = -1
        self.high_start = 0.0
        self._gpioset_ver = _gpioset_version()
        self._bg_proc = None
        self.backend_cfg = backend_cfg.lower()
        self.engine = self._select()
        log(f"🎛  GPIO{self.pin} engine={self.engine}" +
            (f" chip={self.chip}" if "libgpiod" in self.engine else ""))

    def _select(self) -> str:
        """backendと環境から実際のエンジンを決定する。"""
        b = self.backend_cfg
        
        # 明示的なlibgpiod指定
        if b == "libgpiod":
            if self._gpioset_ver > 0:
                return f"libgpiod_v{self._gpioset_ver}"
            log("⚠️  libgpiod指定だが gpioset が見つかりません。fallback")
            return self._fallback_simple()
        
        # 明示的なシンプルモード指定
        if b in ("pinctrl", "raspi-gpio", "sysfs", "null"):
            return self._init_simple(b)
        
        # auto (デフォルト): pinctrl/raspi-gpio/sysfs を順に試す
        return self._fallback_simple()

    def _init_simple(self, engine: str) -> str:
        """pinctrl/raspi-gpio/sysfs のいずれかで初期化。"""
        try:
            if engine == "pinctrl" and subprocess.run(
                "command -v pinctrl", shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False).returncode == 0:
                subprocess.run(["pinctrl", "set", self.pin, "op", "pn", "dl"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False)
                return "pinctrl"
            
            if engine == "raspi-gpio" and subprocess.run(
                "command -v raspi-gpio", shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False).returncode == 0:
                subprocess.run(["raspi-gpio", "set", self.pin, "op", "pn", "dl"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False)
                return "raspi-gpio"
            
            if engine == "sysfs" and os.path.isdir("/sys/class/gpio"):
                gdir = f"/sys/class/gpio/gpio{self.pin}"
                if not os.path.isdir(gdir):
                    with open("/sys/class/gpio/export", "w") as f:
                        f.write(self.pin)
                    time.sleep(0.1)
                with open(f"{gdir}/direction", "w") as f:
                    f.write("out")
                with open(f"{gdir}/value", "w") as f:
                    f.write("0")
                return "sysfs"
            
            if engine == "null":
                return "null"
        except OSError:
            pass
        return "null"

    def _fallback_simple(self) -> str:
        """pinctrl → raspi-gpio → sysfs → null (v2.2.0互換の優先順)。"""
        for eng in ("pinctrl", "raspi-gpio", "sysfs"):
            result = self._init_simple(eng)
            if result != "null":
                return result
        return "null"

    def _kill_bg(self) -> None:
        """libgpiod バックグラウンドプロセスを停止。"""
        if self._bg_proc is not None:
            try:
                self._bg_proc.terminate()
                self._bg_proc.wait(timeout=1.0)
            except (OSError, subprocess.SubprocessError):
                try:
                    self._bg_proc.kill()
                except OSError:
                    pass
            self._bg_proc = None

    def set(self, val: int) -> None:
        """GPIOをHIGH(1)またはLOW(0)にする。"""
        if self.state == val:
            return
        
        try:
            if "libgpiod" in self.engine:
                self._kill_bg()
                if val:
                    if self._gpioset_ver == 2:
                        cmd = ["gpioset", "-c", self.chip, "--mode=wait",
                               f"{self.pin}=1"]
                    else:
                        cmd = ["gpioset", "--mode=wait", self.chip,
                               f"{self.pin}=1"]
                    self._bg_proc = subprocess.Popen(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    if self._gpioset_ver == 2:
                        subprocess.run(["gpioset", "-c", self.chip, f"{self.pin}=0"],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, check=False)
                    else:
                        subprocess.run(["gpioset", self.chip, f"{self.pin}=0"],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, check=False)
            elif self.engine == "pinctrl":
                subprocess.run(["pinctrl", "set", self.pin, "dh" if val else "dl"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False)
            elif self.engine == "raspi-gpio":
                subprocess.run(["raspi-gpio", "set", self.pin, "dh" if val else "dl"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False)
            elif self.engine == "sysfs":
                with open(f"/sys/class/gpio/gpio{self.pin}/value", "w") as f:
                    f.write(str(val))
        except OSError as e:
            log(f"⚠️ GPIO Error: {e}")

        self.high_start = time.time() if val else 0.0
        self.state = val
        log(f"⚡ GPIO{self.pin} -> HIGH" if val else f"🌑 GPIO{self.pin} -> LOW")

    def cleanup(self) -> None:
        """GPIO状態をLOWに戻す。sysfs/libgpiod v2のプロセスも停止。"""
        self.set(0)
        self._kill_bg()
        if self.engine == "sysfs":
            try:
                with open("/sys/class/gpio/unexport", "w") as f:
                    f.write(self.pin)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# コマンドソケットサーバ (Unix domain socket)
# ---------------------------------------------------------------------------

class CmdServer:
    """
    tg_change.py からのコマンドを Unix socket 経由で受け取る。
    以前のFIFO(ポーリング+上書き競合)を置き換え。

    プロトコル: クライアントが1行テキストを送る → "OK\n" を返す。
    コマンド一覧:
        stop    ... 復帰タイマーをキャンセル
        reload  ... 設定リロード
        status  ... JSON 文字列を返す
    """

    def __init__(self, app: "App") -> None:
        self.app  = app
        self._sock: "socket.socket | None" = None
        self._thr: "threading.Thread | None" = None
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            if os.path.exists(CMD_SOCKET):
                os.unlink(CMD_SOCKET)
            os.makedirs(os.path.dirname(CMD_SOCKET) or "/", exist_ok=True)
        except OSError:
            pass
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
        self._thr  = threading.Thread(target=self._serve, daemon=True,
                                      name="cmd-server")
        self._thr.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as w:
                w.settimeout(0.2)
                w.connect(CMD_SOCKET)
        except OSError:
            pass
        if self._thr:
            self._thr.join(timeout=2.0)
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            os.unlink(CMD_SOCKET)
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    conn.settimeout(2.0)
                    data = b""
                    while b"\n" not in data and len(data) < 512:
                        chunk = conn.recv(512)
                        if not chunk:
                            break
                        data += chunk
                    cmd  = data.decode("utf-8", "replace").strip().lower()
                    resp = self._handle(cmd)
                    conn.sendall((resp + "\n").encode("utf-8"))
                except OSError:
                    continue

    def _handle(self, cmd: str) -> str:
        app = self.app
        if cmd == "stop":
            app.cancel_timer()
            return "OK stop"
        if cmd == "reload":
            load_config()
            app.watch_tg, app.restore_tg = get_dynamic_tgs()
            log("🔄 設定リロード完了")
            log(f"   HOME=TG{app.restore_tg}  WATCH=TG{app.watch_tg}"
                f"  DELAY={config['RESTORE_DELAY']}s")
            return "OK reload"
        if cmd == "status":
            import json
            d = {
                "version":    VERSION,
                "watch_tg":   app.watch_tg,
                "restore_tg": app.restore_tg,
                "delay":      config["RESTORE_DELAY"],
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
        self.gpio       = GPIOEngine(
            config["GPIO_PIN"],
            config.get("GPIO_CHIP", "auto"),      # 保持するが使わない
            config.get("GPIO_BACKEND", "auto")    # 保持するが使わない
        )
        self.timer: "threading.Timer | None" = None
        self._timer_lock = threading.Lock()
        self.dmr_id     = get_dmr_id()
        self.my_call    = get_my_callsign()
        self.watch_tg, self.restore_tg = get_dynamic_tgs()
        self._stop      = threading.Event()
        self._cmd_server = CmdServer(self)

        log(f"🚀 TGIFChanger-Py {VERSION} Active")
        log(f"   HOME=TG{self.restore_tg}/Slot{config['RESTORE_SLOT']}"
            f"  DELAY={config['RESTORE_DELAY']}s")
        log(f"   WATCH=TG{self.watch_tg}  DMR ID={self.dmr_id or '(unknown)'}")

    # --- timer management ---

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
        url = (f"{config['TGIF_API'].rstrip('/')}"
               f"/{self.dmr_id}/{slot_idx}/{self.restore_tg}")
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, method="GET"),
                timeout=int(config.get("TGIF_API_TIMEOUT", "10"))
            ) as res:
                log(f"✅ TG変更リクエスト送信完了 (HTTP {res.status})")
        except urllib.error.HTTPError as e:
            log(f"⚠️ HTTP {e.code}")
        except (urllib.error.URLError, OSError) as e:
            log(f"❌ TGIF API 通信エラー: {e}")

    # --- log line processing ---

    def process_line(self, line: str) -> None:
        slot_marker = f"Slot {config['WATCH_SLOT']},"
        if slot_marker not in line:
            return

        if "voice header" in line:
            # 受信開始: タイマーキャンセル
            self.cancel_timer()
            m_call = re.search(r"from (\S+)", line)
            from_call = m_call.group(1).upper() if m_call else ""
            if from_call and self.my_call and from_call == self.my_call:
                return  # 自局送信は無視
            m_tg = re.search(r"to TG (\d+)", line)
            if m_tg and m_tg.group(1) == self.watch_tg:
                self.gpio.set(1)
                log(f"[ RECEIVING ] TG{self.watch_tg}"
                    f" | From: {from_call or 'Unknown'}")

        elif re.search(
            r"end of voice transmission|transmission lost|watchdog has expired",
            line
        ):
            m_tg  = re.search(r"to TG (\d+)", line)
            tg    = m_tg.group(1) if m_tg else None

            # GPIO を落とす
            if tg == self.watch_tg:
                self.gpio.set(0)
                log(f"[   IDLE   ] TG{tg}")
            elif tg is None and self.gpio.state == 1:
                self.gpio.set(0)
                log("[   IDLE   ] Force Reset (Signal Lost)")

            # 復帰タイマー判定
            if tg and tg not in (self.watch_tg, self.restore_tg):
                self.schedule_restore(tg)
            elif tg:
