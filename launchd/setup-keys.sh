#!/bin/bash
# 換機器之後把 FRED／Tiingo 金鑰放回位置。**貼上，不要打進指令列。**
#
# 為什麼要有這支而不是直接給一行 printf：
#   1. 寫在指令列裡的 key 會進 shell history，而那個檔案不會過期
#   2. 貼上時很容易多帶一個換行或尾隨空白，而**多一個字元的 key 不會報「格式錯」，
#      只會回 400**——看起來像「這把 key 沒有權限」，於是人去查權限而不是查空白
#   3. 寫完要立刻驗，否則「檔案存在」會被當成「金鑰可用」
#
# 用法：
#   bash ~/kb-core/launchd/setup-keys.sh           兩把都設
#   bash ~/kb-core/launchd/setup-keys.sh fred      只設 FRED
#   bash ~/kb-core/launchd/setup-keys.sh tiingo    只設 Tiingo
set -u
PY="$HOME/.venvs/kb/bin/python"
FETCH="$HOME/kb-core/scripts/chart/fetch.py"
export CHART_REPO="${CHART_REPO:-$HOME/chart-of-the-day}"

put() {                      # put <名稱> <目標路徑> <預期長度> <驗證旗標>
  local name="$1" path="$2" want="$3" flag="$4" key=""

  if [ -s "$path" ]; then
    printf '%s 已存在（%s，%s 位元組）。要覆蓋嗎？[y/N] ' \
           "$name" "$path" "$(wc -c < "$path" | tr -d ' ')"
    read -r yn
    case "$yn" in [Yy]*) ;; *) echo "  跳過 $name"; return 0;; esac
  fi

  # -s 不回顯；貼上的內容不會出現在畫面上，也不會進 history
  printf '貼上 %s API key（畫面不會顯示），然後按 Enter：' "$name"
  read -rs key
  echo

  # 前後空白與換行一律剃掉。**這是這支腳本存在的主要理由之一。**
  key="$(printf %s "$key" | tr -d '[:space:]')"
  if [ -z "$key" ]; then echo "  沒有輸入，跳過 $name"; return 0; fi

  local n=${#key}
  if [ "$n" -ne "$want" ]; then
    printf '  ⚠︎ 長度是 %s，一般的 %s key 是 %s 碼 —— 確定要寫入嗎？[y/N] ' \
           "$n" "$name" "$want"
    read -r yn
    case "$yn" in [Yy]*) ;; *) echo "  取消 $name"; return 0;; esac
  fi

  mkdir -p "$(dirname "$path")"
  printf %s "$key" > "$path" && chmod 600 "$path"
  printf '  ✓ 寫入 %s（%s 碼，開頭 %s…，不顯示全文）\n' "$path" "$n" "${key:0:4}"
  key=""

  # **寫檔成功與金鑰可用是兩件獨立的事。** 立刻打一次網路問清楚。
  echo "  ── 驗證中（會連外，慢一點是正常的）"
  "$PY" "$FETCH" "$flag" 2>&1 | sed 's/^/     /'
}

case "${1:-both}" in
  fred)   put FRED   "$HOME/.config/fred/api_key"   32 --check-key ;;
  tiingo) put Tiingo "$HOME/.config/tiingo/api_key" 40 --check-tiingo ;;
  both)   put FRED   "$HOME/.config/fred/api_key"   32 --check-key
          echo
          put Tiingo "$HOME/.config/tiingo/api_key" 40 --check-tiingo ;;
  *)      echo "用法：$0 [fred|tiingo|both]"; exit 2 ;;
esac

echo
echo "現況："
ls -l "$HOME/.config/fred/api_key" "$HOME/.config/tiingo/api_key" 2>&1
echo
echo "兩把都綠了就跑：bash ~/kb-core/launchd/kbprefetch-chart.sh"
