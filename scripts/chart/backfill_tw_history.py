# -*- coding: utf-8 -*-
"""
backfill_tw_history.py — 一次性把台股路線的快取補到 `anchors.history_limits.tw_route_months`。

【為什麼要有這支，而不是改一個數字就好】

**先看一眼 `tw_route_months` 為什麼是 37 不是 36**：`_months_back()` 含本月，
而本月不完整，所以**覆蓋 N 年要 12N+1 個月**。2026-09-02 實跑時填的是 36，
補完 `^TWII` 每個數字都變好（485 → 708 點）、這支也判「已夠深」，
**而 `scan_moves` 的 ★ 還在**（`short_by_days` ＝ 31）。
案例（3）就是為了讓這件事下次是紅字，不是一次安靜的重跑。


2026-09-02 量到：走 `fetch_tw_price` 的七條快取（`^TWII`、2330、2317、2344、2382、
2408、8069.TWO）**全部起於 2024-09-02、跨距剛好 2.00 年**，而同一天其他路線是
5.22–11.66 年。成因是 `series()` 的預設 `months=24`，而 `fetch.get()` 從來沒有覆寫它。

**把預設改大不會補到歷史。** `series()` 在 `have_through` 非空時走
`_months_since()`，只從快取末日數到本月 —— 歷史那一段**永遠不會被要求**，
所以快取的起日會一直停在它第一次被建起來的那一天，只往前長不往後長。
要補得刻意走一次 `have_through=""` 的全量，讓 `fetch.get()` 那道
「只能長不能縮」的聯集守衛把舊的那一段接回去。

【為什麼預設一次只做兩條】

一條全量 ＝ `tw_route_months` 次證交所請求（`series()` 內部每月之間 sleep 1 秒），
現在是 37。七條全做 259 次，而 **2026-08-30 那場證交所節流事故是 144 次／天造成的**，
壞掉的正是抓取順序的最後兩個，嚴重度隨順序遞增。所以：

  · 預設 `--max-series 2`，跑完印出還剩哪幾條，**要你自己再跑一次**。
  · 已經夠深的序列自動跳過，所以重跑是冪等的、也不會白打請求。
  · 想一次做完要明寫 `--all`，那是一個決定，不是一個預設。

【這支必須在 Mac 上跑】

沙箱那一側連不到證交所。跑之前先確認 `CHART_REPO` 指到 `~/chart-of-the-day`。

用法：
    python3 ~/kb-core/scripts/chart/backfill_tw_history.py --dry-run
    python3 ~/kb-core/scripts/chart/backfill_tw_history.py
    python3 ~/kb-core/scripts/chart/backfill_tw_history.py --only '^TWII'
    python3 ~/kb-core/scripts/chart/backfill_tw_history.py --all
    python3 ~/kb-core/scripts/chart/backfill_tw_history.py --selftest-offline
"""
from __future__ import annotations
import argparse, datetime, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F                                    # noqa: E402
import fetch_tw_price as TW                          # noqa: E402

PAUSE_BETWEEN_SERIES = 5.0
# 深度容差：目標起日與實際起日差在這個天數內就算補到了。
# **與 `scan_moves.SHORT_TOLERANCE_DAYS` 是同一個理由**（台股農曆年可連休九天加
# 前後週末約十一天），值刻意取一樣 —— 兩邊都在問「這條夠不夠深」，
# 用兩個不同的容差會讓同一條序列在一邊算夠、另一邊算不夠。
TOLERANCE_DAYS = 14


def tw_cached_ids() -> list:
    """快取目錄裡走台股路線的代號。**清單自己維護自己，不硬寫。**

    代號從檔頭第一行讀（`# ^TWII | TWSE 指數 | fetched ...`），
    **不從檔名反推** —— `cache_path()` 的轉換是有損的（`_` 可能來自 `^`，
    `-` 可能來自 `=` 或 `/`），反推寫錯不會報錯，只會安靜地去抓另一條序列。
    """
    out = []
    if not os.path.isdir(F.CACHE):
        return out
    for fn in sorted(os.listdir(F.CACHE)):
        if not fn.endswith(".csv"):
            continue
        try:
            with open(os.path.join(F.CACHE, fn), encoding="utf-8") as f:
                head = f.readline().strip()
        except OSError:
            continue
        if not head.startswith("#"):
            continue
        ident = head.lstrip("#").split("|")[0].strip()
        if ident and F.route_of(ident) == "tw":
            out.append(ident)
    return out


