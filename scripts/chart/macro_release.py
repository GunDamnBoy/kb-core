# -*- coding: utf-8 -*-
"""
macro_release.py — 美國三大月度數據發布的偵測與製圖（非農／CPI／PCE）。

設計核心：**不維護發布行事曆。**
    行事曆會過期，而且過期時是靜默的——沒有人會發現今年的日期表還是去年那份。
    改用資料自己的「最後更新時間」：FRED 每條序列都帶 `last_updated`，
    那個時刻就是官方發布的時刻（實測 PAYEMS ＝ 2026-08-07 8:31 AM CDT，
    正是 BLS 非農公布的 8:30 ET）。**只要問「它是不是剛更新的」就夠了。**

時序：三者都在美東 08:30 公布 ＝ 台北 20:30，永遠落在次日 11:30 那輪之前
    約 13 小時，所以每日執行必然接得到，不會漏。

用法：
    python3 ~/kb-core/scripts/chart/macro_release.py --check            # 今天有沒有新發布
    python3 ~/kb-core/scripts/chart/macro_release.py --build NFP        # 印出可直接放進當日 JSON 的圖
    python3 ~/kb-core/scripts/chart/macro_release.py --selftest         # 不打網路，驗證轉換邏輯

取得 `last_updated` 的兩條路（與 fetch.py 同樣的雙路徑設計）：
    A. 有 FRED API key → `fred/series` 端點回 JSON，欄位就叫 last_updated，穩定。
    B. 沒有 key → 解析 `https://fred.stlouisfed.org/data/<ID>` 頁面上的
       「Last Updated」欄位。**那是 HTML 頁面不是文件化 API，改版就會斷**，
       所以解析失敗時大聲拋錯，不要安靜地回「沒有新發布」——
       靜默的否定會讓這套機制無聲失效，那正是本系統反覆踩過的坑。
"""
from __future__ import annotations
import datetime as dt
import json, os, re, sys, urllib.error, urllib.parse, urllib.request

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _repo  # noqa: E402
REPO = _repo.repo()
# 同目錄的兄弟模組。舊制是 os.path.join(REPO, "tools")——
# 那綁在「程式住在資料 repo 底下」這個佈局上，搬家就斷。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F                                        # noqa: E402  沿用取數層與 _redact
import build_series as _bs                                # noqa: E402  轉換的唯一實作

# 每個發布要用的序列。theme 固定為「央行、利率與匯率」——三者都是政策路徑的輸入。
RELEASES = {
    "NFP": {
        "label": "非農就業", "trigger": "PAYEMS",
        "series": {"PAYEMS": "非農就業人數"},
        "release": "BLS Employment Situation",
    },
    "CPI": {
        "label": "消費者物價", "trigger": "CPIAUCSL",
        "series": {"CPIAUCSL": "總體 CPI", "CPILFESL": "核心 CPI"},
        "release": "BLS Consumer Price Index",
    },
    "PCE": {
        "label": "個人消費支出物價", "trigger": "PCEPI",
        "series": {"PCEPI": "總體 PCE", "PCEPILFE": "核心 PCE"},
        "release": "BEA Personal Income and Outlays",
    },
}
THEME = "央行、利率與匯率"
FRESH_HOURS = 36        # 「剛發布」的認定窗口。抓 36 小時是為了容納週末與執行延誤。


# ────────────────────────────────────────────────── 最後更新時間
def last_updated(series_id: str) -> dt.datetime:
    """回傳該序列的最後更新時刻（naive，美中時間 CT）。取不到就拋錯，不回 None。"""
    key = F.fred_key()
    if key:
        url = ("https://api.stlouisfed.org/fred/series"
               f"?series_id={urllib.parse.quote(series_id)}&api_key={key}&file_type=json")
        j = json.loads(F._get(url))
        s = (j.get("seriess") or [{}])[0].get("last_updated")
        if not s:
            raise RuntimeError(f"{series_id}：API 回應沒有 last_updated")
        # 形如 '2026-08-07 08:31:00-05'
        return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")

    html = F._get(f"https://fred.stlouisfed.org/data/{urllib.parse.quote(series_id)}").decode(
        "utf-8", "replace")
    m = re.search(r"Last Updated.{0,200}?(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s*([AP]M)",
                  html, re.S)
    if not m:
        raise RuntimeError(
            f"{series_id}：頁面上找不到 Last Updated——FRED 可能改版了。"
            "**不要把這個當成『沒有新發布』**，那會讓偵測機制無聲失效；請改用 API key 路徑。")
    d, hh, mm, ap = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    hh = hh % 12 + (12 if ap == "PM" else 0)
    return dt.datetime.strptime(f"{d} {hh:02d}:{mm}", "%Y-%m-%d %H:%M")


