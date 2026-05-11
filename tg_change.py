#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# TGIFChanger-Py - TGIF Talk Group Changer CLI
#
# File:        tg_change.py
# Version:     v2.3.1
# Author:      Kazuhiko Shinoda (JI2TAB)
# License:     GPL v3
#
# Changes from v2.3.0:
#   - デフォルト表示を -168 から -4000 へ変更
# =============================================================================

import sys, os, re, socket, json, urllib.request, urllib.error
from pathlib import Path

CONF_FILE  = "/etc/tgifchanger.conf"
CMD_SOCKET = "/run/tgifchanger-py.sock"
DMRGW_CONF = "/etc/dmrgateway"
MMDVM_CONF = "/etc/mmdvmhost"


def _send_cmd(cmd: str) -> str:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(CMD_SOCKET)
            s.sendall((cmd + "\n").encode("utf-8"))
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b"\n"):
                    break
        return buf.decode("utf-8", "replace").strip()
    except (OSError, socket.timeout) as e:
        return f"ERR socket: {e}"


def _load_conf() -> dict:
    result = {}
    if not os.path.isfile(CONF_FILE):
        return result
    for line in Path(CONF_FILE).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _save_conf(key: str, value: str) -> None:
    if os.geteuid() != 0:
        print(f"❌ エラー: 設定変更には root 権限が必要です。")
        print(f"   sudo tg_change {' '.join(sys.argv[1:])} を実行してください。")
        sys.exit(1)
    lines, found = [], False
    if os.path.isfile(CONF_FILE):
        for line in Path(CONF_FILE).read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True):
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                lines.append(f'{key}="{value}"\n')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    try:
        Path(CONF_FILE).write_text("".join(lines), encoding="utf-8")
    except OSError as e:
        print(f"❌ 書き込みエラー: {e}")
        sys.exit(1)


def _iter_sections(path: str):
    if not os.path.isfile(path):
        return
    current, buf = "", []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\[(.+?)\]\s*$", raw)
        if m:
            yield current, buf
            current, buf = m.group(1).strip(), []
        else:
            buf.append(raw)
    yield current, buf


def _get_dmr_id() -> str:
    for section, lines in _iter_sections(DMRGW_CONF):
        if not section.startswith("DMR Network"):
            continue
        is_tgif, found_id = False, ""
        for line in lines:
            s = line.strip()
            if not s or s.startswith(("#", ";")):
                continue
            if "=" not in s:
                continue
            k, _, v = s.partition("=")
            k, v = k.strip(), v.split("#", 1)[0].strip()
            if k == "Address" and "tgif.network" in v:
                is_tgif = True
            elif k == "Id" and v:
                found_id = v
        if is_tgif and found_id:
            return found_id
    for _sec, lines in _iter_sections(MMDVM_CONF):
        for line in lines:
            s = line.strip()
            if s.startswith("Id=") and "=" in s:
                _, _, v = s.partition("=")
                v = v.split("#", 1)[0].strip()
                if v:
                    return v
    return ""


def cmd_show_config() -> None:
    print("⚙️  現在の TGIFChanger 設定:")
    print("-" * 40)
    if os.path.isfile(CONF_FILE):
        for line in Path(CONF_FILE).read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                print(f"  {stripped}")
    else:
        print("  (設定ファイルがまだ作成されていません)")
    print("-" * 40)


def cmd_status() -> int:
    raw = _send_cmd("status")
    if raw.startswith("ERR"):
        print(f"❌ デーモン応答なし: {raw}")
        print(f"   サービスが起動しているか確認: systemctl status tgifchanger-py")
        return 1
    try:
        data = json.loads(raw)
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")
    except json.JSONDecodeError:
        print(raw)
    return 0


def cmd_cancel_timer() -> int:
    resp = _send_cmd("stop")
    if resp.startswith("OK"):
        print("✅ タイマー停止信号を送信しました。")
        return 0
    print(f"⚠️ デーモン応答: {resp}")
    return 1


