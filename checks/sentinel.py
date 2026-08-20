"""哨兵的檢查——看的不是資料內容，是「這套系統還活著嗎」。

payload 形狀：
    {"now": ISO8601, "index": {...}, "prev": {...}|None}

`prev` 是上一次哨兵執行時留下的 heartbeat 快照。**沒有它就看不見「東西變少了」**
——單張快照永遠答不出「有沒有掉東西」。

## 兩個門檻為什麼不一樣

`days[0].date` 是一個**日期**，`index.updated` 是一個**時間戳**，兩者的「多舊算太舊」
算法不同：

- 日期 D 的資料，最晚會在 D 當天（台北）被發布。門檻必須大於「每日發布時刻 ＋ 24
  小時」，否則昨天的資料會在今天發布之前就先誤報。取 **36 小時** ＝ 昨天的資料撐到
  今天台北中午才叫。
- `updated` 記的是執行發生的那一刻，兩次執行間隔就是 24 小時。取 **30 小時**，容得下
  GitHub cron 的漂移（官方不保證準時，尖峰會延遲甚至漏跑）。

把兩者設成同一個數字很整齊，但那個整齊會買到一個每天誤報兩小時的哨兵。**會固定響
的警報就是雜訊，而雜訊訓練人忽略警報。**

## 時區

台北固定 UTC+8、無日光節約，所以直接用固定位移，不依賴 tzdata。
"""
import datetime as dt

from kbcore.check import Check, fail, ok, register, skipped, warn

TPE = dt.timezone(dt.timedelta(hours=8))

# **這個數字與三個 repo 的 sentinel.yml cron 是一組的。** 年齡從那一天的台北零時
# 起算，所以 36 小時這條線落在次日中午 12:00 台北。哨兵必須排在那條線**之後**，
# 而且要留得夠遠 —— 2026-08-21 之前三個都排在 11:00–11:30，距離只有 30–60 分鐘，
# 而 GitHub 排程延遲動輒數十分鐘（實測有一次延了五小時）。
# **一個判決取決於 cron 準不準時的檢查，會隨機紅、隨機綠。**
# 現在三個都排在 07:00–07:30 UTC（15:00–15:30 台北）：昨天的資料 39 小時 → 紅。
MAX_DATE_AGE_H = 36
MAX_UPDATED_AGE_H = 30


def _now(p) -> dt.datetime:
    return dt.datetime.fromisoformat(p["now"])


def _days(p):
    return (p.get("index") or {}).get("days") or []


def _date_age_hours(p):
    """days[0].date 當天台北零時到現在，經過幾小時。負數代表日期在未來。"""
    days = _days(p)
    if not days:
        return None
    d = dt.date.fromisoformat(days[0]["date"])
    midnight = dt.datetime.combine(d, dt.time(0, 0), tzinfo=TPE)
    return (_now(p) - midnight).total_seconds() / 3600


# ── 1. 資料有沒有停在過去 ────────────────────────────────────────────
def _data_fresh(p):
    days = _days(p)
    if not days:
        return fail("index 裡一天都沒有 —— 這不是「還沒開始」，是東西不見了")
    age = _date_age_hours(p)
    if age is None:
        return skipped("算不出資料年齡")
    if age > MAX_DATE_AGE_H:
        return fail(f"最新一期是 {days[0]['date']}，已經 {age:.0f} 小時 "
                    f"（上限 {MAX_DATE_AGE_H}）—— 管線停了")
    return ok()


register(Check(
    id="sentinel.data_fresh",
    covers=f"days[0].date 距今不超過 {MAX_DATE_AGE_H} 小時",
    blind_to=[
        "日期是新的但內容跟昨天一模一樣（換了日期沒換資料）",
        "days[0] 是新的，但更舊的幾天被悄悄改過",
        "整份 index 是對的，但單期檔案本身壞掉或不存在",
    ],
    run=_data_fresh,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "index": {"days": [{"date": "2026-08-17"}]}},
    near_miss={"now": "2026-08-19T01:00:00+00:00",
               "index": {"days": [{"date": "2026-08-18"}]}},
    suite="sentinel",
))


# ── 2. 日期在未來 ──────────────────────────────────────────────────
def _no_future_date(p):
    days = _days(p)
    if not days:
        return skipped("index 裡沒有天數，該項未執行")
    age = _date_age_hours(p)
    # age 是從**那個日期的台北零時**算起。今天的資料 age 落在 0~24 之間；
    # 只要 age < 0，那個日期的零時都還沒到——它就是未來。
    #
    # 這裡原本寫 `age < -24`，想表達「容許超前一天」。但明天的零時只在十幾個
    # 小時之後，所以那條線要日期超前**兩天**才碰得到。2026-08-19 實測時漏放了
    # 一個 latest_date = 明天 的靶子，判定「全部正常」。
    #
    # 而且沒有理由容許超前：已發布的日期應該是被觀測到的，不是被寫出來的。
    if age < 0:
        return fail(f"最新一期是 {days[0]['date']}，那一天還沒到（還有 {-age:.0f} 小時）"
                    " —— 日期是被寫出來的，不是被觀測到的")
    return ok()


