"""台股官方端點與黃金保底的取數。

與 `fetch.py` 同一組具名例外，路由在 `fetch.py` 的 `route_of` 裡加。

## 單位陷阱

這一層存在的最大理由不是「發 HTTP 請求」，是**把單位換算收在一個地方**。
三大法人回的是元、融資金額是仟元、月營收是仟元——舊系統靠人記，而人會忘。
每一條路由的 `unit` 欄位就是它的宣告，寫進 raw 檔給下游看。

## 兩個 Chrome 時代的坑在這裡消失

- 「`navigate` 到 JSON 網址會被 Chrome 當檔案下載」——這一層不用 Chrome。
- 「跨子網域 `fetch` 被 CORS 擋」——伺服器端沒有同源政策。

**這是把採集從 Chrome 搬到 Actions 的真正收益**：那兩個坑不是被繞過，是不存在了。
"""
import csv
import io
import json
import urllib.error
import urllib.request
from typing import Dict

from .fetch import UA, TIMEOUT, ParseFailed, UnknownIdent, UpstreamError

ROUTES = {
    "TWSE:BFI82U": {
        "url": "https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={ymd}&type=day&response=json",
        "kind": "json", "unit": "元",
        "note": "三大法人買賣超。**單位是元**，下游要換算成億元。",
    },
    "TWSE:MI_MARGN": {
        "url": "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=MS&response=json",
        "kind": "json", "unit": "仟元",
        "note": "融資融券餘額。**融資金額單位是仟元。**",
    },
    "TPEX:INDEX": {
        "url": "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingIndex?date={y}/{m}/{d}&response=json",
        "kind": "json", "unit": "點",
        "note": "櫃買指數收盤。回傳當月逐日列，**取最後一列**。",
    },
    "TWSE:REV_L": {
        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        "kind": "json", "unit": "仟元",
        "note": "上市公司月營收。**金額單位仟元。**",
    },
    "TWSE:REV_O": {
        "url": "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv",
        "kind": "csv", "unit": "仟元",
        "note": "上櫃公司月營收。**CSV，UTF-8 含 BOM。**",
    },
    "TWSE:CONF": {
        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
        "kind": "json", "unit": "—", "empty_ok": True,
        "note": ("法說會備援（主源是 MOPS 一覽表，需人工）。`符合條款` ＝ 第12款；"
                 "**`主旨 ` 這個欄位名結尾有一個半形空白**；週末回傳 0 筆——"
                 "那是「當日訊息」不是「行事曆」，0 筆是正常狀態不是故障。"),
    },
    "SPDR:GLD": {
        "url": "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv",
        "kind": "csv", "unit": "噸／美元",
        "note": ("GLD 歷史持倉序列。**這條路徑未經實測** —— 舊規格記載 2026-08-16 "
                 "四路徑皆 404、結論是「官網沒有歷史序列 API」，因而改用「讀前一日的"
                 "保底卡相減」。這條若通，那個跨檔相減的 workaround 就不需要了。"
                 "第一次 Actions 實跑就是它的驗證。"),
    },
    "SPDR:GLDM": {
        "url": "https://www.spdrgoldshares.com/assets/dynamic/GLDM/GLDM_US_archive_EN.csv",
        "kind": "csv", "unit": "噸／美元",
        "note": "同上，GLDM。**未經實測。**",
    },
}


def parse_json(raw: bytes, ident: str) -> Dict:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ParseFailed(f"{ident} 回應不是合法 JSON：{e}") from e


def parse_csv(raw: bytes, ident: str) -> Dict:
    """UTF-8 BOM 由 `utf-8-sig` 吃掉。

    **欄位名一律原樣保留，不 strip。** `主旨 ` 結尾那個半形空白是真的，
    幫它清乾淨會讓下游照文件寫的欄位名反而取不到。
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ParseFailed(f"{ident} 不是 UTF-8：{e}") from e
    r = csv.DictReader(io.StringIO(text))
    rows = list(r)
    if r.fieldnames is None:
        raise ParseFailed(f"{ident} 連表頭都沒有 —— 這不是空資料，是不是 CSV")
    # **零列不是錯誤。** 週末的法說會端點回 0 筆是正常狀態（「當日訊息」不是
    # 「行事曆」）。解析器報它看到什麼，「空算不算失敗」是呼叫端的政策 ——
    # 把政策烤進解析器，會讓正常狀態長得跟故障一模一樣。
    return {"columns": list(r.fieldnames), "rows": rows}


def get_tw(ident: str, ymd: str) -> Dict:
    """ymd 形如 20260819。回傳 {ident, url, unit, note, kind, data}。"""
    spec = ROUTES.get(ident)
    if spec is None:
        raise UnknownIdent(f"無法路由的代號：{ident!r}")

    url = spec["url"].format(ymd=ymd, y=ymd[:4], m=ymd[4:6], d=ymd[6:])
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise UpstreamError(f"{ident} 回 {e.code}") from e
    except Exception as e:
        raise UpstreamError(f"連不到 {ident}：{e}") from e

    data = parse_json(raw, ident) if spec["kind"] == "json" else parse_csv(raw, ident)
    return {"ident": ident, "url": url, "unit": spec["unit"],
            "note": spec["note"], "kind": spec["kind"], "data": data}
