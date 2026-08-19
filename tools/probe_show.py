#!/usr/bin/env python3
"""節目探針 —— 「該不該收這檔」變成可量測的問題。

用法：probe_show.py <輸出 json> "<ident>,<ident>,..."
      ident 是 AppleID（純數字），或 `search:<節目名>`
      **用逗號分隔，整串當一個參數傳。**

第一版用空白分隔，於是 workflow 展開 `${{ inputs.idents }}` 時被 shell 切開：
`search:Sharp Tech` → `search:Sharp` ＋ `Tech`，前者搜到一檔美式足球節目、
後者被當成 AppleID 送出去。**而表格照樣印出五行真數字** ——
失敗沒有長得像失敗。節目名裡有空白是常態，所以分隔符不能是空白。

跑在 GitHub Actions（雲端容器連不到 iTunes，Actions 連得到 —— 2026-08-19 實測）。

## 它回答的三件事

- **更新頻率** —— 決定 BG2 這類低頻節目值不值得留（沒發就沒成本）
- **片長分布** —— 決定成本。十個系列同時跑的節目會吃掉整晚的轉錄預算
- **是不是還活著** —— 現役清單裡有沒有已經停更的

## 四個 iTunes 的坑，全部寫進程式

1. **必帶 `&cb=<時間戳>`。** 快取過期綁在確切的查詢字串上，換任何一個變動參數
   就繞開。2026-08-15 不帶 cb 時兩檔主秀都停在 15 天前，帶了立刻拿到當日集數。
2. **第一筆是節目本身**（`wrapperType` 不是 `podcastEpisode`），要跳過。
3. **節目層的 `releaseDate` 可能落後好幾個月** —— 用它判斷停更會出錯，
   一律看集數層日期。這支程式會把兩者都印出來，讓那個落差看得見。
4. **`limit` 越小快取越舊。** 這裡取 50，寧可多抓。
"""
import datetime as dt
import json
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore.fetch import UA, TIMEOUT, ParseFailed, UpstreamError  # noqa: E402
from kbcore.result import Exit  # noqa: E402

LIMIT = 50
UTC = dt.timezone.utc


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise UpstreamError(f"iTunes 回 {e.code}") from e
    except Exception as e:
        raise UpstreamError(f"連不到 iTunes：{e}") from e
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ParseFailed(f"iTunes 回應不是 JSON（{len(raw)} bytes）：{e}") from e


def resolve(term: str, cb: str) -> str:
    """用 search 端點找 AppleID。

    舊環境實測 search 透過 web_fetch 回空字串，所以規格說「找 AppleID 要改用
    WebSearch」。**那是環境限制不是端點限制** —— 這支跑在 Actions，值得試一次，
    而且會把結果據實報出來。
    """
    q = urllib.parse.urlencode({"term": term, "media": "podcast", "limit": 5, "cb": cb})
    d = _get(f"https://itunes.apple.com/search?{q}")
    hits = d.get("results") or []
    if not hits:
        raise UpstreamError(f"search 找不到 {term!r}（回 {d.get('resultCount')} 筆）")
    top = hits[0]
    print(f"    search 命中：{top.get('collectionName')} → {top.get('collectionId')}")
    return str(top["collectionId"])