def check(now: dt.datetime | None = None) -> list:
    """回傳今天「剛發布」的項目清單。now 用 CT，預設取台北時間往回推 13 小時的近似。"""
    now = now or (dt.datetime.utcnow() - dt.timedelta(hours=5))     # UTC → CDT
    out = []
    for kind, cfg in RELEASES.items():
        lu = last_updated(cfg["trigger"])
        age = (now - lu).total_seconds() / 3600
        fresh = 0 <= age <= FRESH_HOURS
        out.append({"kind": kind, "label": cfg["label"], "last_updated": lu.isoformat(),
                    "age_hours": round(age, 1), "fresh": fresh})
    return out


# ────────────────────────────────────────────────── 轉換
# 轉換一律轉呼叫 build_series，**不在這裡另寫一份**。
# 2026-08-09 這裡原本有自己的 mom_change／yoy，兩份實作必然漂移——
# 而當時 build_series 修好了「月頻要按日曆回推」，這裡卻還是位置對應，
# 等於同一個 CPI 序列在兩條路徑上會算出不同的年增率。
def mom_change(d: list, v: list) -> tuple:
    """水準值 → 月增。非農用。**缺月時回 None，不跨缺口相減。**"""
    dd, vv, _ = _bs._transform(d, v, "diff")
    return dd, vv


def yoy(d: list, v: list) -> tuple:
    """物價指數 → 年增率 %。**按日曆回推 12 個月**，找不到基期就跳過該點。

    CPIAUCSL 實測缺過 2025-10；位置對應會讓其後 8 個點變成 13 個月變動
    卻仍標示為年增率——數字看起來完全正常，不會露餡。
    """
    dd, vv, _ = _bs._transform(d, v, "yoy")
    return dd, vv


def moving_avg(v: list, n: int = 3) -> list:
    return [round(sum(v[max(0, i - n + 1):i + 1]) / min(i + 1, n), 1) for i in range(len(v))]


def _tail(d: list, v: list, months: int) -> tuple:
    return d[-months:], v[-months:]


