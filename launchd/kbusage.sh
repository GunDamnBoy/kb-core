#!/bin/bash
# 七套系統 · 用量量測 —— launchd 呼叫的包裝腳本。
#
# ## 它解的是「唯一沒有自動化執行者的那一步」
#
# 每一套系統的收尾都要把那一輪的 token 用量寫進 `metrics/usage.csv`。
# 到 2026-08-24 為止那一步是**人工**的：run skill 印一行指令，人要在 Mac 的
# 終端機貼上去跑。結果是 `usage.csv` 只有三列（broker-research 08-22、
# podcast 08-23、chart 08-23），而 **advisory 一列都沒有** —— 它每天都跑，
# 每天都沒有人記得補。
#
# **這不是紀律問題，是缺一個執行者。** 另外六件事（抓、發布、看門狗、轉檔、
# 預抓、推 kb-core）都有 launchd 在跑，只有量測沒有。這一支補上它。
#
# ## 為什麼要 sidecar，不讓腳本自己去猜
#
# `usage_report.py` 預設會挑 `CLAUDE_CONFIG_DIR/projects/*/*.jsonl` 裡**最新的**
# 那一份。在 Cowork 這個假設會錯，而且錯得很安靜：
#
#   · 每一場 Cowork 對話有**自己的** `local_<uuid>/.claude`，不是共用一個。
#     「最新」指的是最近有人講話的那一場，不是那一輪排程跑的那一場。
#   · 排程輪次與事後的維護對話**會共用同一份逐字稿**（2026-08-24 實測：
#     07:35 的 advisory 輪次與 09:47 起的維護對話在同一個 session）。
#   · 挑錯逐字稿與挑對的，**算出來的數字都很合理** —— 只有檔名那一行看得出來。
#
# 所以路徑不用猜：**輪次自己知道它在哪一場**（outputs 目錄的兄弟就是 `.claude`），
# 收尾時把逐字稿的絕對路徑寫進 sidecar，這一支照著讀。
# `--transcript` 一旦給了，`pick_transcript()` 直接回傳它，
# **既不挑也不做 90 分鐘的 staleness 判斷** —— 於是 Mac 睡著、launchd 延後、
# 或那一場後來又有人講話，都不影響結果。
#
# ## sidecar 長什麼樣
#
# 位置與回執同一個目錄（advisory 在 `~/outbox/` 根目錄，其餘六套在自己的子目錄）：
#
#     ~/outbox/<日期>.usage.json                 # advisory
#     ~/outbox/<系統目錄>/<日期>.usage.json      # 其餘六套
#
#     {"system":"advisory","date":"2026-08-24",
#      "transcript":"/Users/macmini/Library/Application Support/Claude/…/<uuid>.jsonl",
#      "since":"2026-08-24T07:35:00+08:00"}
#
# `until` 應該填，值是那一輪寫進日檔 `window.to` 的那一刻。
# **不要用回執當上界** —— `~/outbox/<日期>.receipt.json` 每一次 publish 都覆寫同一個檔，
# 所以它的 `at` 是「那個日期最後一次 publish 的時刻」，不是「那一輪落地的時刻」。
# 2026-08-24 實測四期：08-21 差 1 分、08-23 差 −1 分、08-24 差 24 分，
# 而 **08-22 差 613 分鐘**（那天重發過）。平常只差一兩分鐘，
# **所以它壞掉的那天不會有人發現**，而算出來的數字仍然很合理。
# 沒給 `until` 時仍退回 `--until-receipt <date>`（`usage_report.py` 有 `OUTBOX_DIR`
# 對照表，知道 advisory 的回執在根目錄），但會在日誌記一筆說上界是鬆的。
#
# ## 為什麼不跑 git
#
# `usage.csv` 在 `~/kb-core` 裡，而 `com.kenny.kbcorepush` 每 300 秒會帶著閘門推它。
# 這支只 append 一行就結束 —— **與 `kbprefetch-*.sh` 同一個紀律：
# 產生變動的不碰 git，變動由專責那條線帶走。**
set -o pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# **三個環境變數的唯一理由是它驗得動。** 生產路徑是預設值，launchd 不用設任何東西；
# 但少了這三個縫，這支腳本就只能用 `bash -n` 驗語法，而它真正會錯的地方
# （sidecar 解析、含空白的逐字稿路徑、冪等去重、失敗不刪 sidecar）
# 一條都驗不到 —— 而那正是 `dirty_outside()` 被抽成純函式的同一個理由。
export HOME="${KBUSAGE_HOME:-/Users/macmini}"
KB="${KBUSAGE_KB:-$HOME/kb-core}"
PY="${KBUSAGE_PY:-$HOME/.venvs/kb/bin/python}"
CSV="$KB/metrics/usage.csv"
OUTBOX="$HOME/outbox"
LOGDIR="$HOME/.kbusage"
LOG="$LOGDIR/kbusage.log"
STALE_DAYS=2            # sidecar 拖過這麼久還沒成功就搬開，不要每 10 分鐘重試到天荒地老

