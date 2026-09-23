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
# **⚠️ `2>>"$LOG"` 是 2026-09-17 補的，而少了它那一次的代價是一整天的保底檔。**
# 同一支腳本另外兩處 python 呼叫本來就有 `>> "$LOG" 2>&1`，唯獨這一處沒有 ——
# 於是這段驗證只要丟出例外，traceback 就直接消失，
# 下游看到的只有一行「抓到了但不可用」而冒號後面是空的。**見下面那個 try。**
read -r ok_flag summary < <(
  /usr/bin/python3 - "$TMP" "$TODAY" "$SOURCE" 2>>"$LOG" <<'PY'
import json, os, sys
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
    #
    # **⚠️ 這個 try 是 2026-09-17 補的，而它修的是 2026-09-16 真的發生過的一次。**
    # 那天這兩行在 try 之外，而成功的 print 排在它們後面 —— 所以任何例外都會讓
    # **stdout 全空**，`read -r ok_flag summary` 兩個變數雙雙為空，
    # 外面記下一行 `抓到了但不可用（來源 actions）：` **而冒號後面什麼都沒有**，
    # 接著 exit 10 並 `rm -f` 掉那份檔。當天 origin 上那份保底檔是**完全合格**的
    # （date 對、failed_essential 空、14 個 ident 全 ok），輪次因此得改走 Chrome 讀 origin。
    #
    # **這個失效的方向是反的，這才是它真正危險的地方**：`else` 這一支只有在
    # 「date 對 ＋ failed_essential 空」時才進得來，**所以它只在保底檔完全合格時才會發生**。
    # 三個已知的失敗理由（讀不開／date 不符／failed_essential 非空）每一個都會印出具名原因，
    # **唯獨「一切正常」那條路上的例外是啞的**。
    # 2026-09-17 在 /tmp 用唯讀檔重現過，產出的日誌行與當天那一行逐字相同。
    #
    # **⚠️ 原子寫入是 2026-09-23 補的，而 2026-09-17 那一筆自己預告過這件事。**
    # 當時的收尾寫著「`json.dump` 仍不是原子寫入。例外發生在寫到一半時，檔案會是
    # 截斷的 —— 目前靠後面那句 `rm -f "$TMP"` 收掉，所以壞檔不會流到下游。
    # 沒有改成 `.tmp` ＋ rename，是因為那超出這次確認的範圍；記在這裡，
    # **下次碰這支腳本時一起處理**。」——09-23 因為補抓清單要加 FRED 而碰到它，一起處理掉。
    # **修法的範本就在同一個 repo 裡**：`tools/fetch_advisory.py` 的 `top_up()`
    # （同目錄 `.tmp` 再 `replace`）從一開始就是這樣寫的，這裡只是補上同一個紀律。
    # `.partial.tmp` 不會被任何下游撿走：`publish.py` 只掃根目錄 `*.draft.json`、
    # `kbusage.sh` 只掃 `*.usage.json`，而這裡是 `outbox/floor/`。
    try:
        d["produced_by"] = source
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        print(f"0 寫回 produced_by 失敗（{type(e).__name__}）")
        raise SystemExit
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

# ------------------------------------------------------ 補抓：凌晨那一班拿不到的
#
# Actions 那一班跑在台北凌晨（cron 00:15，2026-09-03 實測延到 03:23），
# 而有兩件事那時候還沒發生：
#
#   ① **SPDR 的紐約歸檔要到台北 04:00–04:45 才上站。** 凌晨取到的是前一個交易日
#      那一列 —— 而前一版已經用過它。2026-09-03 實測：快取尾列是 01-Sep，
#      與前一版逐字相同。**照用不會報錯**，只會讓 `advisory.exempt_card_freshness`
#      WARN，而 WARN 不擋發布。當天是靠派工把「請你現場複驗」寫進採集員 D 的
#      任務卡才補上的，**那是一個每天都要有人記得寫的臨時處置，不是修好**。
#   ② **TWSE 的 OpenAPI 在深夜維護窗內會回空字串或 HTML。** 同一天
#      `REV_L`／`REV_O`／`CONF` 三個一起失敗（`REV_O` 回 `<html>`），
#      而當天稍晚實測三個端點全部 200、content-type 正確、**URL 一個字都沒變**。
#
# **兩個症狀、一個病：取數時點。** 沒有選擇把 Actions 的 cron 往後挪，因為那會壓縮
# 它對排程延遲的餘裕（現在 7 小時 05 分，挪到台北 05:00 只剩約 2 小時 20 分，
# 而實測延遲曾達 7 小時 39 分）。**07:20 這一班本來就晚於紐約歸檔、也避開了維護窗**，
# 所以補抓放在這裡最便宜。
#
# 三條刻意的設計：
#   · **補抓失敗不影響這一輪的退出碼。** 補抓是「讓已經合格的東西更新一點」，
#     不是合格的條件。失敗了就用凌晨那一份，那仍然是一份通過驗證的保底層。
#   · **補抓在驗證之後、`mv` 之前。** 落地的一定是補過的完整檔，
#     輪次不會讀到一個補到一半的東西。
#   · ~~**這幾個 ident 都不需要 FRED 金鑰**（SPDR 與 TWSE 都是公開端點），
#     所以這一段刻意不碰 `FRED_API_KEY`，少一個會出錯的地方。~~
#     **2026-09-23 撤回**：補抓清單加進兩條 FRED 之後這句不再成立，見下面那一段。
#     留刪節線而不是刪掉，是因為「少一個會出錯的地方」那個理由本身仍然對 ——
#     改動是判斷它換到的東西更值錢，不是判斷它當初錯。
#
# ## 2026-09-23 加進兩條 FRED：`BAMLC0A0CM` 與 `BAMLH0A0HYM2`
#
# **修的是一個安靜的落後，而它在 09-23 那一輪被實測到。**
# 當天保底檔的 `fetched_at` 是 `2026-09-22T19:45:04+00:00`，而 FRED 頁面自報
# `Updated: Sep 22, 2026 5:28 PM CDT`（＝ `2026-09-22T22:28Z`）——
# **凌晨那一班的取數時刻早於 FRED 當日發布 2 小時 43 分**，
# 於是保底檔裡兩條 OAS 的最新資料日停在 **09-18**，與前一版（09-22 那期）用過的
# **逐字相同**。照抄就會交出兩張與前一版一模一樣的保底卡，
# **而唯一的徵兆只有 `advisory.exempt_card_freshness` 的一個 WARN，那還不擋發布**。
# 當天是派工端比對保底檔與前一版才發現、臨時給採集員 A 一個具名例外去現場複驗，
# 才拿回 09-21 的 0.77／2.66。**那是一個每天都要有人記得做的臨時處置，不是修好**
# —— 與 09-03 SPDR 那次的形狀逐字相同，而那次的解法就是這張補抓清單。
#
# **07:20 這一班晚於 FRED 的發布時刻**（前一日 23:20Z 對當日 22:28Z），所以補得到。
#
# **⚠️ 這兩條與上面那幾個不同：它們要金鑰，而且它們在 `ESSENTIAL` 裡。**
# 兩件事讓它仍然是安全的，都是讀 `tools/fetch_advisory.py` 的 `top_up()` 確認過的，
# 不是假設：
#   · **補抓失敗走 `kept`，`items[ident]` 原值不動**（該函式的 else 分支）。
#     所以沒有金鑰時，Actions 抓到的那一份 `status: ok` 原封不動留著。
#   · **`failed_essential` 是拿合併後的整份 `items` 重算的**，判準是 `status == "failed"`。
#     既然原值還是 `ok`，它就不會被寫髒 —— **補抓失敗不會把整份保底檔變成不可用**。
# 換句話說：金鑰缺席時，行為退回到 09-23 之前的樣子，而不是更糟。
# 2026-09-06 加進 `SPDR:GLD_NOW` 與 `SPDR:GLDM_NOW`：`historical-archive`
# 落後一個交易日（連續三輪落在 `unchanged`，09-06 由同一天兩個端點的直接對照定案），
# 而 `/api/v1/data` 是產品頁在叫的那一個、當日就有。**兩條都補，不是二選一** ——
# archive 給 120 列的跨期序列，`_NOW` 給當日一筆，黃金卡兩個都要。
# 它們宣告了 `empty_ok`，所以取不到不會擋掉整份保底檔。
# 2026-09-15 加進 `LBMA:GOLD_PM` 與 `LBMA:GOLD_AM`：保底層在那之前沒有任何 LBMA 來源，
# 黃金卡的定盤價一直是 `SPDR:*_NOW` 的 `pm_fix_usd` 代用值，而它落後一個交易日
# （09-15 實測 4,386.25／資料日 09-11，對真正的 4,267.10／09-14 差 −2.72%）。
# **嚴格說凌晨那一班應該就抓得到**（倫敦 PM 定盤 15:00 BST ＝ 14:00Z，早於 cron 的 16:15Z），
# **放進補抓是第二道保險**：Actions 的實際開跑時刻會浮動好幾小時，
# 而 07:20 這一班（＝前一日 23:20Z）無論如何都晚於當日定盤。成本是兩個請求。
# 兩條都宣告了 `empty_ok`、都不在 `ESSENTIAL` 裡，所以倫敦休市那天不會擋掉整份保底檔。
TOPUP_IDENTS="SPDR:GLD,SPDR:GLDM,SPDR:GLD_NOW,SPDR:GLDM_NOW,TWSE:REV_L,TWSE:REV_O,TWSE:CONF,LBMA:GOLD_PM,LBMA:GOLD_AM,FRED:BAMLC0A0CM,FRED:BAMLH0A0HYM2"
if [ ! -x "$VENV_PY" ]; then
  log "略過補抓：找不到可執行的 ${VENV_PY}（凌晨那一份仍然可用）"
elif [ ! -f "$FETCHER" ]; then
  log "略過補抓：找不到 ${FETCHER}（凌晨那一份仍然可用）"
else
  # 金鑰只為 FRED 那兩條而設。**缺席不是放棄的理由** —— 其餘九個 ident 都是公開端點，
  # 照補；FRED 那兩條會 AuthFailed、走 `kept_original`，保留 Actions 抓到的原值。
  # **要把缺席這件事說出來**：沒有這一行，「今天沒補到 FRED」與「今天 FRED 沒前進」
  # 在日誌裡長得一模一樣 —— 同這支腳本上面那個 `FRED_KEYFILE` 檢查的理由。
  if [ -s "$FRED_KEYFILE" ]; then
    FRED_API_KEY="$(tr -d '[:space:]' < "$FRED_KEYFILE")"
    export FRED_API_KEY
  else
    log "補抓：找不到 FRED 金鑰（${FRED_KEYFILE}）—— 兩條 OAS 會保留原值，其餘照補"
  fi
  log "補抓開始：${TOPUP_IDENTS}"
  "$VENV_PY" "$FETCHER" --top-up "$TMP" --only "$TOPUP_IDENTS" >> "$LOG" 2>&1
  log "補抓結束（退出碼 $?）—— 逐項結果見上，補抓失敗一律保留原值"
  unset FRED_API_KEY
fi

# 原子寫入：輪次可能正好在讀這個目錄。
mv "$TMP" "$DEST"
log "落地 ${DEST}（$(wc -c < "$DEST") bytes）：${summary}"
log "=== 結束，exit=0 ==="
exit 0