# ────────────────────────────────────────────────── 製圖
def build(kind: str, months: int = 30) -> dict:
    """回傳一個可直接放進當日 JSON `charts[]` 的 dict。

    **文字欄位刻意留空**（title／takeaway／reading／so_what／watch／tags）——
    那是判讀，要由當天的執行者依實際數字寫，不是由工具產生罐頭句。
    工具只負責把「數字與圖」準備好，並在 `_hint` 附上算好的關鍵數值供撰稿引用。
    """
    cfg = RELEASES[kind]
    ids = list(cfg["series"])
    raw = {i: F.get(i, since="2015-01-01") for i in ids}

    series, hint = [], {}
    if kind == "NFP":
        d, v = mom_change(raw["PAYEMS"]["d"], raw["PAYEMS"]["v"])
        ma = moving_avg(v, 3)
        dd, vv = _tail(d, v, months)
        _, mm = _tail(d, ma, months)
        series = [
            {"name": "單月月增", "dates": dd, "values": vv, "style": "bar"},
            {"name": "三個月移動平均", "dates": dd, "values": mm, "style": "line"},
        ]
        hint = {"最新月份": dd[-1][:7], "單月月增（千人）": vv[-1], "三個月均": mm[-1],
                "前值": vv[-2], "近十二個月均": round(sum(v[-12:]) / 12, 1)}
        y_label, y_fmt, zero = "月增（千人）", "{:+,.0f}", True
    else:
        for i in ids:
            d, v = yoy(raw[i]["d"], raw[i]["v"])
            dd, vv = _tail(d, v, months)
            series.append({"name": cfg["series"][i] + " 年增率", "dates": dd, "values": vv})
            hint[cfg["series"][i]] = {"最新": vv[-1], "前值": vv[-2], "月份": dd[-1][:7]}
        # 2% 目標線：常數序列，**只要日期涵蓋頭尾就會連成完整橫線**
        # （2026-08-06 修好 ECharts 依日期對位之後才成立，先前會被擠在最左邊）。
        # **但不能只給頭尾兩點。** `chart.series_wellformed` 對 timeseries 的每條序列要求至少 20 點
        # （防「序列太短畫不出東西」），兩點的參考線會被硬失敗擋下來——
        # 工具產出的圖過不了同一份規範的檢查。2026-08-13 首次真的畫 CPI 當天發現。
        # 補滿與主序列同樣的日期即可，ECharts 依日期對位、matplotlib 用真實日期，兩軌都正確。
        span = list(series[0]["dates"])
        series.append({"name": "聯準會 2% 目標", "dates": span, "values": [2.0] * len(span),
                       "dash": True, "color": "#B8BBBE"})
        y_label, y_fmt, zero = "年增率（%）", "{:.1f}", False

    return {
        "slug": f"{kind.lower()}-release", "slot": "當日主圖", "theme": THEME,
        "title": "", "subtitle": "", "kind": "timeseries",
        "y_label": y_label, "y_fmt": y_fmt, "zero_line": zero,
        "source": f"資料來源：FRED {'、'.join(ids)}（{cfg['release']}），"
                  f"{series[0]['dates'][0][:7]} 至 {series[0]['dates'][-1][:7]}",
        "note": "",
        "series": series,
        "markers": [{"date": series[0]["dates"][-1], "label": f"最新 {cfg['label']}"}],
        "takeaway": "", "reading": "", "so_what": "", "watch": [], "tags": [],
        "_hint": hint,
    }


# ────────────────────────────────────────────────── 自我測試（不打網路）
def selftest() -> int:
    ok = True
    d = [f"2026-{m:02d}-01" for m in range(1, 13)] + ["2027-01-01"]
    v = [100 + i for i in range(13)]
    dd, vv = mom_change(d, v)
    if vv != [1.0] * 12 or len(dd) != 12:
        print("✗ mom_change 錯"); ok = False
    dd, vv = yoy(d, v)
    if len(vv) != 1 or abs(vv[0] - 12.0) > 1e-9:
        print(f"✗ yoy 錯：{vv}"); ok = False
    if moving_avg([3, 3, 3, 9], 3) != [3.0, 3.0, 3.0, 5.0]:
        print("✗ moving_avg 錯"); ok = False

    # 用 2026-08-07 實際的 PAYEMS 水準值驗證非農轉換
    real = [158592, 158436, 158650, 158798, 158861, 158881, 158858]        # 2026-01…07
    _, chg = mom_change([f"2026-{m:02d}-01" for m in range(1, 8)], real)
    if chg[-1] != -23:
        print(f"✗ 非農月增應為 −23，得到 {chg[-1]}"); ok = False
    if moving_avg(chg, 3)[-1] != 20.0:
        print(f"✗ 三個月均應為 20.0，得到 {moving_avg(chg, 3)[-1]}"); ok = False
    print("selftest 全部通過 ✓" if ok else "★ selftest 有錯")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    if "--check" in a:
        for r in check():
            mark = "★ 剛發布" if r["fresh"] else "  "
            print(f"{mark} {r['kind']:4} {r['label']:10} 最後更新 {r['last_updated']}"
                  f"（{r['age_hours']} 小時前）")
        sys.exit(0)
    if "--build" in a:
        print(json.dumps(build(a[a.index("--build") + 1]), ensure_ascii=False, indent=1))
        sys.exit(0)
    print(__doc__)
