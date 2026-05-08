#!/bin/bash
# =============================================================================
# log_monitor.sh - MMDVM to GPIO Bridge (Optimized for WPSD/Pi-Star)
# -----------------------------------------------------------------------------
# MMDVMHost ログをリアルタイム監視し、指定 TG の受信状態を
# Raspberry Pi の GPIO 出力ピンに反映するブリッジ。
#
# 特徴:
#   - libgpiod v1 / v2 を自動判別し、最適なコマンドを選択
#   - フィーチャー検知 (--mode wait) により OS 世代を問わず動作
#   - 自局コールサインの自動同期によるループ防止
# =============================================================================

VERSION="proto-1.1.0"
CONF_FILE="/etc/tgifchanger.conf"
MMDVM_CONF="/etc/mmdvmhost"

# --- 設定読込 (デフォルト値) ------------------------------------------------
LOG_DIR="/var/log/pi-star"
WATCH_SLOT="2"
WATCH_TG="1"
GPIO_PIN="17"
GPIO_BACKEND="auto"
GPIO_CHIP="auto"

[ -f "$CONF_FILE" ] && . "$CONF_FILE"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# --- 自局コールサイン自動取得 -----------------------------------------------
get_my_callsign() {
    local call=""
    if [ -f "$MMDVM_CONF" ]; then
        call=$(grep "^Callsign=" "$MMDVM_CONF" | awk -F= '{print $2}' | tr -d '\r ' | tr '[:lower:]' '[:upper:]')
    fi
    echo "$call"
}

MY_CALL=$(get_my_callsign)
[ -z "$MY_CALL" ] \
    && log "⚠️  自局コールサイン取得失敗。ループ防止が動作しません。" \
    || log "🆔 自局: $MY_CALL (自送信は無視)"

# --- GPIO バックエンド & バージョン検出 --------------------------------------
detect_gpio_backend() {
    case "$GPIO_BACKEND" in
        libgpiod)
            command -v gpioset >/dev/null 2>&1 || { log "❌ gpioset が見つかりません。"; exit 1; }
            GPIO_MODE="libgpiod" ;;
        sysfs)
            GPIO_MODE="sysfs" ;;
        *)
            command -v gpioset >/dev/null 2>&1 && GPIO_MODE="libgpiod" || GPIO_MODE="sysfs" ;;
    esac
}

detect_libgpiod_features() {
    [ "$GPIO_MODE" != "libgpiod" ] && return
    
    # チップ検出
    if [ "$GPIO_CHIP" = "auto" ]; then
        local chip
        chip=$(gpiodetect 2>/dev/null | grep -E 'pinctrl|bcm' | head -1 | awk '{print $1}')
        GPIO_CHIP="${chip:-gpiochip0}"
    fi

    # フィーチャー検知: wait オプションがあるか
    if gpioset --help 2>&1 | grep -q "wait"; then
        LIBGPIOD_VERSION=2
    else
        LIBGPIOD_VERSION=1
    fi
}

# --- GPIO 制御 --------------------------------------------------------------
GPIO_STATE=-1
GPIOSET_PID=""

set_gpio() {
    local val=$1
    [ "$val" = "$GPIO_STATE" ] && return

    # 既存の保持プロセスがあれば停止 (v1/v2共通)
    if [ -n "$GPIOSET_PID" ] && kill -0 "$GPIOSET_PID" 2>/dev/null; then
        kill "$GPIOSET_PID" 2>/dev/null
        wait "$GPIOSET_PID" 2>/dev/null
        GPIOSET_PID=""
    fi

    case "$GPIO_MODE" in
        sysfs)
            echo "$val" > "/sys/class/gpio/gpio${GPIO_PIN}/value" 2>/dev/null
            ;;
        libgpiod)
            if [ "$val" = "1" ]; then
                if [ "$LIBGPIOD_VERSION" -eq 2 ]; then
                    # v2 (Modern): --mode wait でプロセスを維持
                    gpioset -c "$GPIO_CHIP" "${GPIO_PIN}=1" --mode wait &
                else
                    # v1 (Legacy): バックグラウンド実行で維持
                    gpioset "$GPIO_CHIP" "${GPIO_PIN}=1" &
                fi
                GPIOSET_PID=$!
            else
                # LOW 設定
                if [ "$LIBGPIOD_VERSION" -eq 2 ]; then
                    gpioset -c "$GPIO_CHIP" "${GPIO_PIN}=0" 2>/dev/null
                else
                    gpioset "$GPIO_CHIP" "${GPIO_PIN}=0" 2>/dev/null
                fi
            fi
            ;;
    esac
    GPIO_STATE=$val
}

