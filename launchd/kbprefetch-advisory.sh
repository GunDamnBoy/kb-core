#!/bin/bash
# 投顧知識庫 · 保底層預抓 —— launchd 呼叫的包裝腳本。
#
# ## 它解的是一個時序問題，不是一個「沒人拉」的問題
#
# 保底層由 GitHub Actions 在台北約 07:00 產出並推上 origin 的 `raw/<date>.json`。
# 本機的 `~/advisory-rewrite` 確實會拿到它 —— 但要等到 `com.kenny.kbpublish`
# 下一次發布時 `pull --rebase` 才拉下來。而執行輪次是 07:30／07:35 開跑，
# **發布是那一輪的最後一步**（2026-08-23 實測：raw 的 mtime 09:31 ＝ 當輪回執時刻）。
#
# 於是每天早上都是同一個形狀：**輪次開跑時，本機最新的 raw 是昨天的。**
# 2026-08-23 那一輪因此花了約 4 分鐘、6 次工具呼叫用 Chrome 去讀
# `raw.githubusercontent.com`，而且那不是意外——SKILL 的步驟 1 把它寫成了常態路徑。
#
# ## 為什麼不跑 git
#
# `com.kenny.kbpublish` 每 60 秒跑一次，**任何 git 指令留下的 `index.lock` 都會擋住它**。
# 一支每天 07:20 跑的 `git pull` 有機會正好壓在發布上面，而那一次的症狀是發布失敗，
# 不是預抓失敗 —— 錯的地方會叫，出錯的地方不會。
# 所以這支只用 curl 抓一個檔到 repo 外面的快取目錄，
# **與 `kbprefetch-chart.sh` 同一個紀律：預抓不碰 git，變動由 publish 那條線帶。**
#
# ## 消費端
#
# `skills/advisory/SKILL.md` 步驟 1 先看 `~/.advisoryfetch/raw/<今天>.json`，
# 取不到才退回本機 repo，再取不到才用 Chrome。三層都在那張表上。
set -o pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/macmini"

RAW_BASE="https://raw.githubusercontent.com/GunDamnBoy/advisory-rewrite/main/raw"
CACHE="$HOME/.advisoryfetch/raw"
LOG="$HOME/.advisoryfetch/prefetch.log"
TODAY="$(date '+%Y-%m-%d')"
DEST="$CACHE/$TODAY.json"

mkdir -p "$CACHE"

# 日誌只留最後 2000 行
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "=== 開始預抓 $TODAY ==="

if [ -f "$DEST" ]; then
  # 變數一律用 ${} 包起來：後面接全形標點時，`$DEST，` 會被 bash 當成變數名
  # `DEST，` 而展開成空字串 —— 2026-08-23 首次實跑就是這樣把路徑印丟了。
  log "已經有 ${DEST}，不重抓（要重抓就先刪掉它）"
  exit 0
fi

# Actions 可能晚到。重試三次、間隔兩分鐘 —— 07:20 起算最晚 07:24 收工，
# 仍早於 07:30／07:35 的輪次。**再晚就不等了**：等下去會把輪次一起拖慢，
# 而輪次本來就有 Chrome 那條退路。
TMP="$CACHE/.$TODAY.partial"
rc=1
for attempt in 1 2 3; do
  # `?cb=` 是 CDN 快取穿透 —— raw.githubusercontent 會回舊內容長達數分鐘，
  # 而「拿到的是幾分鐘前的空檔案」與「Actions 還沒跑」長得一模一樣。
  if curl -fsS --max-time 60 -o "$TMP" "$RAW_BASE/$TODAY.json?cb=$(date +%s)"; then
    rc=0
    break
  fi
  log "第 $attempt 次失敗（Actions 可能還沒推），120 秒後重試"
  sleep 120
done

if [ "$rc" -ne 0 ]; then
  log "三次都抓不到 $TODAY.json —— 這一輪放棄，輪次會退回 Chrome 那條路"
  log "=== 結束，exit=14 ==="
  exit 14        # ENVIRONMENT：對外抓不到，不是資料壞了
fi

# **抓到檔案不等於抓到今天的檔案。** Actions 若失敗、或 CDN 給了舊物件，
# 這裡拿到的可能是一份 `date` 不對或 `failed_essential` 非空的東西 ——
# 而那兩種情況輪次都必須知道，不能讓它以為保底層正常。
read -r ok_flag summary < <(
  /usr/bin/python3 - "$TMP" "$TODAY" <<'PY'
import json, sys
path, today = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path))
except Exception as e:
    print(f"0 讀不開（{type(e).__name__}）")
    raise SystemExit
date = d.get("date")
fetched = d.get("fetched_at")
fail = d.get("failed_essential") or []
items = len(d.get("items") or {})
if date != today:
    print(f"0 檔案的date是{date}、不是{today}（Actions未跑或CDN給了舊物件）")
elif fail:
    print(f"0 failed_essential非空：{','.join(fail)}")
else:
    print(f"1 date={date}·fetched_at={fetched}·items={items}·failed_essential=空")
PY
)

if [ "$ok_flag" != "1" ]; then
  log "抓到了但不可用：$summary"
  rm -f "$TMP"
  log "=== 結束，exit=10 ==="
  exit 10        # 內容不合格 —— 與 publish 的 exit 10 同義
fi

# 原子寫入：輪次可能正好在讀這個目錄。
mv "$TMP" "$DEST"
log "落地 ${DEST}（$(wc -c < "$DEST") bytes）：${summary}"
log "=== 結束，exit=0 ==="
exit 0