def cmd_set_conf(key: str, value: str, label: str) -> int:
    _save_conf(key, value)
    resp = _send_cmd("reload")
    ok = resp.startswith("OK")
    if ok:
        print(f"✅ {label} に設定し、デーモンに反映しました。")
    else:
        print(f"✅ {label} に設定しました。")
        print(f"   (デーモン未起動またはリロード応答なし: {resp})")
    return 0


def cmd_change_tg(arg: str) -> int:
    target = arg.lstrip("-")
    if ":" in target:
        tg, slot_str = target.split(":", 1)
    else:
        tg = target
        slot_str = "1"

    if not re.match(r"^\d+$", tg):
        print(f"❌ エラー: TG番号が不正: {tg!r}")
        return 1
    if slot_str not in ("1", "2"):
        print(f"❌ エラー: スロットは 1 または 2: {slot_str!r}")
        return 1

    conf  = _load_conf()
    api   = conf.get("TGIF_API", "http://tgif.network:5040/api/sessions/update").rstrip("/")
    tout  = int(conf.get("TGIF_API_TIMEOUT", "10"))
    dmr_id = _get_dmr_id()
    if not dmr_id:
        print("❌ エラー: DMR ID を取得できませんでした。")
        print("   /etc/dmrgateway または /etc/mmdvmhost を確認してください。")
        return 1

    slot_idx = int(slot_str) - 1
    url = f"{api}/{dmr_id}/{slot_idx}/{tg}"
    print(f"Changing Slot {slot_str} to TG {tg} (DMR ID: {dmr_id})...")
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method="GET"), timeout=tout
        ) as res:
            if 200 <= res.status < 300:
                print(f"✅ TG変更リクエスト送信完了 (HTTP {res.status})")
                return 0
            print(f"⚠️ HTTP {res.status}")
            return 1
    except urllib.error.HTTPError as e:
        print(f"⚠️ HTTP {e.code}")
        return 1
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        print(f"❌ API通信エラー: {reason}")
        return 1


def show_help() -> None:
    print("TGIFChanger CLI v2.3.1\n")
    print("使用方法:")
    print("  【API操作 (即時変更)】")
    print("  tg_change -<TG>[:<Slot>]  現在の接続先TGを即座に変更")
    print("  tg_change -4000           スロット1 を TG4000 に変更")
    print("  tg_change -4000:2         スロット2 を TG4000 に変更")
    print()
    print("  【デーモン操作】")
    print("  tg_change -s / --cancel   動作中の復帰タイマーを停止")
    print("  tg_change --status        デーモンの状態を JSON 表示")
    print()
    print("  【設定の変更・確認 (root必要)】")
    print("  tg_change -w <TG>         監視TG (WATCH_TG) を設定")
    print("  tg_change -r <TG>         復帰TG (RESTORE_TG) を設定")
    print("  tg_change -t <秒数>       復帰時間 (RESTORE_DELAY) を設定")
    print("  tg_change -c              現在の設定一覧を確認")
    print()
    print("  -h / --help               このヘルプを表示")


def main() -> int:
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        show_help()
        return 0

    cmd = args[0]

    if cmd in ("-s", "--cancel"):
        return cmd_cancel_timer()

    if cmd == "-c":
        cmd_show_config()
        return 0

    if cmd == "--status":
        return cmd_status()

    if cmd in ("-t", "-w", "-r"):
        if len(args) < 2:
            print("❌ エラー: 設定値が入力されていません。")
            show_help()
            return 1
        val = args[1]
        if cmd == "-t":
            return cmd_set_conf("RESTORE_DELAY", val, f"復帰時間 {val}秒")
        if cmd == "-w":
            return cmd_set_conf("WATCH_TG", val, f"監視TG {val}")
        if cmd == "-r":
            return cmd_set_conf("RESTORE_TG", val, f"復帰TG {val}")

    if re.match(r"^-\d+(:\d+)?$", cmd):
        return cmd_change_tg(cmd)

    print(f"❌ 不明な引数: {cmd!r}")
    show_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