def _target_start(months: int) -> datetime.date:
    """`_months_back(months)` 會抓到的最早那個月的 1 號。

    **跟 `fetch_tw_price._months_back()` 用同一套數法**：它含本月，
    所以往回數 `months` 個月的第一個月就是目標。
    """
    today = datetime.date.today()
    y, m = today.year, today.month
    for _ in range(months - 1):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return datetime.date(y, m, 1)


def depth_of(ident: str) -> tuple[int, str, str]:
    """(點數, 起日, 末日)；沒有快取回 (0, "", "")。"""
    d, _ = F.read_cache(F.cache_path(ident))
    return (len(d), d[0] if d else "", d[-1] if d else "")


def needs_backfill(ident: str, months: int) -> bool:
    """夠深就不用補。**空快取要補**（起日是空字串，比任何日期都「淺」）。"""
    n, first, _ = depth_of(ident)
    if not n:
        return True
    want = _target_start(months)
    try:
        got = datetime.date.fromisoformat(first)
    except ValueError:
        return True
    return (got - want).days > TOLERANCE_DAYS


def backfill_one(ident: str, months: int) -> tuple[int, int]:
    """強制全量取一次，走 `fetch.merge_write()` 的聯集守衛寫回。回傳 (補前, 補後) 點數。

    **`have_through=""` 是這支存在的全部理由** —— 那是唯一會讓 `series()`
    走 `_months_back()` 全量那條路的方式。
    """
    s = TW.series(ident, months=months, have_through="")
    before, dates, _ = F.merge_write(
        F.cache_path(ident), ident, s, time.strftime("%Y-%m-%d"))
    return before, len(dates)


