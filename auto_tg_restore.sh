#!/bin/bash
# =============================================================================
# auto_tg_restore.sh - TGIF Auto TG Restore Daemon
# -----------------------------------------------------------------------------
VERSION="proto-1.1.2"
CONF_FILE="/etc/tgifchanger.conf"
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
RESTORE_DELAY="120"
RESTORE_TG="168"
RESTORE_SLOT="2"

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
TG_CHANGE_CMD="${SCRIPT_DIR}/tg_change.sh"
RESTORE_PID_FILE="/run/auto_tg_restore.pid"
LOCK_FILE="/run/auto_tg_restore.lock"

if [ ! -d /run ]; then
    RESTORE_PID_FILE="/tmp/auto_tg_restore.pid"
    LOCK_FILE="/tmp/auto_tg_restore.lock"
fi

log() { echo "[$(date '+%H:%M:%S')] $*"; }

if [ ! -x "$TG_CHANGE_CMD" ]; then
    log "❌ エラー: $TG_CHANGE_CMD が見つかりません。"
    exit 1
fi

if [ ! -d "$LOG_DIR" ]; then
    log "❌ エラー: ログディレクトリが見つかりません: $LOG_DIR"
    exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "⚠️  既に auto_tg_restore.sh が起動しています。"
    exit 1
fi

get_latest_log() {
    ls -t "${LOG_DIR}"/MMDVM-*.log 2>/dev/null | head -1
}

cancel_pending_restore() {
    if [ -f "$RESTORE_PID_FILE" ]; then
        local pid
        pid=$(cat "$RESTORE_PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for _ in {1..10}; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.1
            done
            kill -9 "$pid" 2>/dev/null 2>/dev/null
        fi
        rm -f "$RESTORE_PID_FILE"
    fi
}

schedule_restore() {
    local prev_tg=$1
    cancel_pending_restore
    log "[END] TG ${prev_tg} | ${RESTORE_DELAY}秒後に TG${RESTORE_TG} へ復帰します..."

    (
        sleep "$RESTORE_DELAY"
        log "🔄 TG ${RESTORE_TG} に自動復帰中..."
        "$TG_CHANGE_CMD" "-${RESTORE_TG}:${RESTORE_SLOT}"
        rm -f "$RESTORE_PID_FILE"
    ) &
    echo $! > "$RESTORE_PID_FILE"
}

cleanup() {
    log "⚠️  停止シグナルを受信しました。クリーンアップ中..."
    cancel_pending_restore
    exit 0
}

trap cleanup SIGINT SIGTERM

log "🚀 auto_tg_restore.sh (${VERSION}) Active"
log "   WATCH_SLOT=${WATCH_SLOT}  HOME=TG${RESTORE_TG}/Slot${RESTORE_SLOT}  DELAY=${RESTORE_DELAY}s"

current_file=""
tail_pid=""

start_tail() {
    local f=$1
    if [ -n "$tail_pid" ] && kill -0 "$tail_pid" 2>/dev/null; then
        kill "$tail_pid" 2>/dev/null
        wait "$tail_pid" 2>/dev/null
    fi
    log "📖 監視開始: $(basename "$f")"
    exec 3< <(tail -n 0 -F "$f" 2>/dev/null)
    tail_pid=$!
}

while :; do
    current_file=$(get_latest_log)
    [ -n "$current_file" ] && break
    log "ログファイル待機中..."
    sleep 5
done
start_tail "$current_file"

while :; do
    if read -r -t 5 line <&3; then
        if echo "$line" | grep -q "Slot ${WATCH_SLOT}," && echo "$line" | grep -q "end of voice transmission"; then
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [[ "$tg" =~ ^[0-9]+$ ]] && [ "$tg" != "$RESTORE_TG" ]; then
                schedule_restore "$tg"
            fi
        elif echo "$line" | grep -q "Slot ${WATCH_SLOT}," && echo "$line" | grep -q "voice header"; then
            cancel_pending_restore
        fi
    else
        latest=$(get_latest_log)
        if [ -n "$latest" ] && [ "$latest" != "$current_file" ]; then
            log "📅 ログ切り替わり検出: $(basename "$latest")"
            current_file="$latest"
            start_tail "$current_file"
        fi
    fi
done
