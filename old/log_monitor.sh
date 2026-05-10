#!/bin/bash
# =============================================================================
# TGIFChanger - MMDVM to GPIO Bridge
# 
# File:        log_monitor.sh
# Version:     v1.2.4
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Monitors MMDVM logs in real-time to detect specific TG activity.
#              Controls a Raspberry Pi GPIO pin to indicate receiving status.
#              (v1.2.4: Ultimate GPIO Engine for WPSD/Bookworm/legacy support)
# License:     GPL v3
# =============================================================================

VERSION="v1.2.4"
CONF_FILE="/etc/tgifchanger.conf"
MMDVM_CONF="/etc/mmdvmhost"
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
WATCH_TG=""
GPIO_PIN="17"
GPIO_CHIP="0"

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

get_my_callsign() {
    local call=""
    if [ -f "$MMDVM_CONF" ]; then
        call=$(grep -m 1 "^Callsign=" "$MMDVM_CONF" | awk -F= '{print $2}' | tr -d '\r ' | tr '[:lower:]' '[:upper:]')
    fi
    echo "$call"
}

get_dynamic_tgs() {
    [ -n "$WATCH_TG" ] && return

    if [ -f "$MMDVM_CONF" ]; then
        local rewrite_line=$(awk '
            /^\[DMR Network / { in_dmr=1; is_tgif=0; next }
            /^\[/ { in_dmr=0 }
            in_dmr && /Address=tgif\.network/ { is_tgif=1 }
            in_dmr && is_tgif && /^TGRewrite/ { print; exit }
        ' "$MMDVM_CONF")
        if [ -n "$rewrite_line" ]; then
            local vals=$(echo "$rewrite_line" | awk -F= '{print $2}')
            WATCH_TG=$(echo "$vals" | cut -d, -f2 | tr -dc '0-9')
        fi
    fi
    [ -z "$WATCH_TG" ] && WATCH_TG="6"
}

MY_CALL=$(get_my_callsign)
get_dynamic_tgs
log "🎯 監視対象 TG: ${WATCH_TG} (Config優先)"

# --- GPIO Engine Auto-Detection ---
GPIO_ENGINE="unknown"
if command -v pinctrl >/dev/null 2>&1; then
    GPIO_ENGINE="pinctrl"
    pinctrl set "$GPIO_PIN" op pn dl  # Set Output, Pull-None, Drive-Low (初期化)
elif command -v raspi-gpio >/dev/null 2>&1; then
    GPIO_ENGINE="raspi-gpio"
    raspi-gpio set "$GPIO_PIN" op pn dl # 初期化
elif command -v gpioset >/dev/null 2>&1 && gpioset --version 2>&1 | grep -q "libgpiod) 2"; then
    GPIO_ENGINE="gpiod_v2"
elif [ -d "/sys/class/gpio" ]; then
    GPIO_ENGINE="sysfs"
    echo "$GPIO_PIN" > /sys/class/gpio/export 2>/dev/null
    sleep 0.1
    echo "out" > /sys/class/gpio/gpio${GPIO_PIN}/direction 2>/dev/null
fi

log "🚀 log_monitor.sh Active (Engine: ${GPIO_ENGINE})"

GPIO_STATE=-1
GPIOSET_PID=""

set_gpio() {
    local val=$1
    [ "$val" = "$GPIO_STATE" ] && return

    case "$GPIO_ENGINE" in
        "pinctrl")
            [ "$val" = "1" ] && pinctrl set "$GPIO_PIN" dh || pinctrl set "$GPIO_PIN" dl
            ;;
        "raspi-gpio")
            [ "$val" = "1" ] && raspi-gpio set "$GPIO_PIN" dh || raspi-gpio set "$GPIO_PIN" dl
            ;;
        "gpiod_v2")
            if [ -n "$GPIOSET_PID" ] && kill -0 "$GPIOSET_PID" 2>/dev/null; then
                kill "$GPIOSET_PID" 2>/dev/null; wait "$GPIOSET_PID" 2>/dev/null; GPIOSET_PID=""
            fi
            if [ "$val" = "1" ]; then
                gpioset "$GPIO_CHIP" "${GPIO_PIN}=1" --mode=wait &
                GPIOSET_PID=$!
            else
                gpioset "$GPIO_CHIP" "${GPIO_PIN}=0" 2>/dev/null
            fi
            ;;
        "sysfs")
            echo "$val" > /sys/class/gpio/gpio${GPIO_PIN}/value 2>/dev/null
            ;;
        *)
            log "⚠️ [Error] No valid GPIO engine available."
            ;;
    esac

    [ "$val" = "1" ] && log "⚡ GPIO${GPIO_PIN} -> HIGH" || log "🌑 GPIO${GPIO_PIN} -> LOW"
    GPIO_STATE=$val
}

cleanup() {
    log "⚠️ 停止"
    set_gpio 0
    [ "$GPIO_ENGINE" = "sysfs" ] && echo "$GPIO_PIN" > /sys/class/gpio/unexport 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

get_latest_log() { ls -t "${LOG_DIR}"/MMDVM-*.log 2>/dev/null | head -1; }
current_file=$(get_latest_log)
while [ -z "$current_file" ]; do sleep 5; current_file=$(get_latest_log); done
exec 3< <(tail -n 0 -F "$current_file" 2>/dev/null)

while :; do
    if read -r -t 5 line <&3; then
        echo "$line" | grep -q "Slot ${WATCH_SLOT}," || continue
        if echo "$line" | grep -q "voice header"; then
            from_call=$(echo "$line" | grep -oP 'from \K[^ ]+' | tr '[:lower:]' '[:upper:]')
            [ "$from_call" = "$MY_CALL" ] && continue
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [ "$tg" = "$WATCH_TG" ]; then
                set_gpio 1; log "[ RECEIVING ] TG${tg} | From: ${from_call}"
            fi
        elif echo "$line" | grep -q "end of voice transmission"; then
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [ "$tg" = "$WATCH_TG" ]; then
                set_gpio 0; log "[   IDLE   ] TG${tg}"
            fi
        fi
    fi
done