def selftest_offline() -> int:
    """純邏輯自檢 —— **不連外**，所以沙箱裡也驗得了。

    補歷史的錯法是安靜的（補了但沒補到底＝快取還是短的，而數字看起來都正常），
    所以「夠不夠深」的判定要有自己的回歸案例。
    """
    rc = 0

    def eq(label, got, want):
        nonlocal rc
        if got != want:
            print(f"  ✗ {label}：得到 {got}，預期 {want}"); rc = 1
        else:
            print(f"  ✓ {label}")

    today = datetime.date.today()

    # 1. 目標起日含本月往回數 —— 36 個月是「本月與之前 35 個月」
    ts = _target_start(36)
    months_span = (today.year - ts.year) * 12 + (today.month - ts.month)
    eq("_target_start(36) 跨 35 個月邊界", months_span, 35)
    eq("_target_start 回傳月初 1 號", ts.day, 1)

    # 2. 與 fetch_tw_price._months_back 同一套數法 —— **兩邊數法不同就會永遠補不完**
    eq("_target_start 對得上 _months_back",
       (ts.year, ts.month), TW._months_back(36)[0])

    # 3. **12N+1**：anchors 設的月數要真的覆蓋得到 `scan_moves` 的三年窗口。
    #    2026-09-02 實跑踩到：36 個月只到 2023-10-01，而三年切點是 2023-09-01，
    #    於是補完之後每個數字都變好、`needs_backfill` 也說夠深，**而 ★ 還在**。
    #    `_months_back()` 含本月（不完整的那個月），所以覆蓋 N 年要 12N+1 個月。
    #    **這一條是為了讓「有人再填 36」變成紅字，而不是變成一次安靜的重跑。**
    months_cfg = F.tw_route_months()
    three_years_ago = datetime.date(today.year - 3, today.month, 1)
    eq(f"tw_route_months={months_cfg} 覆蓋得到三年窗口（12N+1）",
       _target_start(months_cfg) <= three_years_ago, True)

    # 4. 容差：差 1 天算夠深（BAMLH0A0HYM2 那種假警報的形狀，見 scan_moves 2026-09-01）
    class _Fake:
        pass
    saved = F.read_cache
    try:
        F.read_cache = lambda p: ([(ts + datetime.timedelta(days=1)).isoformat(),
                                   today.isoformat()], [1.0, 2.0])
        eq("差 1 天不算淺", needs_backfill("^TWII", 36), False)
        F.read_cache = lambda p: ([(ts + datetime.timedelta(days=TOLERANCE_DAYS + 1)).isoformat(),
                                   today.isoformat()], [1.0, 2.0])
        eq("差 15 天算淺", needs_backfill("^TWII", 36), True)
        # 5. 空快取要補 —— **不可以因為「沒有起日」而被當成夠深**
        F.read_cache = lambda p: ([], [])
        eq("空快取要補", needs_backfill("^TWII", 36), True)
        # 6. 起日壞掉要補，不是安靜跳過
        F.read_cache = lambda p: (["not-a-date", today.isoformat()], [1.0, 2.0])
        eq("起日壞掉要補", needs_backfill("^TWII", 36), True)
    finally:
        F.read_cache = saved

    print("補歷史自檢：" + ("全部通過 ✓" if rc == 0 else "有失敗 ✗"))
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--months", type=int, default=None,
                    help="預設讀 anchors.history_limits.tw_route_months")
    ap.add_argument("--only", default="", help="只補這一條")
    ap.add_argument("--max-series", type=int, default=2)
    ap.add_argument("--all", action="store_true", help="一次補完（七條約 259 次請求，自己決定）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest-offline", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest_offline:
        return selftest_offline()

    months = a.months or F.tw_route_months()
    ids = [a.only] if a.only else tw_cached_ids()
    if a.only and F.route_of(a.only) != "tw":
        print(f"{a.only} 不走台股路線（route_of ＝ {F.route_of(a.only)}）"
              " —— 這支只補台股，其他路線的深度由來源決定，不由我們傳的參數決定",
              file=sys.stderr)
        return 2

    print(f"目標 {months} 個月（起日 ≥ {_target_start(months)}，容差 {TOLERANCE_DAYS} 天）"
          f"｜快取 {F.CACHE}")
    todo, okd = [], []
    for i in ids:
        n, first, last = depth_of(i)
        (todo if needs_backfill(i, months) else okd).append((i, n, first, last))

    for i, n, first, last in okd:
        print(f"  ✓ {i:12s} n={n:5d}  {first} ~ {last}  已夠深，跳過")
    for i, n, first, last in todo:
        print(f"  · {i:12s} n={n:5d}  {first or '(空)'} ~ {last or '(空)'}  要補")

    if not todo:
        print("沒有要補的。**這與「補失敗了」不同** —— 上面每一條都印了實際起日。")
        return 0

    batch = todo if a.all else todo[:max(1, a.max_series)]
    print(f"\n這一批 {len(batch)} 條，約 {len(batch) * months} 次證交所請求"
          f"（每月間隔 1 秒，約 {len(batch) * months // 60} 分 {len(batch) * months % 60} 秒）")
    if a.dry_run:
        print("--dry-run：不取數。")
        return 0

    rc = 0
    for k, (i, n, first, last) in enumerate(batch):
        print(f"\n[{k + 1}/{len(batch)}] {i} 全量重建 {months} 個月 …")
        try:
            before, after = backfill_one(i, months)
            _, nf, nl = depth_of(i)
            print(f"    {before} → {after} 點（{'+' if after >= before else ''}{after - before}）"
                  f"，起日 {first or '(空)'} → {nf}，末日 {nl}")
            if needs_backfill(i, months):
                print("    ⚠ 補完仍然不夠深 —— **不要重跑，先看來源**："
                      "多半是那幾個月被節流回空（SOURCES.md：空不是「沒有資料」，是被擋）")
                rc = 1
        except F.SeriesRegressed as e:
            # 聯集守衛已經保住快取，所以這裡是「今天這條不可信」，不是「資料掉了」
            print(f"    ✗ {e}", file=sys.stderr); rc = 1
        except Exception as e:                       # noqa: BLE001
            print(f"    ✗ {i} 補歷史失敗：{e}", file=sys.stderr); rc = 1
        if k < len(batch) - 1:
            time.sleep(PAUSE_BETWEEN_SERIES)

    left = [t for t in todo if needs_backfill(t[0], months)]
    if left:
        print(f"\n還剩 {len(left)} 條：{', '.join(t[0] for t in left)}"
              "\n**再跑一次這支就會接著做**（夠深的自動跳過，重跑是冪等的）。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
