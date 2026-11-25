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

它讀 manifest 與當日逐字稿 `.md`（只為了 `block_repeats`），不寫任何東西。
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
# 正規化與區塊偵測的**唯一一份實作**在 kbcore，podfetch 也 import 同一份 ——
# 各留一份再靠人記得同步，就是這套系統最常見的那種缺陷。
from kbcore.transcript import block_repeats  # noqa: E402

TPE = dt.timezone(dt.timedelta(hours=8))

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
    missing = []
    for e in manifest.get("episodes") or []:
        fname = e.get("file")
        f = root / date / fname if fname else None
        # 檔案不在就記進 missing，**跟「掃過了沒有重複」是兩件事**。
        # 沒有 `file` 鍵的（podfetch `run_deadline`／`quota_stop` 路徑的 FAILED）用
        # showKey-trackId 具名：舊版拿 `e.get("file")` 當鍵，None 會互相蓋掉，
        # 再拿去 join 就 TypeError、在跑任何檢查之前崩掉（2026-11-25 實例）。
        if fname and f.exists():
            repeats[fname] = block_repeats(f.read_text(), k)
        else:
            tid = (e.get("appleUrl") or "").partition("i=")[2]
            missing.append(fname or f"{e.get('showKey')}-{tid}（manifest 無 file 鍵）")
    if missing:
        print(f"  逐字稿找不到 {len(missing)} 份：{'、'.join(missing)}")

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