cleanup() {
    log "⚠️  停止シグナル受信。GPIO をリセットします。"
    [ -n "$GPIOSET_PID" ] && kill "$GPIOSET_PID" 2>/dev/null
    set_gpio 0
    [ "$GPIO_MODE" = "sysfs" ] && echo "${GPIO_PIN}" > /sys/class/gpio/unexport 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# --- 起動処理 ---------------------------------------------------------------
[ ! -d "$LOG_DIR" ] && { log "❌ ログディレクトリが見つかりません: $LOG_DIR"; exit 1; }

detect_gpio_backend
detect_libgpiod_features

if [ "$GPIO_MODE" = "sysfs" ]; then
    [ ! -d "/sys/class/gpio/gpio${GPIO_PIN}" ] \
        && echo "${GPIO_PIN}" > /sys/class/gpio/export 2>/dev/null
    sleep 0.1
    echo out > "/sys/class/gpio/gpio${GPIO_PIN}/direction" 2>/dev/null
    echo 0   > "/sys/class/gpio/gpio${GPIO_PIN}/value"     2>/dev/null
fi

log "🚀 log_monitor.sh (${VERSION}) Active"
log "   WATCH_SLOT=${WATCH_SLOT}  WATCH_TG=${WATCH_TG}"
log "   GPIO=${GPIO_PIN}  MODE=${GPIO_MODE} (v${LIBGPIOD_VERSION:-sysfs})  CHIP=${GPIO_CHIP}"

# --- ログ監視メインループ ---------------------------------------------------
get_latest_log() { ls -t "${LOG_DIR}"/MMDVM-*.log 2>/dev/null | head -1; }

start_tail() {
    local f=$1
    [ -n "$tail_pid" ] && kill "$tail_pid" 2>/dev/null
    log "📖 監視開始: $(basename "$f")"
    exec 3< <(tail -n 0 -F "$f" 2>/dev/null)
    tail_pid=$!
}

current_file=$(get_latest_log)
while [ -z "$current_file" ]; do
    log "ログ待機中..."
    sleep 5
    current_file=$(get_latest_log)
done
start_tail "$current_file"

while :; do
    if read -r -t 5 line <&3; then
        # ターゲットスロットの判定
        echo "$line" | grep -q "Slot ${WATCH_SLOT}," || continue

        # 受信開始判定
        if echo "$line" | grep -q "voice header"; then
            # コールサイン抽出 (WPSD/Pi-Star 両対応)
            from_call=$(echo "$line" | grep -oP 'from \K[^ ]+' | tr '[:lower:]' '[:upper:]')
            
            # 自局スキップ
            [ -n "$MY_CALL" ] && [ "$from_call" = "$MY_CALL" ] \
                && { log "[  SKIP  ] Self ($from_call)"; continue; }

            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [ "$tg" = "$WATCH_TG" ]; then
                set_gpio 1
                log "[ RECEIVING ] TG${tg} | From: ${from_call} | GPIO${GPIO_PIN}: HIGH"
            fi

        # 受信終了判定
        elif echo "$line" | grep -q "end of voice transmission"; then
            tg=$(echo "$line" | grep -oP 'to TG \K[0-9]+')
            if [ "$tg" = "$WATCH_TG" ]; then
                set_gpio 0
                log "[    IDLE    ] TG${tg} | GPIO${GPIO_PIN}: LOW"
            fi
        fi
    else
        # ログ切替チェック
        latest=$(get_latest_log)
        if [ -n "$latest" ] && [ "$latest" != "$current_file" ]; then
            log "📅 ログ切替: $(basename "$latest")"
            current_file="$latest"
            set_gpio 0
            start_tail "$current_file"
        fi
    fi
done