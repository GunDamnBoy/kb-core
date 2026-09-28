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


# ── 衍生狀態檔：訊號帳本與上游指紋基準（2026-09-29 補回）──────────────────
#
# 兩支都是從舊 repo 的 `publish.py`／`cwlib.py` 搬過來的，**改了兩處**：
# 同結果重判改為 no-op（見 fold_calls 的 docstring），以及 open 先於 close 處理。08-23 搬家時它們沒有跟過來，
# 帳本與指紋從那天起停住，而回執一直是 exit 0。見 `kbcore/system.py` 的 `side_files`。

CALL_RESULTS = ("hit", "miss", "expired", "void")


def fold_calls(ledger: dict, issue: dict):
    """把單期 JSON 的 calls.open/close 機械折入帳本。回傳（新帳本, 錯誤清單）。純函式。

    ## 同結果重判是 no-op（與舊版唯一的差別）

    舊版只容許「同一期、同一個 result」的冪等重跑，別期再結一次同一筆就是錯。
    **帳本停住的那五週把這條規則逼出了第二種合法情形**：PREP 拿不到新帳本，
    於是把已結案的帳目再撈出來，排程照規矩「重新裁決一次」—— 第 009 期重判
    c003-1／c003-5，結果跟第 008 期相同。那不是矛盾的判決，是同一個判決被問了兩次。

    所以：**已結案、且 result 相同 → 保留原結案（日期與理由不動），不是錯**；
    result 不同才是真的衝突，照舊擋下。「不能重複結案」要防的是改判，不是重述。
    """
    calls = {c["id"]: c for c in ledger.get("calls", [])}
    errs = []
    cc = issue.get("calls") or {}
    # 型別不對要回成錯誤清單（→ ValueError → exit 10），不能讓 TypeError 一路拋出去：
    # publish 只接 ValueError，其他例外會讓那一輪**沒有回執**。
    if not isinstance(cc, dict) or not all(isinstance(cc.get(k, []), list) for k in ("open", "close")) \
            or not all(isinstance(x, dict) for k in ("open", "close") for x in cc.get(k, [])):
        return ledger, ["calls 的形狀不對：要是 {open: [...], close: [...]}，每筆是物件"]
    for op in cc.get("open", []):
        cid = op.get("id")
        if not cid or not str(cid).strip():
            errs.append("calls.open 有帳目缺 id")
        elif cid in calls:
            ex = calls[cid]
            if ex.get("issue") == issue.get("issue") and ex.get("opened") == issue["date"] \
                    and ex.get("claim") == op.get("claim"):
                continue
            errs.append(f"calls.open 的 id 重複：{cid}（帳目 id 必須全域唯一，建議格式 c{int(issue.get('issue') or 0):03d}-N）")
        elif not op.get("claim") or not op.get("judge"):
            errs.append(f"calls.open 的 {cid} 缺 claim 或 judge —— 沒有裁判方法的判斷不能登帳")
        else:
            calls[cid] = {"id": cid, "opened": issue["date"], "issue": issue.get("issue"),
                          "kind": op.get("kind", "watch"), "claim": op["claim"],
                          "judge": op["judge"], "deadline": op.get("deadline"),
                          "status": "open"}
    # open 先於 close：同一期開、同一期結（罕見但合法）不該被判成「結不存在的帳」。
    for cl in cc.get("close", []):
        cid, res = cl.get("id"), cl.get("result")
        if res not in CALL_RESULTS:
            errs.append(f"calls.close 的 {cid} result={res!r} 不合法（{'/'.join(CALL_RESULTS)}）")
        elif cid not in calls:
            errs.append(f"calls.close 引用不存在的帳目 id：{cid}")
        elif calls[cid].get("status") != "open":
            if calls[cid].get("status") == res:
                continue                      # 同結果重判：保留原結案
            errs.append(f"calls.close 的 {cid} 已是 {calls[cid].get('status')}，"
                        f"不能改判為 {res} —— 發布後才發現判錯，掛 errata")
        else:
            calls[cid] = {**calls[cid], "status": res, "closed": issue["date"],
                          "closedIssue": issue.get("issue"), "closeNote": cl.get("note", "")}
    return {"calls": sorted(calls.values(), key=lambda c: (c.get("opened", ""), c["id"]))}, errs


def _dim_ids(bub: dict) -> list:
    d = bub.get("dims")
    if isinstance(d, dict):
        return sorted(d.keys())
    if isinstance(d, list):
        return [x.get("id") for x in d]
    return []


def upstream_fingerprint(bub: dict) -> dict:
    """監控庫的指紋。**與 `convergence-weekly/cwlib.py` 同名函式逐欄相同** ——
    `prepare.py` 用那一份讀基準、這裡寫基準，兩邊鍵不一致的話 PREP 每期都會亮 🛑。
    改其中一份就要改另一份。"""
    dm = bub.get("dimMeta", {}) or {}
    return {
        "dims": _dim_ids(bub),
        "weights": {k: (dm.get(k) or {}).get("w") for k in _dim_ids(bub)},
        "triggers": [{"id": t.get("id"), "name": t.get("name")}
                     for t in bub.get("triggers", []) or []],
        "indicators": sorted(i.get("id") for i in bub.get("indicators", []) or []),
        "tw_items": sorted(i.get("id") for i in (bub.get("tw") or {}).get("items", []) or []),
        "checklist": [c.get("item") for c in (bub.get("stage") or {}).get("checklist", []) or []],
        "zones": [{"max": z.get("max"), "label": z.get("label")}
                  for z in bub.get("zones", []) or []],
        "meta_version": (bub.get("meta") or {}).get("version"),
    }


def side_files(doc: dict, repo: Path, payload) -> dict:
    """帳本折入 ＋ 指紋基準。折帳有錯就 raise ValueError（publish 回 exit 10、什麼都不寫）。"""
    p = repo / "data" / "calls.json"
    ledger = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"calls": []}
    new_ledger, errs = fold_calls(ledger, doc)
    if errs:
        raise ValueError("calls 折帳擋下：" + "；".join(errs))
    out = {"data/calls.json": json.dumps(new_ledger, ensure_ascii=False, indent=1)}
    bub = (payload or {}).get("bub") if isinstance(payload, dict) else None
    if bub:
        # **只在重發最新一期時更新基準。** 補掛舊期的 errata 也會走 publish，
        # 那時寫今天的指紋不會錯，但「基準＝最近一期發布時」這句話就不成立了。
        idx = repo / "data" / "index.json"
        latest = ""
        if idx.exists():
            ds = json.loads(idx.read_text(encoding="utf-8")).get("days", [])
            latest = max((d.get("date", "") for d in ds), default="")
        if doc["date"] >= latest:
            out["data/upstream.json"] = json.dumps(upstream_fingerprint(bub),
                                                   ensure_ascii=False, indent=1)
    return out


register(System(
    id="convergence-weekly",
    suite="convergence",
    build=build,
    cadence_hours=168,
    republish_rule=errata_only,
    staged_paths=staged_paths,
    index_entry=index_entry,
    index_meta=index_meta,
    side_files=side_files,
))
