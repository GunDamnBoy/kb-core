#!/usr/bin/env python3
"""驗當天那一輪 podfetch 的取數品質。

用法：podcast_verify.py <逐字稿根目錄> [日期 YYYY-MM-DD]

    podcast_verify.py ~/podcast-transcripts
    podcast_verify.py ~/podcast-transcripts 2026-08-20

## 為什麼是獨立一支，不是塞進 podfetch

podfetch 半夜 01:00 跑，出問題的時候人在睡覺。**判定與執行分開**，
才能在早上用同一組檢查重跑一次同一份 manifest，而不必重抓一次音檔。

同一個理由也讓 payload 的組裝集中在這裡：檢查本身不做 IO，
所以「manifest 在哪、shows 在哪、anchors 在哪」只有這一個家。

## 逐字稿在 repo 外面，這支程式不改變那件事

它只讀 manifest，不讀 `.md`、不寫任何東西。
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: F401,E402
from kbcore.report import report, run_all  # noqa: E402
from kbcore.result import Exit  # noqa: E402

TPE = dt.timezone(dt.timedelta(hours=8))

TS_RE = re.compile(r"^\[\d{1,2}[:.]\d{2}(?::\d{2})?\]\s*", re.M)
SPK_RE = re.compile(r"(?:^|\s)Speaker\s*\d+\s*[:\]]\s*", re.M)
NOISE_RE = re.compile(r"[^\w\s]+")


def _tokens(text: str):
    """把逐字稿正規化成 token 串：去 front matter、時間戳、講者標記、標點，轉小寫。

    講者標記那條刻意同時吃 `Speaker 6:` 與 `Speaker 6]` —— Bloomberg 那幾集有
    冒號被轉成右方括號的行，只認冒號的話那些行會整行被當成內容。
    """
    body = text.split("---", 2)[-1]
    return NOISE_RE.sub(" ", SPK_RE.sub(" ", TS_RE.sub(" ", body)).lower()).split()


def block_repeats(text: str, k: int):
    """找出整段被重播的區塊。回傳 [{tokens, first, second}]，門檻不在這裡判。

    先找重複的 k-gram，再把**位置連續**的併成區塊 —— 單獨一個 k-gram 是慣用語，
    連成一長串才是整段重播。判定門檻交給檢查，因為門檻的家在 anchors。

    這支程式做 IO、檢查不做，跟 `watch_sentinel.py` 的 `code_drift()` 是同一道 seam。
    """
    toks = _tokens(text)
    seen, dup = {}, []
    for i in range(len(toks) - k + 1):
        g = " ".join(toks[i:i + k])
        if g in seen:
            dup.append((seen[g], i))
        else:
            seen[g] = i
    out, cur = [], None
    for a, b in dup:
        if cur and a == cur[0] + cur[2] and b == cur[1] + cur[2]:
            cur = (cur[0], cur[1], cur[2] + 1)
        else:
            if cur:
                out.append(cur)
            cur = (a, b, 1)
    if cur:
        out.append(cur)
    return [{"tokens": n + k - 1, "first": a, "second": b} for a, b, n in out]


def main(argv) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return Exit.BAD_INPUT

    root = Path(argv[1]).expanduser()
    date = argv[2] if len(argv) == 3 else dt.datetime.now(TPE).strftime("%Y-%m-%d")
    mf = root / date / "manifest.json"

    if not mf.exists():
        # 「那一輪沒跑」與「跑了但沒收到東西」是兩件事，而這裡只看得出前者。
        print(f"EMPTY_ROUND  找不到 {mf} —— 那一輪沒有產出 manifest",
              file=sys.stderr)
        return Exit.EMPTY_ROUND

    try:
        manifest = json.loads(mf.read_text())
    except json.JSONDecodeError as e:
        print(f"BAD_INPUT  {mf} 不是合法的 JSON：{e}", file=sys.stderr)
        return Exit.BAD_INPUT

    anchors = json.loads((ROOT / "podcast/anchors.json").read_text())
    k = anchors["quality"]["block_repeat_shingle"]
    repeats = {}
    for e in manifest.get("episodes") or []:
        f = root / date / (e.get("file") or "")
        # 檔案不在就記成 None，**跟「掃過了沒有重複」是兩件事**。
        repeats[e.get("file")] = (block_repeats(f.read_text(), k)
                                  if e.get("file") and f.exists() else None)
    missing = [n for n, v in repeats.items() if v is None]
    if missing:
        print(f"  逐字稿找不到 {len(missing)} 份：{'、'.join(missing[:3])}")
    repeats = {n: v for n, v in repeats.items() if v is not None}

    payload = {
        "manifest": manifest,
        "repeats": repeats,
        "shows": json.loads((ROOT / "scripts/podcast/shows.json").read_text()),
        "anchors": anchors,
        "now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    print(f"{date}｜{len(manifest.get('episodes') or [])} 集｜{mf}")
    return report(run_all(payload, suite="podfetch"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
