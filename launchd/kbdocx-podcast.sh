#!/bin/bash
# 從**已發布的**當日 JSON 產出 Word 報告。
#
# 為什麼這件事從排程的 LLM 輪次搬出來：
#   `podcast_docx.py` 全程不需要 LLM —— 它只是排版，一個字都不改。
#   放在日報那一輪等於為了一段純機械的工作，多掛一個資料夾依賴
#   （`~/Documents/podcast-reports` 得連進工作階段），而 2026-08-21 那一輪
#   就是因為那個掛載請求被中斷、**發布 exit 0、Word 卻沒有**。
#
#   逐字稿與 Word 檔留在所有 repo 外面是結構性的界線，不是 .gitignore ——
#   而「不必連進任何 LLM 工作階段」讓那條界線又厚了一層。
#
# **順序是刻意的：先發布，後轉檔。** 只有真的上線的內容才會變成 Word，
# 不會出現「Word 有這集、網站沒有」。所以這裡先問回執，不問草稿。
set -o pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/macmini"
export PYTHONUNBUFFERED=1

PY="$HOME/.venvs/kb/bin/python"
REPO="$HOME/podcast-knowledge-digest"
OUT="$HOME/Documents/podcast-reports"
DATE="${1:-$(date '+%Y-%m-%d')}"
RECEIPT="$HOME/outbox/podcast/$DATE.receipt.json"

echo "──────── $(date '+%Y-%m-%d %H:%M:%S') kbdocx.podcast $DATE"

if [ ! -f "$RECEIPT" ]; then
  echo "沒有 $DATE 的回執 —— 那一輪還沒發布，Word 不該先於網站存在。空輪次，不是失敗。"
  exit 13        # EMPTY_ROUND
fi

# 回執存在不等於發布成功。**exit 非 0 的那一天不該有 Word。**
rc=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1])).get('exit',99))" "$RECEIPT" 2>/dev/null)
# **「讀不到」與「讀到了但不是 0」是兩件事**，訊息要說得出是哪一種 ——
# 前者是環境壞了（python 不在、回執不是合法 JSON），後者是那一輪真的沒發成功。
if [ -z "$rc" ]; then
  echo "讀不出 $RECEIPT 的 exit —— python 不在或回執不是合法 JSON。**這是環境問題，不是那一輪失敗。**"
  exit 14        # ENVIRONMENT
fi
if [ "$rc" != "0" ]; then
  echo "回執 exit=$rc —— 那一輪沒有成功發布，不轉檔。"
  exit 13
fi

# 冪等：日檔沒有比既有的 Word 新就不做。手動重跑安全，排程重跑也不會每天重寫一份。
SRC="$REPO/data/$DATE.json"
DST="$OUT/podcast-$DATE.docx"
if [ -f "$DST" ] && [ ! "$SRC" -nt "$DST" ]; then
  echo "$DST 已是最新（日檔沒有更動），跳過。"
  exit 0
fi

"$PY" "$HOME/kb-core/tools/podcast_docx.py" "$REPO" "$DATE" "$OUT"
