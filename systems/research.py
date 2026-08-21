"""外資報告週摘。**第五套，也是唯一一套 payload 要讀 repo 以外的東西的系統。**

## 為什麼 build 讀 repo 外面

另外四套的檢查只看已發布或即將發布的東西，所以 payload 全部從資料 repo 讀得到。
這一套不行：`research.no_pii`、`stance_grounded`、`chart_grounded` 都要拿
**抽取文字**回頭比對，而抽取文字**永不進任何 repo**（原文逐頁蓋有可追溯到
個人的浮水印）。那條界線是結構性的，不是 `.gitignore`。

於是 `build()` 去 `~/broker-research/extracted/` 讀。這是刻意的例外，代價是
publish 對這一套多了一個 repo 以外的依賴 —— 所以下面那行 `if not docs: raise`
是整個檔案裡最重要的一行：**抽取目錄不見時，`docs` 會是空 list，
而空 list 會讓每一條逐字比對的檢查 vacuously 通過**。
七份報告的原句一句都沒驗到，十條檢查全綠，回執 exit 0。
那正是這一套系統一路在抓的形狀，只是換到了接縫上。

## 為什麼 `date` 是週日

publish 以 `draft["date"]` 命名 `data/<date>.json` 並據以排序，那是日頻的形狀。
週摘沒有「當日」，所以用**該 ISO 週的最後一天（週日）**當 key ——
它唯一、可排序、而且跟 `range[1]` 逐字相同。週次本身留在 `week` 欄位裡。
"""
import datetime as dt
import glob
import json
import os
import re
from pathlib import Path

from kbcore.system import System, register

ROOT = Path(__file__).resolve().parent.parent
# **抽取目錄有兩個可能的家，而它們會給出不同的答案。**
# 2026-08-21 實測：沙箱裡有一份 12:43 留下的舊拷貝住在 `~/broker-research/extracted`，
# 真正在用的那份在別的路徑。`research_verify` 吃參數、這裡吃 `~`，於是同一批資料
# 兩邊算出不同的結果 —— 一邊全綠、一邊擋下來，**而兩邊看起來都很合理**。
# 環境變數讓「要驗哪一份」變成可以明講的東西，而不是各自預設。
EXTRACTED = os.path.expanduser(
    os.environ.get("RESEARCH_EXTRACTED", "~/broker-research/extracted"))


def build(draft: dict, repo: Path) -> dict:
    files = sorted(glob.glob(os.path.join(EXTRACTED, "*.json")))
    docs = [json.loads(open(f, encoding="utf-8").read()) for f in files]
    if not docs:
        # **空 list 會讓每一條逐字比對的檢查 vacuously 通過。** 見檔頭。
        raise RuntimeError(
            f"{EXTRACTED} 底下沒有抽取結果 —— 這一套的檢查要拿抽取文字回頭比對，"
            "拿不到就**沒有資格判**。這跟「比對過、都對」是兩件事")
    slugs = {d.get("slug") for d in docs}
    missing = [r.get("slug") for r in draft.get("reports") or []
               if r.get("slug") not in slugs]
    if missing:
        # 草稿裡有、抽取目錄裡沒有：那幾份的原句與圖表數字這一輪**驗不到**，
        # 而它們仍然會被發布出去。
        raise RuntimeError(
            f"草稿裡有 {len(missing)} 份在抽取目錄裡找不到：{missing[:3]} —— "
            "那幾份的原句與圖表數字這一輪沒有東西可以比對")
    return {
        "docs": docs,
        "chart_files": chart_files(draft, repo),
        "anchors": json.loads((ROOT / "research" / "anchors.json").read_text(encoding="utf-8")),
        "advisory_anchors": json.loads(
            (ROOT / "advisory" / "anchors.json").read_text(encoding="utf-8")),
        "digest": draft,
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


_NUM = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、.]|\d+[、.)])\s*")
_LEAD = re.compile(r"^(?:一句話(?:主張)?|主張|結論|重點|核心)\s*[：:]\s*")
_ASK = re.compile(r"(?:什麼|嗎|呢|為何|\?|？)\s*$")


