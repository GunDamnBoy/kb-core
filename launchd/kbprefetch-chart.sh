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

PY="$HOME/.venvs/kb/bin/python"
LOG="$HOME/.chartfetch/prefetch.log"
mkdir -p "$(dirname "$LOG")"

# 日誌只留最後 2000 行，免得長期跑下來吃掉磁碟
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 開始預抓（CHART_REPO=$CHART_REPO） ===" >> "$LOG"
"$PY" "$HOME/kb-core/scripts/chart/prefetch.py" --quiet >> "$LOG" 2>&1
rc=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 結束，exit=$rc ===" >> "$LOG"
exit $rc
