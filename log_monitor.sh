#!/bin/bash
# =============================================================================
# log_monitor.sh - MMDVM to GPIO Bridge
# VERSION: v1.2.1 (Dynamic Network Tracking & libgpiod auto-adjust)
# =============================================================================
VERSION="v1.2.1"
CONF_FILE="/etc/tgifchanger.conf"
MMDVM_CONF="/etc/mmdvmhost"

LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
WATCH_TG=""
GPIO_PIN="17"
GPIO_BACKEND="auto"
GPIO_CHIP="0"

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

get_my_callsign() {
    local call=""
    if [ -f "$MMDVM_CONF" ]; then
        call=$(grep "^Callsign=" "$MMDVM_CONF" | awk -F= '{print $2}' | tr -d '\r ' | tr '[:lower:]' '[:upper:]')
    fi
    echo "$call"
}

# --- TG動的取得ロジック (柔軟な追従対応) ---
get_dynamic_tgs() {
    if [ -f "$MMDVM_CONF" ]; then
        # Address=tgif.network を含むDMR Networkセクションを自動で探し、TGRewrite1を抽出
        local rewrite_line=$(awk '
            /^\[DMR Network / { in_dmr=1; is_tgif=0; next }
            /^\[/ { in_dmr=0 }
            in_dmr && /Address=tgif\.network/ { is_tgif=1 }
            in_dmr && is_tgif && /^TGRewrite1=/ { print; exit }
        ' "$MMDVM_CONF")
        
        if [ -n "$rewrite_line" ]; then
            local vals=$(echo "$rewrite_line" | awk -F= '{print $2}')
            WATCH_TG=$(echo "$vals" | cut -d, -f2 | tr -d '\r')
        fi
    fi
    [ -z "$WATCH_TG" ] && WATCH_TG="6"
}

MY_CALL=$(get_my_callsign)
[ -z "$MY_CALL" ] && log "⚠️ 自局コールサイン取得失敗" || log "🆔 自局: $MY_CALL"

get_dynamic_tgs
log "🎯 監視対象 TG: ${WATCH_TG} (自動追従)"

detect_libgpiod_features() {
    if gpioset --version 2>&1 | grep -q "libgpiod) 2"; then
        LIBGPIOD_VERSION=2
    else
        LIBGPIOD_VERSION=1
    fi
}

GPIO_STATE=-1
GPIOSET_PID=""

set_gpio() {
    local val=$1
    [ "$val" = "$GPIO_STATE" ] && return
    if [ -n "$GPIOSET_PID" ] && kill -0 "$GPIOSET_PID" 2>/dev/null; then
        kill "$GPIOSET_PID" 2>/dev/null
        wait "$GPIOSET_PID" 2>/dev/null
        GPIOSET_PID=""
    fi
    if [ "$val" = "1" ]; then
        if [ "$LIBGPIOD_VERSION" -eq 2 ]; then
            gpioset "$GPIO_CHIP" "${GPIO_PIN}=1" --mode=wait &
        else
            gpioset -m wait "$GPIO_CHIP" "${GPIO_PIN}=1" &
        fi
        GPIOSET_PID=$!
        log "⚡ GPIO${GPIO_PIN} -> HIGH"
    else
        gpioset "$GPIO_CHIP" "${GPIO_PIN}=0" 2>/dev/null
        log "🌑 GPIO${GPIO_PIN} -> LOW"
    fi
    GPIO_STATE=$val
}

cleanup() { log "⚠️ 停止"; set_gpio 0; exit 0; }
trap cleanup SIGINT SIGTERM

detect_libgpiod_features
log "🚀 log_monitor.sh Active (v${LIBGPIOD_VERSION}) CHIP=${GPIO_CHIP}"

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
                set_gpio 1
                log "[ RECEIVING ] TG${tg} | From: ${from_call}"
            fi
        elif echo "$line" | grep -q "end of voice transmission"; then
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [ "$tg" = "$WATCH_TG" ]; then
                set_gpio 0
                log "[    IDLE    ] TG${tg}"
            fi
        fi
    fi
done
