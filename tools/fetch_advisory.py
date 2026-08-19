#!/usr/bin/env python3
"""投顧保底層 —— 跑在 GitHub Actions，把「每天一定拿得到」的東西先抓好。

用法：fetch_advisory.py <raw 目錄> [YYYYMMDD]

它抓的是**保底**，不是新聞：兩條信用債 OAS、兩檔黃金 ETF 持倉、六個台股官方端點。
新聞由 Mac 那一輪的採集負責。

三條刻意的設計：

1. **部分失敗是正常的，整輪中止不是。**
   十個端點裡有一個不通，另外九個的資料仍然有價值。所以每一個 ident 各自記
   `ok` / `failed` 加**具名理由**，整輪的退出碼看的是「有沒有必要的那幾個掛掉」。

2. **零筆與失敗是兩件事。** 法說會端點週末回 0 筆是正常狀態（「當日訊息」不是
   「行事曆」），路由表用 `empty_ok` 宣告誰可以是空的。**沒有宣告的端點回空就是失敗**
   —— 否則「今天沒有資料」與「今天沒查到」會退化成同一個訊號。

3. **單位跟著資料走。** 每一筆都帶 `unit` 與 `note`，因為三大法人回的是元、
   融資金額是仟元、月營收是仟元 —— 舊系統靠人記，而人會忘。
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.fetch import (AuthFailed, FetchError, ParseFailed,  # noqa: E402
                          UnknownIdent, UpstreamError, get)
from kbcore.fetch_tw import ROUTES, get_tw  # noqa: E402
from kbcore.result import Exit  # noqa: E402

# 保底卡直接依賴的那幾個。它們掛掉 = 今天的保底卡出不來 = 序列斷點。
ESSENTIAL = {"FRED:BAMLC0A0CM", "FRED:BAMLH0A0HYM2", "SPDR:GLD"}

FRED_IDENTS = ["FRED:BAMLC0A0CM", "FRED:BAMLH0A0HYM2"]
TW_IDENTS = list(ROUTES)


def fetch_one(ident: str, ymd: str) -> dict:
    try:
        if ident.startswith("FRED:"):
            start = (dt.date.fromisoformat(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
                     - dt.timedelta(days=30)).isoformat()
            return {"status": "ok", "unit": "bps 或 %", "note": "ICE BofA OAS",
                    "data": get(ident, start)}
        r = get_tw(ident, ymd)
        rows = (r["data"].get("rows") if isinstance(r["data"], dict) else None)
        empty = rows is not None and len(rows) == 0
        if empty and not ROUTES[ident].get("empty_ok"):
            return {"status": "failed", "reason": "EmptyResult",
                    "detail": f"{ident} 回了零列，而它沒有宣告 empty_ok"}
        enc = r["data"].get("encoding") if isinstance(r["data"], dict) else None
        return {"status": "ok", "unit": r["unit"], "note": r["note"],
                "url": r["url"], **({"encoding": enc} if enc else {}),
                "data": r["data"]}
    except FetchError as e:
        return {"status": "failed", "reason": type(e).__name__, "detail": str(e)}


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return Exit.BAD_INPUT
    raw_dir = Path(argv[1])
    ymd = argv[2] if len(argv) == 3 else dt.datetime.now(
        dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d")
    date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"

    out, failed_essential, failed_other = {}, [], []
    for ident in FRED_IDENTS + TW_IDENTS:
        r = fetch_one(ident, ymd)
        out[ident] = r
        mark = "ok" if r["status"] == "ok" else f"{r['reason']}"
        print(f"  {ident:16} {mark}"
              + ("" if r["status"] == "ok" else f" —— {r['detail'][:90]}"))
        if r["status"] == "failed":
            (failed_essential if ident in ESSENTIAL else failed_other).append(ident)

    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{date}.json").write_text(json.dumps({
        "date": date,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "essential": sorted(ESSENTIAL),
        "failed_essential": failed_essential,
        "failed_other": failed_other,
        "items": out,
    }, ensure_ascii=False, indent=1))

    # 退讓過就要看得見。utf-8 以外的編碼不是錯誤，但它是一個要被人看到的狀態。
    fell_back = [f"{k}（{r['encoding']}）" for k, r in out.items()
                 if r.get("encoding") and r["encoding"] != "utf-8-sig"]
    if fell_back:
        print(f"\n編碼退讓：{'、'.join(fell_back)} —— 不是錯誤，但值得看一眼是不是亂碼")

    n_ok = sum(1 for r in out.values() if r["status"] == "ok")
    print(f"\n{n_ok}/{len(out)} 成功；"
          f"必要項失敗 {len(failed_essential)}、其餘失敗 {len(failed_other)}")

    if failed_essential:
        print(f"必要項掛了：{'、'.join(failed_essential)} —— 保底卡今天出不來",
              file=sys.stderr)
        return Exit.ENVIRONMENT
    if failed_other:
        # **不是失敗。** 其餘九項的資料仍然有價值，而失敗已經具名寫進 raw 檔，
        # 下游看得到。整輪紅掉會讓「有一個端點不通」與「整層沒跑」長得一樣。
        print("有非必要項失敗，已具名記錄，raw 仍然落地")
    return Exit.OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
