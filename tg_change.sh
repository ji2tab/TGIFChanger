#!/bin/bash
# =============================================================================
# tg_change.sh - TGIF Talk Group Changer
# -----------------------------------------------------------------------------
# DMRGateway / MMDVMHost の設定から DMR ID を自動取得し、
# TGIF Network の API を呼び出して指定スロットの TG を即時変更する。
#
# Usage:
#   tg_change -<TG番号>           # スロット1
#   tg_change -<TG番号>:<スロット>  # スロット指定
#   tg_change -h | --help         # ヘルプ
# =============================================================================

VERSION="proto-1.1.0"
CONF_FILE="/etc/tgifchanger.conf"

# --- 設定読込 (デフォルト値) ------------------------------------------------
TGIF_API="http://tgif.network:5040/api/sessions/update"
TGIF_API_TIMEOUT="10"

# 設定ファイルがあれば上書き [cite: 3]
[ -f "$CONF_FILE" ] && . "$CONF_FILE"

SCRIPT_NAME=$(basename "$0")

# --- DMR ID 自動取得 -------------------------------------------------------
# 優先順位: 1) /etc/dmrgateway の [DMR Network 4] (TGIF), 2) /etc/mmdvmhost [cite: 4]
get_dmr_id() {
    local id=""

    if [ -f /etc/dmrgateway ]; then
        # TGIFネットワークセクションからIDを抽出 [cite: 4]
        id=$(sed -n '/\[DMR Network 4\]/,/^\[/p' /etc/dmrgateway \
             | grep -m 1 "^Id=" \
             | awk -F= '{print $2}' \
             | tr -d '\r ' \
             | cut -d'#' -f1)
    fi

    if [ -z "$id" ] && [ -f /etc/mmdvmhost ]; then
        # MMDVMHostの基本設定からIDを抽出 [cite: 5]
        id=$(grep -m 1 "^Id=" /etc/mmdvmhost \
             | awk -F= '{print $2}' \
             | tr -d '\r ' \
             | cut -d'#' -f1)
    fi

    echo "$id"
}

show_help() {
    cat <<EOF
$SCRIPT_NAME (TGIFChanger ${VERSION})

使用方法:
  $SCRIPT_NAME -<TG番号>           スロット1 の TG を変更
  $SCRIPT_NAME -<TG番号>:<スロット> 指定スロットの TG を変更
  $SCRIPT_NAME -h | --help         このヘルプを表示

例:
  $SCRIPT_NAME -168      # スロット1 を TG168 に変更
  $SCRIPT_NAME -168:2    # スロット2 を TG168 に変更

設定ファイル: $CONF_FILE
EOF
}

change_tg() {
    local slot=$1
    local tg=$2

    if ! [[ "$tg" =~ ^[0-9]+$ ]]; then
        echo "❌ エラー: TG番号は数字で指定してください: $tg" >&2
        return 1
    fi

    if ! [[ "$slot" =~ ^[12]$ ]]; then
        echo "❌ エラー: スロットは 1 または 2 を指定してください: $slot" >&2
        return 1
    fi

    # TGIF API は slot を 0-indexed (0=Slot1, 1=Slot2) で受け付ける [cite: 10]
    local slot_idx=$((slot - 1))
    local api_url="${TGIF_API}/${DMR_ID}/${slot_idx}/${tg}"

    echo "Changing Slot ${slot} to TG ${tg} (DMR ID: ${DMR_ID})..."

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
               --max-time "$TGIF_API_TIMEOUT" "$api_url")
    local curl_rc=$?

    if [ $curl_rc -ne 0 ]; then
        echo "❌ エラー: TGIF API への通信に失敗しました (curl exit=$curl_rc)" >&2
        return 1
    fi

    if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
        echo "✅ TG変更リクエスト送信完了 (HTTP $http_code)"
        return 0
    else
        echo "⚠️  HTTP $http_code が返却されました (API側の状態を確認してください)" >&2
        return 1
    fi
}

# --- メイン ------------------------------------------------------------------
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# ヘルプ引数の先行チェック [cite: 14, 16]
for arg in "$@"; do
    case "$arg" in
        -h|--help) show_help; exit 0 ;;
    esac
done

# DMR ID 取得
DMR_ID=$(get_dmr_id)
if [ -z "$DMR_ID" ]; then
    echo "❌ エラー: DMR ID を取得できませんでした。" >&2
    echo "   /etc/dmrgateway または /etc/mmdvmhost を確認してください。" >&2
    exit 1
fi

exit_code=0
for arg in "$@"; do
    case "$arg" in
        -[0-9]*)
            target="${arg#-}"
            tg="${target%:*}"
            slot="${target##*:}"
            # ":" が無い場合はデフォルトスロット1として扱う [cite: 17]
            [ "$slot" = "$tg" ] && slot=1
            change_tg "$slot" "$tg" || exit_code=1
            ;;
        *)
            echo "❌ 不明な引数: $arg" >&2
            show_help
            exit 1
            ;;
    esac
done

exit $exit_code