register(Check(
    id="sentinel.no_future_date",
    covers="days[0].date 不在未來",
    blind_to=[
        "日期沒超前，但它是硬寫進去的當天日期而非真的抓到了資料",
    ],
    run=_no_future_date,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "index": {"days": [{"date": "2026-08-20"}]}},
    near_miss={"now": "2026-08-19T01:00:00+00:00",
               "index": {"days": [{"date": "2026-08-19"}]}},
    suite="sentinel",
))


# ── 3. 執行時間戳有沒有跟著動 ───────────────────────────────────────
def _updated_fresh(p):
    """**這條才是 8/03 那次會抓到的。**

    舊系統的 days[0].date 一直是當天日期，看起來永遠正常，實際上流程早就沒跑。
    日期可以被寫出來，時間戳記的是「有沒有真的執行過」。
    """
    upd = (p.get("index") or {}).get("updated")
    if upd is None:
        return skipped("index 沒有 updated 欄位 —— 無法分辨「寫了日期」與「真的跑過」")
    age = (_now(p) - dt.datetime.fromisoformat(upd)).total_seconds() / 3600
    if age > MAX_UPDATED_AGE_H:
        return fail(f"index.updated 是 {upd}，已經 {age:.0f} 小時 "
                    f"（上限 {MAX_UPDATED_AGE_H}）—— 沒有人在跑")
    if age < 0:
        return warn(f"index.updated 在未來（{upd}）—— 機器時鐘或時區有問題")
    return ok()


register(Check(
    id="sentinel.updated_fresh",
    covers=f"index.updated 距今不超過 {MAX_UPDATED_AGE_H} 小時",
    blind_to=[
        "時間戳在動但寫進去的內容是空的",
        "時間戳是在失敗路徑上被更新的",
    ],
    run=_updated_fresh,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "index": {"days": [{"date": "2026-08-19"}],
                       "updated": "2026-08-17T18:00:00+00:00"}},
    near_miss={"now": "2026-08-19T01:00:00+00:00",
               "index": {"days": [{"date": "2026-08-19"}],
                         "updated": "2026-08-17T20:00:00+00:00"}},
    suite="sentinel",
))


# ── 4. 東西有沒有變少 ──────────────────────────────────────────────
def _no_data_loss(p):
    """單張快照答不出這個問題，所以要拿上一次的 heartbeat 來比。

    這條是 2026-08-19 生產 repo 污染事故的直接產物：那次 index.json 的 days 從
    14 天被蓋成 1 天，而**當下每一個訊號都說成功**。
    """
    prev = p.get("prev")
    if prev is None:
        return skipped("沒有上一次的 heartbeat，第一次執行無從比較")
    was = prev.get("day_count")
    if was is None:
        return skipped("上一次的 heartbeat 沒有 day_count")
    now = len(_days(p))
    if now < was:
        return fail(f"天數從 {was} 掉到 {now} —— 已發布的資料只該增加。"
                    "有東西蓋掉了 index")
    return ok()


register(Check(
    id="sentinel.no_data_loss",
    covers="index 的天數只增不減（與上一次 heartbeat 相比）",
    blind_to=[
        "天數沒變但某一天的內容被換掉了",
        "天數增加了，但增加的是垃圾",
        "兩次哨兵之間掉了又補回來（取樣間隔看不到）",
    ],
    run=_no_data_loss,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "index": {"days": [{"date": "2026-08-19"}]},
             "prev": {"day_count": 2}},
    near_miss={"now": "2026-08-19T01:00:00+00:00",
               "index": {"days": [{"date": "2026-08-19"}]},
               "prev": {"day_count": 1}},
    suite="sentinel",
))


# ── 5. 帳本逾期未判 ────────────────────────────────────────────────
def _ledger_overdue(p):
    led = p.get("ledger")
    if led is None:
        return skipped("這個系統還沒有訊號帳本，該項未執行")
    now = _now(p)
    late = [x["id"] for x in led
            if x.get("judge", {}).get("type") == "manual"
            and x.get("judge", {}).get("at") is None
            and dt.datetime.fromisoformat(x["due"]) < now]
    if late:
        return warn(f"{len(late)} 筆逾期未判：{', '.join(late[:5])}")
    return ok()


register(Check(
    id="sentinel.ledger_overdue",
    covers="帳本裡沒有逾期未判的項目",
    blind_to=[
        "有判但判得很敷衍",
        "還沒到期但顯然已經錯了的項目",
    ],
    run=_ledger_overdue,
    fixture={"now": "2026-08-19T01:00:00+00:00",
             "ledger": [{"id": "x1", "due": "2026-08-19T00:59:00+00:00",
                         "judge": {"type": "manual", "at": None}}]},
    near_miss={"now": "2026-08-19T01:00:00+00:00",
               "ledger": [{"id": "x1", "due": "2026-08-19T01:01:00+00:00",
                           "judge": {"type": "manual", "at": None}}]},
    suite="sentinel",
))
