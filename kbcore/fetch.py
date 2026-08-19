"""取數層 —— 底盤的第一個 seam。

介面只有兩個函式：`route_of(ident)` 決定去哪裡拿，`get(ident)` 拿回來。
上面是「要哪條序列」，下面是「從哪裡拿」，中間那條線就是 seam。

兩條紀律寫在這一層裡：

1. **代理必須在 spec 明寫，不由取數層自動替換。**
   舊系統寫過「`^SOX` 取不到就改抓 `SOXQ`」，結果 ETF 的資料被寫進指數的快取，
   **圖上標的是指數、數字卻是 ETF**。替換要是一個有意識的決定。

2. **否定訊號要具名。**
   「查無此序列」「解析失敗」「憑證失效」「該日無觀測值」是四件不同的事，
   不可以都退化成 None 或空 list。這裡用四個具名例外表達。
"""
import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

UA = "kb-core/0.1"
TIMEOUT = 30


class FetchError(Exception):
    """取數層的錯誤基底。所有子類都是**具名的否定訊號**。"""


class UnknownIdent(FetchError):
    """代號無法路由 —— 不是「沒資料」，是我們不知道去哪裡拿。"""


class AuthFailed(FetchError):
    """憑證失效或權限不足。**與『取不到資料』分開**，否則換 key 那天會找不到原因。"""


class UpstreamError(FetchError):
    """上游回了非 200，或連不上。重跑可能會好。"""


class ParseFailed(FetchError):
    """拿到東西但解析不了。**與『上游沒給東西』分開。**"""


def route_of(ident: str) -> str:
    """代號樣式明確時樣式優先，不做啟發式猜測。"""
    if ident.startswith("FRED:"):
        return "fred"
    if ident.split(":", 1)[0] in ("TWSE", "TPEX", "SPDR"):
        return "tw"
    raise UnknownIdent(
        f"無法路由的代號：{ident!r}（支援的前綴：FRED、TWSE、TPEX、SPDR）")


def _fred_key() -> str:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise AuthFailed("環境變數 FRED_API_KEY 未設定或為空")
    return key


def parse_fred(raw: bytes) -> List[Tuple[str, float]]:
    """把 FRED 的 observations 轉成 (日期, 值)。

    **FRED 用 '.' 表示該日無觀測值**（例如假日）。它不是 0，也不是錯誤——
    直接跳過，不內插、不拿前一日頂替。舊系統在這裡吃過虧：
    「空值那天直接跳過，不要內插、不要拿前一日頂替」。
    """
    try:
        obs = json.loads(raw)["observations"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ParseFailed(f"FRED 回應解析失敗：{e}") from e

    out = []
    for o in obs:
        v = o.get("value")
        if v is None or v == ".":
            continue
        try:
            out.append((o["date"], float(v)))
        except (ValueError, KeyError) as e:
            raise ParseFailed(f"FRED 觀測值格式異常：{o!r}") from e
    return out


def get(ident: str, start: str = "2020-01-01") -> Dict:
    """取一條序列。回傳 {ident, source, start, points:[[date, value], ...]}。"""
    source = route_of(ident)
    if source != "fred":
        raise UnknownIdent(f"尚未實作的來源：{source}")

    series_id = ident.split(":", 1)[1]
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={_fred_key()}"
        f"&file_type=json&observation_start={start}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            raise AuthFailed(f"FRED 回 {e.code} —— 先確認 key 是否有效") from e
        raise UpstreamError(f"FRED 回 {e.code}") from e
    except Exception as e:
        raise UpstreamError(f"連不到 FRED：{e}") from e

    points = parse_fred(raw)
    if not points:
        raise UpstreamError(f"{ident} 在 {start} 之後沒有任何觀測值")
    return {"ident": ident, "source": source, "start": start,
            "points": [[d, v] for d, v in points]}