mkdir -p "$LOGDIR"

if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

if [ ! -x "$PY" ]; then
  log "找不到 ${PY} —— 這是環境問題，不是資料問題"
  exit 14
fi

# `~/outbox/*.usage.json` 是 advisory（回執在根目錄），`*/*.usage.json` 是其餘六套。
# nullglob 讓「沒有 sidecar」變成空迴圈而不是一個字面值路徑。
shopt -s nullglob
SIDECARS=("$OUTBOX"/*.usage.json "$OUTBOX"/*/*.usage.json)
shopt -u nullglob

if [ ${#SIDECARS[@]} -eq 0 ]; then
  exit 0          # 空輪次，不是失敗。**不寫日誌** —— 每 10 分鐘一行會把日誌洗掉
fi

rc_all=0
for SC in "${SIDECARS[@]}"; do
  # 解析 sidecar。**欄位缺一個就跳過並講出來**，不要用預設值把它補起來 ——
  # 補起來的那一輪會產生一列看起來很合理、但界線是猜的資料。
  read -r SYS DATE SINCE UNTIL TRANSCRIPT < <(
    /usr/bin/python3 - "$SC" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print(f"! ! ! ! 讀不開（{type(e).__name__}）")
    raise SystemExit
miss = [k for k in ("system", "date", "transcript", "since") if not d.get(k)]
if miss:
    print(f"! ! ! ! 缺欄位：{','.join(miss)}")
    raise SystemExit
# 逐字稿路徑含空白（"Application Support"），所以這裡不能用空白分隔輸出 ——
# 把它擺在最後一欄，讓 read 的最後一個變數把剩下的全吃走。
print(d["system"], d["date"], d["since"], d.get("until") or "-", d["transcript"])
PY
  )

  if [ "$SYS" = "!" ]; then
    log "sidecar 不合格 $SC —— $TRANSCRIPT，搬到 .bad 讓它別再擋著"
    mv "$SC" "$SC.bad"
    rc_all=12
    continue
  fi

  # 冪等：同一天同一套已經有一列就不要再寫。**重跑不該長出第二列** ——
  # 而 launchd 每 10 分鐘就是一次重跑。
  if [ -f "$CSV" ] && grep -q "^${DATE},${SYS}," "$CSV"; then
    log "$SYS $DATE 已經在 usage.csv 裡，移除 sidecar"
    rm -f "$SC"
    continue
  fi

  if [ ! -f "$TRANSCRIPT" ]; then
    log "$SYS $DATE 的逐字稿不存在：$TRANSCRIPT —— 這一輪跳過（等下一次）"
    rc_all=12
    continue
  fi

  # 上界：sidecar 明講的優先；沒講就讓 usage_report.py 自己去讀那一套的回執。
  # **兩種都是界線，不是「沒有界線」**，但它們不一樣可信，而 `bounded` 欄記的
  # 就是這件事：sidecar 給了 until 記 `sidecar`；退回讀回執記 `manual`
  # （有界線，但那是「那個日期最後一次 publish 的時刻」，說不清楚是哪一輪的）。
  if [ "$UNTIL" != "-" ]; then
    # **出處記成 sidecar** —— 那個值是輪次自己寫的交草稿時刻，
    # 與 usage_scan.py 從日檔讀到的 window.to 是同一個東西的兩條路。
    BOUND=(--until "$UNTIL" --bound-src sidecar)
  else
    # 回執那條路**不標 sidecar** —— 它是「那個日期最後一次 publish 的時刻」。
    # 記成 commit 也不對（那是 publish 成功的時刻但至少取的是最早那顆），
    # 所以留給 usage_report.py 記成 `manual`：有界線，但出處說不清楚。
    BOUND=(--until-receipt "$DATE")
    log "$SYS $DATE 的 sidecar 沒給 until，退回回執當上界 —— **那是那個日期最後一次 publish 的時刻，不是那一輪落地的時刻**，同一天重發過就會偏高"
  fi

  log "量 $SYS $DATE（since=$SINCE ${BOUND[*]}）"
  # **`--date` 明講**：sidecar 帶的 `date` 是那一輪自己的日期，而
  # `usage_report.py` 沒收到就會用逐字稿最後一筆的 **UTC** 日期 ——
  # 台北 08:00 前收工的輪次會被記成前一天。
  OUT="$("$PY" "$KB/tools/usage_report.py" "$SYS" \
          --transcript "$TRANSCRIPT" --since "$SINCE" "${BOUND[@]}" \
          --date "$DATE" --append "$CSV" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    log "$SYS $DATE 完成：$(printf '%s\n' "$OUT" | tail -2 | tr '\n' ' ')"
    rm -f "$SC"
  else
    # **先把失敗記下來，再做任何可能自己出錯的事。**
    # 2026-08-24 首次負向測試時這兩行是相反的順序：先算 sidecar 年紀、後設 rc_all，
    # 而 `stat` 在測試環境上是另一種方言、算式炸掉，於是**整個失敗分支被跳過、
    # 這一支回報 exit 0**。launchd 只看得到退出碼，所以那等於「量測失敗但沒人知道」——
    # 正是這套系統一路在防的那種形狀。
    rc_all="$rc"
    # **失敗不刪 sidecar**，下一輪還會再試（回執晚到是最常見的原因）。
    # 但也不要永遠試下去：拖過 STALE_DAYS 就搬開並留下原因。
    #
    # **年紀用 sidecar 自己帶的 `date` 算，不用檔案 mtime。** 兩個理由：
    # ①`stat` 有兩種方言（macOS `-f %m`、GNU `-c %Y`），而 `$(A || B)` 會把
    #   **A 的 stdout 也一起吃進來** —— GNU 的 `-f` 是「檔案系統狀態」，
    #   它會成功印出一整段 Blocks/Inodes，於是變數裡混著那段文字，
    #   數值比較安靜失敗、年紀永遠算成 0。2026-08-24 的負向測試就是這樣抓到的，
    #   而**那個分支在生產（macOS）上跑得動，所以不測就永遠不會發現**。
    # ②mtime 會被複製、備份、rsync 重設，`date` 不會。要問的本來就是
    #   「這是哪一天那一輪的」，不是「這個檔案什麼時候被碰過」。
    AGE_D="$(/usr/bin/python3 -c "
import datetime as dt, sys
try:
    d = dt.date.fromisoformat(sys.argv[1])
    print((dt.date.today() - d).days)
except Exception:
    print(0)
" "$DATE")"
    log "$SYS $DATE 失敗 exit=$rc（已 ${AGE_D} 天）：$(printf '%s\n' "$OUT" | head -3 | tr '\n' ' ')"
    if [ "$AGE_D" -ge "$STALE_DAYS" ]; then
      mv "$SC" "$SC.failed"
      log "$SYS $DATE 超過 ${STALE_DAYS} 天仍失敗，搬成 .failed —— 這一列要人來補"
    fi
  fi
done

exit "$rc_all"
