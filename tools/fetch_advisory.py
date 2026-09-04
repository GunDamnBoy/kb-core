#!/usr/bin/env python3
"""投顧保底層 —— 跑在 GitHub Actions，把「每天一定拿得到」的東西先抓好。

用法：fetch_advisory.py <raw 目錄> [YYYYMMDD]
      fetch_advisory.py --top-up <既有的 raw json> --only IDENT[,IDENT...]

**補抓模式（`--top-up`）解的是取數時點問題，不是取數失敗問題。**
Actions 那一班跑在台北凌晨（cron 00:15、實測延到 03:23），而有兩件事那時候還沒發生：

- **SPDR 的紐約歸檔要到台北 04:00–04:45 才上站** —— 凌晨取到的是**前一個交易日**那一列，
  而前一版已經用過它。照用不會報錯，只會讓 `advisory.exempt_card_freshness` WARN。
- **TWSE 的 OpenAPI 在深夜維護窗內會回空字串或 HTML** —— 2026-09-03 那一班
  `REV_L`／`REV_O`／`CONF` 三個同時失敗，而同日稍晚實測三個端點全部 200、URL 一個字都沒變。

**兩個症狀、一個病。** 修法不是把 Actions 往後挪（那會壓縮它對排程延遲的餘裕，
實測延遲曾達 7 小時 39 分），而是讓 Mac 本機在台北 07:20 那一班**補抓那幾個**，
因為 07:20 既晚於紐約歸檔也避開了維護窗。

補抓有一條不可讓步的性質：**補抓失敗時保留原值。**
原值可能過期，但它至少是資料；補抓失敗若把它清掉，就是「補一次讓情況變糟」。
補了什麼、保留了什麼，逐項記進 `top_ups`，因為**下游必須分得出「這一列是補抓來的」
與「這一列是凌晨那一班的、補抓沒成功」** —— 這兩者在 `items` 裡長得一模一樣。

**2026-09-04 加第三種結局：抓成功了，但抓回來的跟原本那一份一模一樣。**
當天 `top_ups` 回報 `replaced` 五個 ident 全中、`kept_original` 空的，看起來完全成功；
而 SPDR 補回的歷史檔**最後一列仍是 `02-Sep-2026`，與前一版用過的那一列相同**，
當輪的採集端現場開產品頁才確認 `03-Sep` 已經上站。
**`replaced` 只證明「抓取這個動作成功了」，不證明「資料前進了一天」** ——
而下游照抄的話會產出一張與前一版逐字相同的保底卡，`exempt_card_freshness` 只會給一個 WARN。
所以現在每個 ident 在覆蓋前後各取一次 `data` 的指紋，**內容沒動的另外記進 `unchanged`**。
`replaced` 的語意刻意不動（仍是「抓取成功」的全集），因為它已經有下游在讀；
`unchanged` 是加上去的一個子集，只讀 `replaced` 的下游行為完全不變。

**這個欄位同時就是量測。** 2026-09-04 只證明了「台北 07:20 時 archive 沒有 03-Sep」，
而產品頁那一次是 49 分鐘後、且是**不同的端點** ——
「archive 落後一整天」還是「archive 貼得比 07:20 晚」**尚未分辨**。
明天起 `unchanged` 會自己回答：若 SPDR 天天落在 `unchanged` 裡就是前者，
偶爾才落就是後者，而修法與量測是同一件事、不必另外安排。

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
import hashlib
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


def parse_flags(argv):
    """把 `--only` 與 `--top-up` 拆出來，位置參數維持原樣。

    刻意不用 argparse：這支被 Actions 以 `fetch_advisory.py raw` 呼叫，
    位置參數的行為一個字都不能變，而 argparse 會把 `--` 開頭的未知參數變成錯誤，
    也會自己接管 `-h`。手寫這十行的代價比「某天 Actions 那一行安靜地改變行為」低。
    """
    only, top_up, rest = None, None, []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a.startswith("--only="):
            only = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
        elif a == "--only":
            i += 1
            only = [s.strip() for s in argv[i].split(",") if s.strip()]
        elif a.startswith("--top-up="):
            top_up = Path(a.split("=", 1)[1])
        elif a == "--top-up":
            i += 1
            top_up = Path(argv[i])
        else:
            rest.append(a)
        i += 1
    return only, top_up, rest


def _payload_fingerprint(item) -> str:
    """一個 ident 的內容指紋。**只看 `data`，不看 `note`／`url`／`unit`** ——
    後面那幾個是靜態的說明欄，把它們算進去不會改變結果，但會讓指紋的意義變模糊。

    刻意用整份 payload 的雜湊，而不是「最後一列的日期」：後者要為每一種 ident 的
    形狀各寫一個取法（FRED 的 `points[-1][0]`、SPDR 的 `rows[-1][0]`、TWSE 的
    `data[0]['出表日期']`…），**而那正是這個檔已經有過一次的漂移形狀** ——
    多一份對形狀的假設，就多一個會安靜過期的地方。雜湊不需要知道任何形狀。
    代價是它答不出「新的那一列是哪一天」，只答得出「有沒有動」；
    對「補抓到底有沒有讓資料前進」這個問題，有沒有動就夠了。
    """
    if not isinstance(item, dict):
        return ""
    return hashlib.sha1(
        json.dumps(item.get("data"), sort_keys=True, ensure_ascii=False,
                   default=str).encode("utf-8")).hexdigest()


def top_up(path: Path, only) -> int:
    """把 `only` 那幾個 ident 重抓一次，成功的才覆蓋回 `path`。"""
    if not only:
        print("`--top-up` 必須搭配 `--only`：不指定補哪幾個等於整份重抓，"
              "而整份重抓是位置參數那條路，不是這一條", file=sys.stderr)
        return Exit.BAD_INPUT
    if not path.exists():
        print(f"補抓對象不存在：{path}", file=sys.stderr)
        return Exit.ENVIRONMENT
    known = set(FRED_IDENTS) | set(TW_IDENTS)
    unknown = [i for i in only if i not in known]
    if unknown:
        print(f"不認得的 ident：{'、'.join(unknown)}", file=sys.stderr)
        return Exit.BAD_INPUT

    doc = json.loads(path.read_text(encoding="utf-8"))
    items = doc["items"]
    ymd = doc["date"].replace("-", "")
    print(f"補抓 {path.name}（date={doc['date']}）：{'、'.join(only)}")

    replaced, kept, unchanged = [], [], []
    for ident in only:
        # **覆蓋前先取一次指紋。** 這一行就是 2026-09-04 那次「五個全中但資料沒前進」
        # 的解藥：沒有它，成功與空轉在 `top_ups` 裡長得一模一樣。
        before_fp = _payload_fingerprint(items.get(ident))
        r = fetch_one(ident, ymd)
        if r["status"] == "ok":
            items[ident] = r
            replaced.append(ident)
            if _payload_fingerprint(r) == before_fp:
                unchanged.append(ident)
                print(f"  {ident:16} ok —— 已取代，**但內容與原本那一份完全相同**"
                      f"（抓到了，資料沒有前進）")
            else:
                print(f"  {ident:16} ok —— 已取代")
        else:
            # **保留原值。** 見模組 docstring：補抓失敗把原值清掉是「補一次讓情況變糟」。
            kept.append(ident)
            prev = items.get(ident, {}).get("status", "缺席")
            print(f"  {ident:16} {r['reason']} —— 補抓失敗，保留原值"
                  f"（原本是 {prev}）：{r['detail'][:70]}")

    # **拿合併後的整份重算，不是拿補抓的子集算。** 只算子集會讓沒被補抓的那些
    # 失敗項從清單裡消失，而它們還在 `items` 裡失敗著。
    doc["failed_essential"] = sorted(
        i for i, r in items.items() if r.get("status") == "failed" and i in ESSENTIAL)
    doc["failed_other"] = sorted(
        i for i, r in items.items() if r.get("status") == "failed" and i not in ESSENTIAL)
    doc.setdefault("top_ups", []).append({
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "requested": list(only), "replaced": replaced, "kept_original": kept,
        # `unchanged` ⊆ `replaced`。**刻意是子集而不是第三個互斥狀態** ——
        # 已經有下游在讀 `replaced`，把它拆掉會安靜地改變那些讀者的意思。
        "unchanged": unchanged,
    })

    # 原子寫入：同目錄 .tmp 再 rename。這個檔每天早上會被輪次讀，
    # 而輪次讀到寫到一半的 JSON 會是一個沒有人看得懂的失敗。
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)

    print(f"\n補抓 {len(replaced)}/{len(only)} 成功"
          f"{'；保留原值：' + '、'.join(kept) if kept else ''}"
          f"{'；**抓到了但內容沒變**：' + '、'.join(unchanged) if unchanged else ''}")
    print(f"合併後：必要項失敗 {len(doc['failed_essential'])}、"
          f"其餘失敗 {len(doc['failed_other'])}")
    if doc["failed_essential"]:
        print(f"必要項仍然掛著：{'、'.join(doc['failed_essential'])}", file=sys.stderr)
        return Exit.ENVIRONMENT
    return Exit.OK


def main(argv) -> int:
    try:
        only, top_up_path, rest = parse_flags(argv)
    except IndexError:
        print(__doc__)
        return Exit.BAD_INPUT
    if top_up_path is not None:
        return top_up(top_up_path, only)
    if not 1 <= len(rest) <= 2:
        print(__doc__)
        return Exit.BAD_INPUT
    argv = [argv[0]] + rest
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
