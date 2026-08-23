"""主題匯流訊號報。**第六套，也是唯一一套 payload 要讀五個上游的系統。**

## 為什麼 build 讀 repo 外面

跟外資報告同一個理由，但更極端：這一套的檢查要拿**五個上游的原始資料**回頭比對
——敘事佐證要逐字回查投顧／節目／圖表的語料，量化佐證要對回監控庫的 `data.json`，
賣方佐證要對回外資報告的 `stances`。那些東西全部不在這個 repo 裡，也不該在。

於是 `build()` 去 `work/` 讀 `prepare.py` 產出的摘要層與上游快照。

## 缺語料一律 raise，不是回空

舊系統這裡是 exit 2 的黃燈，而規格寫著「**黃燈不是通過，publish 一律當失敗**」。
搬進來之後 publish 只擋 FAIL、不擋 SKIPPED，所以那條紀律必須改由這裡執行：

**缺語料就 raise。** 理由跟外資報告的 `if not docs: raise` 逐字相同——
空的語料會讓每一條逐字比對的檢查 **vacuously 通過**，
十幾條檢查全綠、回執 exit 0，而一條佐證都沒有被驗到。

離線稽核（拿舊期回頭驗）走 `tools/convergence_verify.py`，
那裡語料本來就不存在，對應的檢查會誠實回 SKIPPED。**兩條路刻意分開。**

## 索引鍵用 `days` 不用 `issues`

舊 repo 的 `index.json` 用 `issues`。`tools/publish.py` 寫死 `days`，
而 `tools/verify_site_index.py`、哨兵、`verify_live.py` 也全部走 `days`。

**這裡選擇對齊，而不是給 `System` 加第五個 `index_key` 參數。**
`kbcore/system.py` 的檔頭已經記了這道接縫被補過四次
（`index_entry`／`index_meta`／`staged_paths`／`republish_rule`），
每一次都是「第二個使用者才發現」。加第五個維度的成本不是這一次的改動，
是**之後每一支共用工具都要記得尊重它**——而忘記的那次不會有徵兆。

週頻用 `days` 這個名字有點怪，但外資報告週摘也是週頻、也叫 `days`。
名字的怪是看得見的，接縫的洞不是。
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from kbcore.system import System, register

TPE = dt.timezone(dt.timedelta(hours=8))

# `prepare.py` 產在這裡。**路徑由環境變數決定，不靠 `~` 猜** ——
# 理由見 `scripts/research/_paths.py` 的檔頭：同一個 `~` 在 launchd 與 Cowork
# 沙箱裡展開成不同的地方，而錯的那一種是安靜的。
WORK_ENV = "CONVERGENCE_WORK"


def work_dir() -> Path:
    return Path(os.path.expanduser(os.environ.get(WORK_ENV, "~/convergence-weekly/work")))


def _read(p: Path, what: str) -> str:
    if not p.exists():
        raise RuntimeError(
            f"缺 {what}（{p}）—— **這一套的檢查要拿它回頭逐字比對，拿不到就沒有資格判**。\n"
            "  空語料會讓每一條佐證檢查 vacuously 通過：十幾條全綠、回執 exit 0，\n"
            "  而一條佐證都沒有被驗到。先跑 prepare.py。")
    return p.read_text(encoding="utf-8")


def build(draft: dict, repo: Path) -> dict:
    """(草稿, 資料 repo) → payload。**讀檔全部在這裡，檢查本身不做 IO。**"""
    w = work_dir()
    corpora = {k: _read(w / f"{k}.txt", f"{k}.txt 語料")
               for k in ("adv", "pod", "cotd", "res")}
    bub_path = w / "bub" / "data.json"
    if not bub_path.exists():
        raise RuntimeError(
            f"缺監控庫快照（{bub_path}）—— 量化佐證與量化對帳全部驗不到。先跑 prepare.py。")
    stances_path = w / "stances.json"
    idx_path = repo / "data" / "index.json"
    return {
        "draft": draft,
        "corpora": corpora,
        # **監控庫吃原始 `data.json`，不吃壓縮過的 `bub.txt`** ——
        # 舊系統這裡餵錯過，症狀是整批檢查直接壞掉（`--bub` vs `--cotd` 不同型）。
        "bub": json.loads(bub_path.read_text(encoding="utf-8")),
        "stances": (json.loads(stances_path.read_text(encoding="utf-8"))
                    if stances_path.exists() else None),
        "index": (json.loads(idx_path.read_text(encoding="utf-8"))
                  if idx_path.exists() else {"days": []}),
        "now": dt.datetime.now(TPE).isoformat(timespec="seconds"),
    }


def index_entry(doc: dict) -> dict:
    """索引是**跨期趨勢圖的唯一資料來源**，所以量化快照要逐欄帶齊。

    舊系統的頭號隱性事故就在這裡：快照漏寫一欄，趨勢圖少一個點，
    **頁面不會報錯**，而歷史永不改寫 —— 那個缺口會永遠留在線上。
    `checks/convergence.py` 的 `index_snapshot` 是逐欄等值對帳，就是為了這件事。
    """
    q = doc.get("quant") or {}
    dims = {x.get("id"): x.get("v") for x in (q.get("dims") or [])}
    qd = q.get("quadrant") or {}
    st = q.get("stage") or {}
    return {
        "date": doc["date"],
        "issue": doc.get("issue"),
        "label": doc.get("label", ""),
        # **`short` 是推導值，不是抄寫值。** 第一版寫 `doc.get("short","")` ——
        # 單期 JSON 根本沒有這個欄位，於是索引裡的 `8/16` 對上空字串。
        # 抄一個來源沒有的東西，拿到的一定是預設值，而預設值不會報錯。
        "short": f"{int(doc['date'][5:7])}/{int(doc['date'][8:10])}",
        "headline": doc.get("headline", ""),
        "quantVer": q.get("schemaVer"),
        "composite": q.get("composite"),
        "dims": dims,
        "quadrant": {"heat": qd.get("heat"), "support": qd.get("support")},
        "trigLit": sum(1 for t in (q.get("triggers") or []) if t.get("state")),
        "twHeat": q.get("twHeat"),
        "stage": st.get("current"),
        "file": f"data/{doc['date']}.json",
        **({"errata": doc["errata"]} if doc.get("errata") else {}),
    }


def index_meta(doc: dict) -> dict:
    now = dt.datetime.now(TPE)
    return {
        "title": "主題匯流訊號報",
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "updatedLabel": f"{now.month}/{now.day} {now:%H:%M}",
    }


def staged_paths(doc: dict, repo: Path) -> list:
    """`data/` 就是全部 —— 這一套不產圖檔。

    **仍然明寫，不用預設值。** `System` 刻意不給 `staged_paths` 預設，
    理由是「給一個 `['data']` 的預設，等於讓下一套系統安靜地繼承錯的形狀」。
    這一套的答案剛好等於那個預設，但那是答案，不是省略。
    """
    return ["data"]


def errata_only(old: dict, new: dict) -> "str | None":
    """已發布的一期只准**加勘誤**，內文一個字都不准動。

    ## 為什麼不能直接沿用 `append_only`

    `append_only` 是照 `reports[].slug` 比的 —— 那是外資報告週摘的形狀。
    這一套的期沒有 `reports`，套上去 `was` 與 `now` 都會是空 dict，
    於是「沒有不見的、沒有被改的」，**任何改寫都放行**。

    一個為別套系統的 schema 寫的守衛，套在這一套上不會報錯，
    它會安靜地永遠回 None —— 跟「檢查過、沒問題」長得一模一樣。

    ## 為什麼不是 `frozen`

    `frozen` 擋掉一切，包含掛 `errata`。而發布後才發現的問題只有兩種處置：
    改內文（等於改歷史）或掛勘誤。**掛勘誤是「歷史全部保留」與
    「不在頁面上說謊」唯一能同時滿足的做法**，所以它必須是允許的那一個。
    """
    import json as _j
    a = {k: v for k, v in old.items() if k != "errata"}
    b = {k: v for k, v in new.items() if k != "errata"}
    if _j.dumps(a, sort_keys=True, ensure_ascii=False) != _j.dumps(b, sort_keys=True, ensure_ascii=False):
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        return (f"已發布的內容被改了（{diff[:4]}）—— **改草稿沒有用**。"
                "發布後才發現的問題掛 `errata`，不改內文")
    was, now = old.get("errata") or [], new.get("errata") or []
    if len(now) < len(was):
        return f"`errata` 從 {len(was)} 條變成 {len(now)} 條 —— **勘誤只准加，不准撤**"
    return None


register(System(
    id="convergence-weekly",
    suite="convergence",
    build=build,
    cadence_hours=168,
    republish_rule=errata_only,
    staged_paths=staged_paths,
    index_entry=index_entry,
    index_meta=index_meta,
))