def probe(ident: str, cb: str, now: dt.datetime) -> dict:
    if ident.startswith("search:"):
        ident = resolve(ident[7:], cb)
    q = urllib.parse.urlencode({"id": ident, "entity": "podcastEpisode",
                                "limit": LIMIT, "cb": cb})
    d = _get(f"https://itunes.apple.com/lookup?{q}")
    results = d.get("results") or []
    if not results:
        raise UpstreamError(f"lookup {ident} 回 0 筆")

    show = next((r for r in results if r.get("wrapperType") != "podcastEpisode"), {})
    eps = [r for r in results if r.get("wrapperType") == "podcastEpisode"]
    if not eps:
        raise UpstreamError(f"{ident} 只回了節目層、沒有集數層")

    def when(e):
        return dt.datetime.fromisoformat(e["releaseDate"].replace("Z", "+00:00"))

    eps.sort(key=when, reverse=True)
    latest = when(eps[0])
    d30 = sum(1 for e in eps if (now - when(e)).days <= 30)
    d90 = sum(1 for e in eps if (now - when(e)).days <= 90)
    mins = sorted(round((e.get("trackTimeMillis") or 0) / 60000)
                  for e in eps if e.get("trackTimeMillis"))
    span = (latest - when(eps[-1])).days or 1

    # 節目層的 releaseDate 與最新集數的落差 —— 坑 #3 的證據
    show_date = show.get("releaseDate")
    lag = None
    if show_date:
        lag = (latest - dt.datetime.fromisoformat(
            show_date.replace("Z", "+00:00"))).days

    return {
        "id": ident,
        "name": show.get("collectionName") or eps[0].get("collectionName"),
        "latest": latest.date().isoformat(),
        "days_since_latest": (now - latest).days,
        "eps_30d": d30, "eps_90d": d90,
        "per_week": round(len(eps) / (span / 7), 2) if span >= 7 else None,
        "minutes": {"min": mins[0], "median": statistics.median(mins),
                    "max": mins[-1]} if mins else None,
        "sampled": len(eps),
        # 取樣被 LIMIT 切斷時，30 天與 90 天會變成同一個數字而看起來像真的。
        # 截斷要具名 —— 跟 XLSX 只留最後 N 列同一條。
        "capped": len(eps) >= LIMIT,
        "show_level_releaseDate": show_date[:10] if show_date else None,
        "show_level_lag_days": lag,
    }


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return Exit.BAD_INPUT
    out_path = Path(argv[1])
    idents = [x.strip() for x in ",".join(argv[2:]).split(",") if x.strip()]
    now = dt.datetime.now(UTC)
    cb = now.strftime("%Y%m%d%H%M%S")

    rows, failed = [], []
    for ident in idents:
        print(f"  探 {ident}")
        try:
            r = probe(ident, cb, now)
            rows.append(r)
        except Exception as e:
            failed.append({"ident": ident, "reason": type(e).__name__, "detail": str(e)})
            print(f"    {type(e).__name__}: {e}")

    print(f"\n{'節目':38} {'最新':>11} {'天前':>5} {'30天':>5} {'90天':>5} "
          f"{'每週':>5} {'片長 min/中位/max':>20}")
    print("-" * 100)
    for r in sorted(rows, key=lambda x: x["days_since_latest"]):
        m = r["minutes"]
        mm = f"{m['min']}/{m['median']:.0f}/{m['max']}" if m else "—"
        cap = " ⚠取樣被截斷" if r["capped"] else ""
        print(f"{(r['name'] or '?')[:36]:38} {r['latest']:>11} "
              f"{r['days_since_latest']:>5} {r['eps_30d']:>5} {r['eps_90d']:>5} "
              f"{str(r['per_week']):>5} {mm:>20}{cap}")

    capped = [r for r in rows if r["capped"]]
    if capped:
        print(f"\n⚠ 取樣被 LIMIT={LIMIT} 截斷 {len(capped)} 檔："
              f"{'、'.join(r['name'][:24] for r in capped)}")
        print("  它們的 30天／90天集數是下限不是實數，每週值也偏低。"
              "高頻節目要單獨用更大的 limit 再探一次。")

    stale = [r for r in rows if r["show_level_lag_days"] and r["show_level_lag_days"] > 30]
    if stale:
        print("\n節目層 releaseDate 落後最新集數超過 30 天（坑 #3 的實證）：")
        for r in stale:
            print(f"  {r['name'][:40]:42} 節目層 {r['show_level_releaseDate']}"
                  f" vs 最新集數 {r['latest']}（差 {r['show_level_lag_days']} 天）")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"probed_at": now.isoformat(timespec="seconds"), "limit": LIMIT,
         "shows": rows, "failed": failed}, ensure_ascii=False, indent=1))
    print(f"\n{len(rows)}/{len(idents)} 成功，寫入 {out_path}")
    return Exit.ENVIRONMENT if failed and not rows else Exit.OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
