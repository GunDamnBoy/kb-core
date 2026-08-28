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
#
# ## 2026-08-28 改了兩件事，各自解掉一個實測到的失效
#
# ### ① 快取搬到 `~/outbox/floor/`，因為輪次讀不到 `~/.advisoryfetch/`
#
# 舊路徑在使用者的連接資料夾之外，Cowork 的輪次 `Read`／`Grep`／`Bash` 三個都
# 碰不到它（`Glob` 看得到檔名、讀不了內容）。2026-08-24 與 08-28 兩輪實測：
# **檔案在、內容拿不到**，於是第①層形同虛設、每一輪都退到 Chrome 那條路。
# 「看得到檔名」與「讀得到內容」長得很像，而錯的那一邊不會叫。
#
# `~/outbox` 本來就是連接資料夾。放 `floor/` 子目錄不會撞到任何人：
# `publish.py` 只掃根目錄的 `*.draft.json`，`kbusage.sh` 只掃 `*.usage.json`
# 與 `*/*.usage.json` —— 這裡放的是 `<date>.json`，兩邊都看不到。
# 日誌也一起搬進來：**輪次現在讀得到預抓失敗的理由，而昨天讀不到。**
#
# ### ② curl 抓不到時改在 Mac 本機自取，因為 GitHub 排程開始漏跑
#
# 2026-08-28 拉 fetch-floor 的 14 筆歷史：08-19 到 08-25 的七次排程班延後全部
# 落在 **16–21 分鐘**，非常穩定；**08-26 那一班整班沒有出現**（序列直接跳到
# 08-27T04:00Z，延後 317 分），**08-27 那一班也沒有出現**，連續第二天。
#
# **這是漏跑，不是延後 —— 而把 cron 提前對漏跑沒有任何幫助。**
# （這一句是更正：08-28 早上那一輪的執行報告寫的建議是「把 cron 提前
# 60–90 分鐘」，那是只看了兩筆就下的診斷。錯的診斷會變成錯的待修事項。）
#
# Mac 這一端其實什麼都有：有網路、有 `~/.venvs/kb`、有 `~/.config/fred/api_key`
# （五圖那套在用），而 `tools/fetch_advisory.py` 吃的是任意輸出目錄。
# 所以三次 curl 失敗之後直接在本機跑同一支取數程式 ——
# **保底層從此不依賴 GitHub 的排程器。**
#
# 本機自取的檔會被標上 `"produced_by": "mac-local"`。這不是裝飾：
# 沒有這個欄位，「Actions 正常」與「Actions 掛了但本機補上了」在下游眼裡
# 一模一樣，於是漏跑會被自己的備援藏起來，直到備援也壞掉那天才爆。
#
# ## 為什麼不跑 git
#
# `com.kenny.kbpublish` 每 60 秒跑一次，**任何 git 指令留下的 `index.lock` 都會擋住它**。
# 一支每天 07:20 跑的 `git pull` 有機會正好壓在發布上面，而那一次的症狀是發布失敗，
# 不是預抓失敗 —— 錯的地方會叫，出錯的地方不會。
# 所以這支只用 curl（或本機取數）寫一個檔到 repo 外面的目錄，
# **與 `kbprefetch-chart.sh` 同一個紀律：預抓不碰 git，變動由 publish 那條線帶。**
#
# ## 消費端
#
# `skills/advisory/SKILL.md` 步驟 1 先看 `~/outbox/floor/<今天>.json`，
# 取不到才退回本機 repo，再取不到才用 Chrome。三層都在那張表上。
set -o pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/macmini"

RAW_BASE="https://raw.githubusercontent.com/GunDamnBoy/advisory-rewrite/main/raw"
CACHE="$HOME/outbox/floor"
LOG="$CACHE/prefetch.log"
TODAY="$(date '+%Y-%m-%d')"
DEST="$CACHE/$TODAY.json"

# 本機自取要用到的三樣東西。三個都是絕對路徑，與 PATH 無關 ——
# `watch.external_binaries` 讀的是 plist，而 plist 只需要宣告 curl。
VENV_PY="$HOME/.venvs/kb/bin/python"
FETCHER="$HOME/kb-core/tools/fetch_advisory.py"
FRED_KEYFILE="$HOME/.config/fred/api_key"

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

TMP="$CACHE/.$TODAY.partial"
SOURCE="actions"

# ---------------------------------------------------------------- 第一條路：origin
# Actions 可能晚到。重試三次、間隔兩分鐘 —— 07:20 起算最晚 07:24 收工，
# 仍早於 07:30／07:35 的輪次。**再晚就不等了**：等下去會把輪次一起拖慢。
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

