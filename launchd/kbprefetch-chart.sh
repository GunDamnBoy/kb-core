#!/bin/bash
# 每日五圖 · 序列預抓 —— launchd 呼叫的包裝腳本。
#
# 舊版住在 chart-of-the-day/tools/prefetch-launchd.sh，跑的是資料 repo 裡的
# tools/prefetch.py，並且**假設 cwd 就是 repo**。2026-08-20 程式搬進 kb-core 之後
# 那個假設不再成立 —— 現在 repo 是明確傳進去的（CHART_REPO），
# **這裡刻意不猜**：猜錯的樣子是「抓到了、寫進另一個目錄」，而那一輪看起來會是成功的。
#
# 為什麼要有包裝而不是讓 launchd 直接跑 python：
#   1. launchd 的環境變數極少，PATH 與 HOME 要自己給（FRED／Tiingo 金鑰在 ~/.config 底下）
#   2. 要把 stdout/stderr 導進日誌，否則失敗是靜默的
#   3. 要記錄每次的起訖時間 —— 「今天到底有沒有跑」是狀態檔以外的第二個證據
#
# **這支不跑任何 git 指令。** 快取的變動由 publish 那條線帶上去。
set -o pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/macmini"
export CHART_REPO="$HOME/chart-of-the-day"
# 輸出走 `| tee`，於是 python 的 stdout 是管道而不是終端機 —— 預設會從行緩衝
# 變成區塊緩衝，要積滿好幾 KB 才吐一次。**逐條進度照印，只是看不到。**
# 2026-08-20 第二次手動驗證就栽在這裡：我剛拿掉 --quiet，症狀卻跟沒拿掉一模一樣。
export PYTHONUNBUFFERED=1

PY="$HOME/.venvs/kb/bin/python"
LOG="$HOME/.chartfetch/prefetch.log"
mkdir -p "$(dirname "$LOG")"

# 日誌只留最後 2000 行，免得長期跑下來吃掉磁碟
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 開始預抓（CHART_REPO=$CHART_REPO） ===" >> "$LOG"

# ── 起飛前先問金鑰 ──────────────────────────────────────────────
# 沒有 FRED key 的樣子**不是報錯，是沉默 20 分鐘**：沒 key 就退到 fredgraph，
# 而那條路在這台機器上本來就不通（SOURCES.md，Errno 60），於是 46 條各自逾時 30 秒、
# 一條快取都不會寫，最後才印一行摘要說全部失敗。**這個問題要在兩秒內問完。**
#
# 刻意只問「讀不讀得到」而不打網路：key 錯的話 FRED 回 400 很快，
# 不會有那 20 分鐘；真正會拖死的只有「根本沒有 key」這一種。
# 想連帶驗它能不能用，手動跑 `fetch.py --check-key`（那支會打三個端點，比較慢）。
if ! "$PY" -c "import sys;sys.path.insert(0,'$HOME/kb-core/scripts/chart');import fetch;sys.exit(0 if fetch.fred_key() else 1)" 2>>"$LOG"; then
  { echo "!!! 找不到 FRED API key（FRED_API_KEY 或 ~/.config/fred/api_key）—— 這一輪不跑。"
    echo "    沒有 key 會退到 fredgraph，而那條路在這台機器上不通，"
    echo "    結果會是安靜跑二十分鐘然後全部失敗。"; } | tee -a "$LOG"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 中止，exit=14 ===" >> "$LOG"
  exit 14        # ENVIRONMENT：環境的問題，不是資料的問題
fi

# 人在看的時候要逐條印，launchd 在看的時候只印摘要。
# **沉默同時符合「跑得好」與「全部失敗」**，而手動跑的人分不出來 ——
# 2026-08-20 首次手動驗證就卡在這裡，看起來像當掉。
if [ -t 1 ]; then QUIET=""; else QUIET="--quiet"; fi

"$PY" "$HOME/kb-core/scripts/chart/prefetch.py" $QUIET 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}      # 要的是 prefetch 的退出碼，不是 tee 的
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 結束，exit=$rc ===" >> "$LOG"
exit $rc
