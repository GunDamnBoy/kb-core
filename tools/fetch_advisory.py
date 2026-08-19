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


# 會把日期塞進網址的那幾個台股端點。其餘是固定網址的 OpenAPI 清單，不吃日期。
DATED_TW = [i for i, s in ROUTES.items()
            if "{ymd}" in s["url"] or "{y}" in s["url"]]
LOOKBACK_DAYS = 10


def stat_ok(data) -> bool:
    """TWSE／TPEX 用回應體裡的 `stat` 說有沒有資料，而 HTTP 一律回 200。

    「很抱歉，沒有符合條件的資料」是一個 **200 OK 的正常回應**——這正是它危險的
    地方：不看 `stat` 就會把「今天還沒收盤」記成抓取成功。2026-08-19 首輪的 raw
    就是 `status: ok` 而 `data.stat` 是那句道歉，三大法人與融資融券整組是空的，
    靠採集端的人工比對才發現。**HTTP 狀態碼與資料有效性是兩件事。**
    """
    if not isinstance(data, dict) or "stat" not in data:
        return True  # 沒有 stat 欄的端點（OpenAPI 清單、CSV）不適用這條
    return str(data["stat"]).strip().upper() == "OK"


def fetch_tw_backdated(ident: str, ymd: str) -> dict:
    """從前一日往回走，直到端點回出真的有資料的那一天。

    **為什麼不是「今天」**：三大法人與融資融券是*盤後*數據。這一輪排在台北 07:30、
    保底層更早在 06:43，問今天等於問一個還沒發生的收盤，而窗口本來就是前一日
    07:00 起——要的本來就是前一日的盤後數字。舊行為連規格都對不上。

    **為什麼不是固定「昨天」**：昨天可能是週末或國定假日。與其自己維護一份台股
    行事曆——那會是第二份會漂移的副本，而且每年都要改——不如讓端點自己回答
    哪一天有資料。往回走的天數會記在 `looked_back` 裡，連假就是會大於 1。
    """
    start = dt.date.fromisoformat(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
    tried = []
    for back in range(1, LOOKBACK_DAYS + 1):
        d = start - dt.timedelta(days=back)
        r = get_tw(ident, d.strftime("%Y%m%d"))
        if stat_ok(r["data"]):
            r["session_date"] = d.isoformat()
            r["looked_back"] = back
            return r
        tried.append(d.isoformat())
    raise UpstreamError(
        f"{ident} 自 {tried[0]} 往回 {LOOKBACK_DAYS} 天都回「沒有符合條件的資料」")


def fetch_one(ident: str, ymd: str) -> dict:
    try:
        if ident.startswith("FRED:"):
            start = (dt.date.fromisoformat(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
                     - dt.timedelta(days=30)).isoformat()
            return {"status": "ok", "unit": "bps 或 %", "note": "ICE BofA OAS",
                    "data": get(ident, start)}
        r = fetch_tw_backdated(ident, ymd) if ident in DATED_TW else get_tw(ident, ymd)
        rows = (r["data"].get("rows") if isinstance(r["data"], dict) else None)
        empty = rows is not None and len(rows) == 0
        if empty and not ROUTES[ident].get("empty_ok"):
            return {"status": "failed", "reason": "EmptyResult",
                    "detail": f"{ident} 回了零列，而它沒有宣告 empty_ok"}
        # 不吃日期的端點也要驗 stat——它們一樣可能回 200 ＋ 一句道歉。
        if not stat_ok(r["data"]) and not ROUTES[ident].get("empty_ok"):
            return {"status": "failed", "reason": "NoDataForDate",
                    "detail": f"{ident} 回 200 但 stat 是 {r['data'].get('stat')!r}"}
        enc = r["data"].get("encoding") if isinstance(r["data"], dict) else None
        return {"status": "ok", "unit": r["unit"], "note": r["note"],
                "url": r["url"],
                **({"session_date": r["session_date"],
                    "looked_back": r["looked_back"]} if "session_date" in r else {}),
                **({"encoding": enc} if enc else {}),
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
    # 截斷要看得見。安靜地只留最後 N 列，會讓「歷史很短」與「我們只保留這麼多」
    # 在下游眼裡長得一樣。
    truncated = [f"{k}（{r['data']['total_rows']}→{r['data']['kept_last']}）"
                 for k, r in out.items()
                 if r["status"] == "ok" and isinstance(r.get("data"), dict)
                 and r["data"].get("dropped")]
    if truncated:
        print(f"\n只保留最後幾列：{'、'.join(truncated)}")

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