# ------------------------------------------------- 第二條路：在這台機器上自己抓
#
# 走到這裡代表 origin 上今天的 raw 不存在。以前的做法是放棄、讓輪次退回 Chrome；
# 但 08-26 與 08-27 連兩天漏跑之後，「退回 Chrome」變成了常態而不是例外，
# 而 Chrome 那條路每次要約 4 分鐘、6 次工具呼叫，還拿不到台股盤後那幾個端點
# （它們在輪次開跑時本來就還沒收盤，Actions 那一班也一樣拿不到）。
if [ "$rc" -ne 0 ]; then
  log "三次都抓不到 ${TODAY}.json —— 改用本機自取"
  SOURCE="mac-local"
  rc=1

  if [ ! -x "$VENV_PY" ]; then
    log "本機自取放棄：找不到可執行的 ${VENV_PY}"
  elif [ ! -f "$FETCHER" ]; then
    log "本機自取放棄：找不到 ${FETCHER}"
  elif [ ! -s "$FRED_KEYFILE" ]; then
    # **金鑰缺席要說出來。** 沒有它 FRED 那兩條會 AuthFailed，
    # 而 FRED 兩條都在 ESSENTIAL 裡，整份 raw 會被下面的驗證擋掉 ——
    # 症狀會長得像「本機自取也不行」，而真正的原因只是少一個檔案。
    log "本機自取放棄：找不到 FRED 金鑰（${FRED_KEYFILE}）—— 用 setup-keys.sh 補"
  else
    # 金鑰前後空白一律剃掉：多一個字元不會報「格式錯」，只會回 400，
    # 而那看起來像「這把 key 沒有權限」。同 setup-keys.sh 的理由。
    FRED_API_KEY="$(tr -d '[:space:]' < "$FRED_KEYFILE")"
    export FRED_API_KEY
    WORK="$CACHE/.local.$$"
    mkdir -p "$WORK"
    log "本機自取開始：$VENV_PY $FETCHER $WORK"
    "$VENV_PY" "$FETCHER" "$WORK" >> "$LOG" 2>&1
    frc=$?
    if [ -f "$WORK/$TODAY.json" ]; then
      # **檔案有沒有落地，跟退出碼是兩件事。** fetch_advisory 在「必要項失敗」時
      # 回 14 但檔案照樣寫出來（失敗理由具名寫在裡面），那正是下面驗證要讀的東西。
      mv "$WORK/$TODAY.json" "$TMP"
      rc=0
      log "本機自取結束（fetch_advisory 退出碼 $frc），檔案已落地待驗"
    else
      log "本機自取沒有產出 ${TODAY}.json（退出碼 $frc）"
    fi
    unset FRED_API_KEY
    rm -rf "$WORK"
  fi
fi

if [ "$rc" -ne 0 ]; then
  log "兩條路都拿不到 $TODAY.json —— 這一輪放棄，輪次會退回本機 repo 或 Chrome"
  log "=== 結束，exit=14 ==="
  exit 14        # ENVIRONMENT：對外抓不到，不是資料壞了
fi

# **抓到檔案不等於抓到今天的檔案。** Actions 若失敗、或 CDN 給了舊物件，
# 這裡拿到的可能是一份 `date` 不對或 `failed_essential` 非空的東西 ——
# 而那兩種情況輪次都必須知道，不能讓它以為保底層正常。
# 本機自取的檔走的是同一條驗證，刻意不給它另一套標準。
read -r ok_flag summary < <(
  /usr/bin/python3 - "$TMP" "$TODAY" "$SOURCE" <<'PY'
import json, sys
path, today, source = sys.argv[1], sys.argv[2], sys.argv[3]
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
    # 來源標記寫回檔案裡。**沒有它，「Actions 正常」與「Actions 漏跑但本機補上了」
    # 在下游眼裡一模一樣** —— 備援會把它要回報的那個故障藏起來。
    d["produced_by"] = source
    json.dump(d, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"1 date={date}·produced_by={source}·fetched_at={fetched}"
          f"·items={items}·failed_essential=空")
PY
)

if [ "$ok_flag" != "1" ]; then
  log "抓到了但不可用（來源 ${SOURCE}）：$summary"
  rm -f "$TMP"
  log "=== 結束，exit=10 ==="
  exit 10        # 內容不合格 —— 與 publish 的 exit 10 同義
fi

# 原子寫入：輪次可能正好在讀這個目錄。
mv "$TMP" "$DEST"
log "落地 ${DEST}（$(wc -c < "$DEST") bytes）：${summary}"
log "=== 結束，exit=0 ==="
exit 0
