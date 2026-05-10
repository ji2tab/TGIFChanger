#!/bin/bash
# =============================================================================
# TGIFChanger - Auto TG Restore Daemon
# 
# File:        auto_tg_restore.sh
# Version:     v1.2.4
# Author:      Kazuhiko Shinoda (JI2TAB)
# Description: Monitors MMDVM logs to detect the end of voice transmissions.
#              Automatically restores the connection to the designated Home TG
#              after a specified delay. Optimized for Pi-Star and WPSD.
#              (v1.2.4: Prioritizes explicit config over auto-detection)
# License:     GPL v3
# =============================================================================

VERSION="v1.2.4"
CONF_FILE="/etc/tgifchanger.conf"
MMDVM_CONF="/etc/mmdvmhost"
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_DELAY="120"
RESTORE_SLOT="2"

# 初期値として空にしておく
WATCH_TG=""
RESTORE_TG=""

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
TG_CHANGE_CMD="${SCRIPT_DIR}/tg_change.sh"
RESTORE_PID_FILE="/run/auto_tg_restore.pid"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

get_dynamic_tgs() {
    # 1. tgifchanger.confで両方設定されていれば、それを最優先する
    if [ -n "$WATCH_TG" ] && [ -n "$RESTORE_TG" ]; then
        return
    fi

    # 2. 設定ファイルに無い場合のみ、mmdvmhost から抽出を試みる
    if [ -f "$MMDVM_CONF" ]; then
        local rewrite_line=$(awk '
            /^\[DMR Network / { in_dmr=1; is_tgif=0; next }
            /^\[/ { in_dmr=0 }
            in_dmr && /Address=tgif\.network/ { is_tgif=1 }
            in_dmr && is_tgif && /^TGRewrite/ { print; exit }
        ' "$MMDVM_CONF")
        if [ -n "$rewrite_line" ]; then
            local vals=$(echo "$rewrite_line" | awk -F= '{print $2}')
            [ -z "$WATCH_TG" ] && WATCH_TG=$(echo "$vals" | cut -d, -f2 | tr -dc '0-9')
            [ -z "$RESTORE_TG" ] && RESTORE_TG=$(echo "$vals" | cut -d, -f4 | tr -dc '0-9')
        fi
    fi

    # 3. それでも空っぽなら、最終フォールバック値を入れる
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
