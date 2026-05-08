#!/bin/bash
# =============================================================================
# auto_tg_restore.sh - TGIF Auto TG Restore Daemon
# VERSION: v1.2.1 (Dynamic Network Tracking)
# =============================================================================
VERSION="v1.2.1"
CONF_FILE="/etc/tgifchanger.conf"
MMDVM_CONF="/etc/mmdvmhost"
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_DELAY="120"
RESTORE_SLOT="2"

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
TG_CHANGE_CMD="${SCRIPT_DIR}/tg_change.sh"
RESTORE_PID_FILE="/run/auto_tg_restore.pid"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# --- TG動的取得ロジック (柔軟な追従対応) ---
get_dynamic_tgs() {
    WATCH_TG=""
    RESTORE_TG=""
    if [ -f "$MMDVM_CONF" ]; then
        local rewrite_line=$(awk '
            /^\[DMR Network / { in_dmr=1; is_tgif=0; next }
            /^\[/ { in_dmr=0 }
            in_dmr && /Address=tgif\.network/ { is_tgif=1 }
            in_dmr && is_tgif && /^TGRewrite1=/ { print; exit }
        ' "$MMDVM_CONF")
        
        if [ -n "$rewrite_line" ]; then
            local vals=$(echo "$rewrite_line" | awk -F= '{print $2}')
            WATCH_TG=$(echo "$vals" | cut -d, -f2 | tr -d '\r')
            RESTORE_TG=$(echo "$vals" | cut -d, -f4 | tr -d '\r')
        fi
    fi
    [ -z "$WATCH_TG" ] && WATCH_TG="6"
    [ -z "$RESTORE_TG" ] && RESTORE_TG="44833"
}

get_dynamic_tgs

cancel_pending_restore() {
    if [ -f "$RESTORE_PID_FILE" ]; then
        local pid=$(cat "$RESTORE_PID_FILE" 2>/dev/null)
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
        rm -f "$RESTORE_PID_FILE"
    fi
}

schedule_restore() {
    local prev_tg=$1
    cancel_pending_restore
    log "[END] TG ${prev_tg} | ${RESTORE_DELAY}秒後に復帰します..."
    (
        sleep "$RESTORE_DELAY"
        log "🔄 TG ${RESTORE_TG} に自動復帰中..."
        "$TG_CHANGE_CMD" "-${RESTORE_TG}:${RESTORE_SLOT}"
        rm -f "$RESTORE_PID_FILE"
    ) &
    echo $! > "$RESTORE_PID_FILE"
}

get_latest_log() { ls -t "${LOG_DIR}"/MMDVM-*.log 2>/dev/null | head -1; }

log "🚀 auto_tg_restore.sh (${VERSION}) Active"
log "   HOME=TG${RESTORE_TG}/Slot${RESTORE_SLOT}  DELAY=${RESTORE_DELAY}s"
log "   IGNORE (No Auto-Restore): TG${WATCH_TG}, TG${RESTORE_TG}"

current_file=$(get_latest_log)
while [ -z "$current_file" ]; do sleep 5; current_file=$(get_latest_log); done
exec 3< <(tail -n 0 -F "$current_file" 2>/dev/null)

while :; do
    if read -r -t 5 line <&3; then
        if echo "$line" | grep -q "Slot ${WATCH_SLOT}," && echo "$line" | grep -q "end of voice transmission"; then
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            
            if [[ "$tg" =~ ^[0-9]+$ ]] && [ "$tg" != "$RESTORE_TG" ] && [ "$tg" != "$WATCH_TG" ]; then
                schedule_restore "$tg"
            else
                log "ℹ️ [SKIP] TG ${tg} は自動復帰の対象外です。"
            fi
            
        elif echo "$line" | grep -q "Slot ${WATCH_SLOT}," && echo "$line" | grep -q "voice header"; then
            cancel_pending_restore
        fi
    fi
done