def chart_files(draft: dict, repo: Path):
    """digest 宣稱的每個圖檔，在**資料 repo 裡**實際多大。

    **這是「檢查讀本機、讀者拿到 404」那個形狀的專屬防線。**
    圖是由 `assemble.py` 複製進 repo 的，而它跑在 Cowork 的掛載視角下 ——
    資料夾沒接上時那一步做不到，**但草稿仍然會發布成功**：
    JSON 上線、網站更新、回執 exit 0，只有圖是 404。每一個訊號都說成功。

    找不到檔案回 None，不是 0 —— 「沒有這個檔」與「檔案是空的」是兩件事，
    處置也不同（前者是沒複製進來、後者是渲染壞了）。
    """
    d = repo / "charts" / (draft.get("week") or "")
    out = {}
    for r in draft.get("reports") or []:
        for c in r.get("charts") or []:
            for k in ("png", "svg"):
                n = c.get(k)
                if n:
                    f = d / n
                    out[n] = f.stat().st_size if f.exists() else None
    return out


def _headline(summary: str) -> str:
    """索引卡片上那一行。**第一個標題優先，但問句形狀的標題要退回內文。**

    首批七份裡有三份的第一個標題是欄目名而不是主張
    （「一、這份報告要你相信什麼」「這一期在爭什麼」）——
    照搬上卡片，讀者從列表上分不出這三份在講什麼，
    **而卡片看起來完全正常**。`preamble` 已加規則要求第一個標題寫成主張；
    這裡的退路是給既有資料與下一個忘了的人。

    取不到就回空字串。**不要無條件退回內文第一行** ——
    那是一整段，塞進卡片會變成沒有斷點的一塊字。
    """
    lines = (summary or "").splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        h = _LEAD.sub("", _NUM.sub("", line.lstrip("# ").strip())).strip()
        if h and not _ASK.search(h):
            return h
        # 問句標題：改用它底下第一段的第一句。
        for nxt in lines[i + 1:]:
            t = nxt.strip()
            if not t or t.startswith("#"):
                continue
            t = re.sub(r"\*\*|__|`", "", t)
            # 退路本來就比不上一個寫好的主張，所以**寧可短**：
            # 截到第一個句讀，再硬切 40 字並留一個看得見的刪節號。
            t = re.split(r"[。；]|——", t)[0].strip()
            return t if len(t) <= 40 else t[:40] + "…"
        return h
    return ""


def index_entry(doc: dict) -> dict:
    """索引就是**站台上的檢索層**：標籤篩選、券商篩選、關鍵字搜尋全部只讀這一份，
    點進去才載那一週的完整 JSON。

    所以這裡要帶的是「找得到」需要的欄位，不是「讀得完」需要的欄位 ——
    精華本文刻意不進索引（七份三萬字，每次開站台都載一次）。
    """
    return {
        "date": doc["date"],
        "week": doc.get("week", ""),
        "range": doc.get("range") or [],
        "reports": doc.get("reports_count", len(doc.get("reports") or [])),
        "brokers": doc.get("brokers") or {},
        "tags": sorted((doc.get("tags") or {}).keys()),
        "items": [{
            "slug": r.get("slug"),
            "broker": r.get("broker"),
            "title": r.get("title"),
            "date": r.get("date"),
            "pages": r.get("pages"),
            "tags": r.get("tags") or [],
            "chars": r.get("summary_chars", 0),
            "headline": _headline(r.get("summary", "")),
        } for r in doc.get("reports") or []],
        "file": f"data/{doc['date']}.json",
    }


def index_meta(doc: dict) -> dict:
    """`updatedLabel` 存在的理由跟另外三套一樣：`days[0].date` 是週日、
    每一期都會被寫成新的一週，**只看它看不出推送鏈斷掉**。
    """
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    return {
        "title": "外資報告週摘",
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "updatedLabel": f"{now.month}/{now.day} {now:%H:%M}",
    }


def staged_paths(doc: dict, repo: Path) -> list:
    """`data/` 加上這一期的圖。

    **`charts/<week>/` 跟 `data/` 是兩個都得推的東西，不是一主一附** ——
    每日五圖 2026-08-21 那次的教訓逐字適用：檢查讀的是本機檔案系統，
    圖沒推上去它一樣全綠，而讀者拿到的是 404。
    """
    out = ["data"]
    w = doc.get("week", "")
    if w and (repo / "charts" / w).is_dir():
        out.append(f"charts/{w}")
    return out


register(System(
    id="broker-research-digest",
    suite="research",
    build=build,
    staged_paths=staged_paths,
    index_entry=index_entry,
    index_meta=index_meta,
))
